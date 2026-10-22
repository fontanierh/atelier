#include "FoliageResidencyBuilder.h"
#include "Engine/StaticMesh.h"

#if WITH_EDITOR
#include "StaticMeshAttributes.h"
#include "StaticMeshResources.h"
#include "MeshDescription.h"
#include "StaticMeshOperations.h"
#include "MeshReductionSettings.h"
#include "IMeshReductionManagerModule.h"
#include "IMeshReductionInterfaces.h"
#include "OverlappingCorners.h"
#include "Modules/ModuleManager.h"
#include "StaticMeshCompiler.h"
#include "PhysicsEngine/BodySetup.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Misc/PackageName.h"
#include "Misc/SecureHash.h"
#include "Serialization/JsonSerializer.h"
#include "PhysicsEngine/SphylElem.h"
#include "Materials/Material.h"
#include "Chaos/TriangleMeshImplicitObject.h"
#include "Serialization/MemoryWriter.h"
#include "UObject/Package.h"

namespace
{
void UInt(FSHA1& Hash,uint32 Value)
{
    uint8 Bytes[4];for (int32 I=0;I<4;++I) Bytes[I]=uint8(Value>>(I*8));Hash.Update(Bytes,4);
}
bool Number(FSHA1& Hash,float Value,bool NumericZero=false)
{
    if (!FMath::IsFinite(Value)) return false;
    uint32 Bits;FMemory::Memcpy(&Bits,&Value,4);
    if (NumericZero && Value==0.f) Bits=0;
    UInt(Hash,Bits);return true;
}
bool TriangleHash(FSHA1& Hash,const FMeshDescription& D,FTriangleID T,int32 Slot,int32 Channels=-1,bool NumericZero=false)
{
    FStaticMeshConstAttributes A(D);auto P=A.GetVertexPositions();auto N=A.GetVertexInstanceNormals();
    auto C=A.GetVertexInstanceColors();auto UV=A.GetVertexInstanceUVs();
    if (!P.IsValid() || !N.IsValid() || !C.IsValid() || !UV.IsValid() || D.GetTriangleVertexInstances(T).Num()!=3) return false;
    if (Channels<0) Channels=UV.GetNumChannels();
    if (UV.GetNumChannels()<1 || Channels<1 || Channels>8) return false;
    UInt(Hash,Channels);UInt(Hash,Slot);
    for (auto I:D.GetTriangleVertexInstances(T))
    {
        const auto V=P[D.GetVertexInstanceVertex(I)];const auto Normal=N[I];const auto Colour=C[I];
        for (float F:{V.X,V.Y,V.Z,Normal.X,Normal.Y,Normal.Z,Colour.X,Colour.Y,Colour.Z,Colour.W})
            if (!Number(Hash,F,NumericZero)) return false;
        for (int32 Channel=0;Channel<Channels;++Channel)
        { const auto U=UV.Get(I,Channel<UV.GetNumChannels()?Channel:0);if (!Number(Hash,U.X,NumericZero) || !Number(Hash,U.Y,NumericZero)) return false; }
    }
    return true;
}
FString FinishHash(FSHA1& Hash)
{ Hash.Final();uint8 Digest[20];Hash.GetHash(Digest);return BytesToHex(Digest,20); }
FString TriangleKey(const FMeshDescription& D,FTriangleID T,int32 Slot,int32 Channels=-1)
{ FSHA1 Hash;return TriangleHash(Hash,D,T,Slot,Channels,true)?FinishHash(Hash):FString{}; }
FString GeometryHash(const FMeshDescription& D)
{
    FStaticMeshConstAttributes A(D);auto UV=A.GetVertexInstanceUVs();
    if (!UV.IsValid()) return {};
    FSHA1 Hash;UInt(Hash,UV.GetNumChannels());UInt(Hash,D.Triangles().Num());
    TMap<FPolygonGroupID,int32> Slots;int32 Slot=0;
    for (auto G:D.PolygonGroups().GetElementIDs()) Slots.Add(G,Slot++);
    for (auto T:D.Triangles().GetElementIDs())
        if (!TriangleHash(Hash,D,T,Slots.FindChecked(D.GetTrianglePolygonGroup(T)))) return {};
    return FinishHash(Hash);
}
void Initialize(FMeshDescription& D,const TArray<FStaticMaterial>& Materials,int32 Channels)
{
    FStaticMeshAttributes A(D);A.Register();A.GetVertexInstanceUVs().SetNumChannels(Channels);
    auto Names=A.GetPolygonGroupMaterialSlotNames();
    for (const auto& Material:Materials) Names[D.CreatePolygonGroup()]=Material.MaterialSlotName;
}
bool CopyTriangle(const FMeshDescription& Input,FTriangleID Triangle,int32 Slot,FMeshDescription& Output)
{
    FStaticMeshConstAttributes A(Input);FStaticMeshAttributes B(Output);
    auto P=A.GetVertexPositions();auto N=A.GetVertexInstanceNormals();auto C=A.GetVertexInstanceColors();auto UV=A.GetVertexInstanceUVs();
    auto OP=B.GetVertexPositions();auto ON=B.GetVertexInstanceNormals();auto OC=B.GetVertexInstanceColors();auto OU=B.GetVertexInstanceUVs();
    TArray<FVertexInstanceID> Corners;
    for (auto I:Input.GetTriangleVertexInstances(Triangle))
    {
        const auto V=Output.CreateVertex();OP[V]=P[Input.GetVertexInstanceVertex(I)];
        const auto Corner=Output.CreateVertexInstance(V);ON[Corner]=N[I];OC[Corner]=C[I];
        if (UV.GetNumChannels()<1 || OU.GetNumChannels()<1 || OU.GetNumChannels()>8) return false;
        for (int32 Channel=0;Channel<OU.GetNumChannels();++Channel)
            OU.Set(Corner,Channel,UV.Get(I,Channel<UV.GetNumChannels()?Channel:0));
        Corners.Add(Corner);
    }
    if (Corners.Num()!=3) return false;
    Output.CreateTriangle(FPolygonGroupID(Slot),Corners);return true;
}
bool IsLeaf(const FMeshDescription& D,FTriangleID Triangle,int32 Slot,int32 SourceSlots,
    const FString& Mode,const TSet<int32>& LeafSlots,double Height,bool& Leaf)
{
    if (Slot>=SourceSlots) { Leaf=true;return true; }
    if (Mode==TEXT("authored") || Mode==TEXT("authored-material"))
    {
        FStaticMeshConstAttributes A(D);auto UV=A.GetVertexInstanceUVs();
        if (UV.GetNumChannels()<=5) return false;
        for (auto I:D.GetTriangleVertexInstances(Triangle))
        { auto U=UV.Get(I,5);if (U.X!=3.f || FMath::Min(FMath::Abs(U.Y-73.125f),FMath::Abs(U.Y+72.125f))>.01f) return false; }
        Leaf=Mode==TEXT("authored") || LeafSlots.Contains(Slot);return true;
    }
    FStaticMeshConstAttributes A(D);const auto Corners=D.GetTriangleVertexInstances(Triangle);
    if (Corners.Num()!=3) return false;
    if (Mode==TEXT("roles"))
    {
        auto UV=A.GetVertexInstanceUVs();if (UV.GetNumChannels()<=5) return false;
        int32 Role=-1;
        for (auto I:Corners)
        {
            const auto U=UV.Get(I,5);
            if (FMath::Min(FMath::Abs(U.Y-73.125f),FMath::Abs(U.Y+72.125f))>.01f ||
                (U.X!=0.f && U.X!=1.f && U.X!=2.f)) return false;
            const int32 Value=int32(U.X);if (Role>=0 && Role!=Value) return false;Role=Value;
        }
        Leaf=Role>0;return true;
    }
    if (Mode==TEXT("material")) { Leaf=LeafSlots.Contains(Slot);return true; }
    if (Mode==TEXT("height"))
    {
        auto P=A.GetVertexPositions();double Z=0.;for (auto I:Corners) Z+=double(P[D.GetVertexInstanceVertex(I)].Z);
        Leaf=Z/3.>Height;return true;
    }
    if (Mode==TEXT("palette"))
    {
        auto C=A.GetVertexInstanceColors();FVector3d Colour=FVector3d::ZeroVector;
        for (auto I:Corners) { auto V=C[I];Colour+=FVector3d(V.X,V.Y,V.Z); }Colour/=3.;
        for (int32 I=0;I<3;++I) Colour[I]=Colour[I]<=.04045?Colour[I]/12.92:FMath::Pow((Colour[I]+.055)/1.055,2.4);
        Leaf=Colour.X>.4 && Colour.Y>.08 && Colour.Z<.07 && Colour.X>Colour.Y*1.2;return true;
    }
    return false;
}
bool Split(UStaticMesh* Input,int32 Level,UStaticMesh* Source,int32 SourceLevel,
    const FString& Mode,const TSet<int32>& LeafSlots,FMeshDescription& Canopy,FMeshDescription* Rigid,int32& RigidCount,
    FMeshDescription* AuthoredLeaves=nullptr)
{
    const auto Refuse=[&](const TCHAR* Reason)
    { UE_LOG(LogTemp,Warning,TEXT("FOLIAGE RESIDENCY split refused source=%s sourceLOD=%d input=%s inputLOD=%d mode=%s reason=%s"),
        *Source->GetPathName(),SourceLevel,*Input->GetPathName(),Level,*Mode,Reason);return false; };
    const FMeshDescription* D=Input->GetMeshDescription(Level);
    if (!D || GeometryHash(*D).IsEmpty()) return Refuse(TEXT("invalid prepared description"));
    FStaticMeshConstAttributes A(*D);auto UV=A.GetVertexInstanceUVs();auto Names=A.GetPolygonGroupMaterialSlotNames();
    const FMeshDescription* Original=Source->GetMeshDescription(SourceLevel);
    FMeshDescription RenderOriginal;
    if (!Original && Source->GetRenderData() && Source->GetRenderData()->LODResources.IsValidIndex(SourceLevel))
    {
        // Same source-read path as the certified ExportSource: engine-reduced
        // LODs have render resources without stored source descriptions.
        Source->ExportStaticMeshLOD(Source->GetRenderData()->LODResources[SourceLevel],RenderOriginal);
        Original=&RenderOriginal;
        UE_LOG(LogTemp,Display,TEXT("FOLIAGE RESIDENCY source render readback: %s LOD%d"),*Source->GetPathName(),SourceLevel);
    }
    if (!Original || GeometryHash(*Original).IsEmpty()) return Refuse(TEXT("invalid source description/render LOD"));
    FStaticMeshConstAttributes SA(*Original);auto SP=SA.GetVertexPositions();
    FBox3f Bounds(ForceInit);for (auto T:Original->Triangles().GetElementIDs())
        for (auto I:Original->GetTriangleVertexInstances(T)) Bounds+=SP[Original->GetVertexInstanceVertex(I)];
    if (!Bounds.IsValid) return Refuse(TEXT("empty source bounds"));
    TMap<FPolygonGroupID,int32> OriginalSlots;int32 Index=0;
    auto OriginalNames=SA.GetPolygonGroupMaterialSlotNames();if (!OriginalNames.IsValid()) return Refuse(TEXT("missing source group names"));
    for (auto G:Original->PolygonGroups().GetElementIDs())
    {
        const FName Name=OriginalNames[G];int32 Slot=Source->GetMaterialIndex(Name);
        if (Slot==INDEX_NONE) for (int32 I=0;I<Source->GetStaticMaterials().Num();++I)
            if (Source->GetStaticMaterials()[I].ImportedMaterialSlotName==Name) { Slot=I;break; }
        if (!Source->GetStaticMaterials().IsValidIndex(Slot)) return Refuse(TEXT("unbound source material group"));OriginalSlots.Add(G,Slot);
    }
    if (AuthoredLeaves) Initialize(*AuthoredLeaves,Input->GetStaticMaterials(),UV.GetNumChannels());
    TMap<FString,int32> Remaining;RigidCount=0;
    for (auto T:Original->Triangles().GetElementIDs())
    {
        const int32 Slot=OriginalSlots.FindChecked(Original->GetTrianglePolygonGroup(T));bool Leaf;
        if (!IsLeaf(*Original,T,Slot,Source->GetStaticMaterials().Num(),Mode,LeafSlots,
            double(Bounds.Min.Z)+(double(Bounds.Max.Z)-double(Bounds.Min.Z))*.4,Leaf)) return Refuse(TEXT("invalid source face classification"));
        if (!Leaf) { const FString Key=TriangleKey(*Original,T,Slot,UV.GetNumChannels());if (Key.IsEmpty()) return Refuse(TEXT("invalid rigid corner key"));++Remaining.FindOrAdd(Key);++RigidCount; }
        else if (AuthoredLeaves && !CopyTriangle(*Original,T,Slot,*AuthoredLeaves))
            return Refuse(TEXT("authored leaf corner copy failed"));
    }
    if (!Names.IsValid() || UV.GetNumChannels()<1 || UV.GetNumChannels()>8 ||
        D->PolygonGroups().Num()!=Input->GetStaticMaterials().Num()) return Refuse(TEXT("prepared UV/group/material table mismatch"));
    Initialize(Canopy,Input->GetStaticMaterials(),UV.GetNumChannels());
    if (Rigid) Initialize(*Rigid,Source->GetStaticMaterials(),UV.GetNumChannels());
    TMap<FPolygonGroupID,int32> Slots;Index=0;
    for (auto G:D->PolygonGroups().GetElementIDs())
    { if (Names[G]!=Input->GetStaticMaterials()[Index].MaterialSlotName) return Refuse(TEXT("prepared ordered group names mismatch"));Slots.Add(G,Index++); }
    for (auto Triangle:D->Triangles().GetElementIDs())
    {
        const int32 Slot=Slots.FindChecked(D->GetTrianglePolygonGroup(Triangle));
        int32* Count=Remaining.Find(TriangleKey(*D,Triangle,Slot));
        if (Count && *Count>0)
        { --*Count;if (Rigid && !CopyTriangle(*D,Triangle,Slot,*Rigid)) return Refuse(TEXT("rigid corner copy failed")); }
        else if (!CopyTriangle(*D,Triangle,Slot,Canopy)) return Refuse(TEXT("canopy corner copy failed"));
    }
    for (const auto& Pair:Remaining) if (Pair.Value) return Refuse(TEXT("missing exact rigid corner multiplicity"));
    Input->ClearMeshDescription(Level);Source->ClearMeshDescription(SourceLevel);
    return Canopy.Triangles().Num()>0 || Refuse(TEXT("empty canopy"));
}


// Reuse the original's complete authored chain, including its far material slots.
// Geometry comes from the same stored-description/render-LOD path as ExportSource.
bool OriginalParts(UStaticMesh* Source,int32 Level,const FString& Mode,const TSet<int32>& LeafSlots,
    const TArray<FStaticMaterial>& Materials,int32 Channels,FMeshDescription& Leaves,FMeshDescription* Rigid)
{
    const auto Refuse=[&](const TCHAR* Reason)
    { UE_LOG(LogTemp,Warning,TEXT("FOLIAGE RESIDENCY authored source refused %s LOD%d: %s"),*Source->GetPathName(),Level,Reason);return false; };
    const FMeshDescription* Original=Source->GetMeshDescription(Level);FMeshDescription RenderOriginal;
    if (!Original && Source->GetRenderData() && Source->GetRenderData()->LODResources.IsValidIndex(Level))
    { Source->ExportStaticMeshLOD(Source->GetRenderData()->LODResources[Level],RenderOriginal);Original=&RenderOriginal; }
    if (!Original || GeometryHash(*Original).IsEmpty()) return Refuse(TEXT("invalid source description/render LOD"));
    FStaticMeshConstAttributes A(*Original);auto P=A.GetVertexPositions();auto Names=A.GetPolygonGroupMaterialSlotNames();
    const auto OriginalUV=A.GetVertexInstanceUVs();
    if (!OriginalUV.IsValid() || OriginalUV.GetNumChannels()<1 || OriginalUV.GetNumChannels()>8) return Refuse(TEXT("invalid source UV channels"));
    // A far authored material may use more channels than LOD0. Preserve those
    // channels; only missing receiving channels use the reviewed UV0 fallback.
    Channels=FMath::Max(Channels,OriginalUV.GetNumChannels());
    if (!Names.IsValid() || Channels<1 || Channels>8 || Materials.Num()!=Source->GetStaticMaterials().Num())
        return Refuse(TEXT("invalid source material/channel table"));
    FBox3f Bounds(ForceInit);for (auto T:Original->Triangles().GetElementIDs())
        for (auto I:Original->GetTriangleVertexInstances(T)) Bounds+=P[Original->GetVertexInstanceVertex(I)];
    if (!Bounds.IsValid) return Refuse(TEXT("empty source bounds"));
    TMap<FPolygonGroupID,int32> Slots;
    for (auto G:Original->PolygonGroups().GetElementIDs())
    {
        const FName Name=Names[G];int32 Slot=Source->GetMaterialIndex(Name);
        if (Slot==INDEX_NONE) for (int32 I=0;I<Source->GetStaticMaterials().Num();++I)
            if (Source->GetStaticMaterials()[I].ImportedMaterialSlotName==Name) { Slot=I;break; }
        if (!Materials.IsValidIndex(Slot)) return Refuse(TEXT("unbound source material group"));Slots.Add(G,Slot);
    }
    Initialize(Leaves,Materials,Channels);if (Rigid) Initialize(*Rigid,Source->GetStaticMaterials(),Channels);
    for (auto T:Original->Triangles().GetElementIDs())
    {
        const int32 Slot=Slots.FindChecked(Original->GetTrianglePolygonGroup(T));bool Leaf;
        if (!IsLeaf(*Original,T,Slot,Source->GetStaticMaterials().Num(),Mode,LeafSlots,
            double(Bounds.Min.Z)+(double(Bounds.Max.Z)-double(Bounds.Min.Z))*.4,Leaf)) return Refuse(TEXT("invalid source face classification"));
        if (Leaf && !CopyTriangle(*Original,T,Slot,Leaves)) return Refuse(TEXT("leaf corner copy"));
        if (!Leaf && Rigid && !CopyTriangle(*Original,T,Slot,*Rigid)) return Refuse(TEXT("rigid corner copy"));
    }
    // Empty distant leaves are intentional only when this exact source has none.
    // Polygon groups are real material bindings even when no face survives.
    // UE IsEmpty checks every element container; retain this table so an empty
    // face set is a custom LOD rather than an absent/generated LOD. Build still
    // requires an actual zero-triangle render resource, including after reload.
    if (Leaves.IsEmpty() || (Rigid && Rigid->IsEmpty())) return Refuse(TEXT("lost material groups"));
    Source->ClearMeshDescription(Level);return Level>0 || Leaves.Triangles().Num()>0;
}

struct FLeafPart
{
    int32 Slot=0;
    bool Tagged=false;
    FVector2f Role=FVector2f::ZeroVector;
    FMeshDescription Mesh;
};

bool LeafRole(const FMeshDescription& D,FTriangleID T,bool& Tagged,FVector2f& Role)
{
    const auto UV=FStaticMeshConstAttributes(D).GetVertexInstanceUVs();
    Tagged=false;Role=FVector2f::ZeroVector;
    if (UV.GetNumChannels()<=5) return true;
    const auto Corners=D.GetTriangleVertexInstances(T);
    if (Corners.Num()!=3) return false;
    int32 Tags=0;
    for (auto I:Corners)
    {
        const auto V=UV.Get(I,5);
        if (FMath::Min(FMath::Abs(V.Y-73.125f),FMath::Abs(V.Y+72.125f))>.01f) continue;
        if (V.X!=1.f && V.X!=2.f && V.X!=3.f) return false;
        if (Tags && V!=Role) return false;
        Role=V;++Tags;
    }
    if (Tags && Tags!=3) return false;
    Tagged=Tags==3;return true;
}

bool LeafLevels(const FMeshDescription& Near,const TArray<FStaticMaterial>& Materials,
    TArray<FMeshDescription>& Levels,FString& Version)
{
    const auto Refuse=[](const TCHAR* Reason)
    { UE_LOG(LogTemp,Error,TEXT("FOLIAGE RESIDENCY leaf LOD refusal: %s"),Reason);return false; };
    if (Near.Triangles().Num()<1 || GeometryHash(Near).IsEmpty()) return Refuse(TEXT("invalid exact authored leaves"));
    auto& Manager=FModuleManager::LoadModuleChecked<IMeshReductionManagerModule>(TEXT("MeshReductionInterface"));
    IMeshReduction* Reducer=Manager.GetStaticMeshReductionInterface();
    if (!Reducer || !Reducer->IsSupported() || Reducer->GetVersionString().IsEmpty()) return Refuse(TEXT("unsupported installed reducer"));
    Version=Reducer->GetVersionString();
    const int32 Channels=FStaticMeshConstAttributes(Near).GetVertexInstanceUVs().GetNumChannels();
    TArray<FLeafPart> Parts;TMap<FString,int32> PartIndices;
    for (auto T:Near.Triangles().GetElementIDs())
    {
        const int32 Slot=Near.GetTrianglePolygonGroup(T).GetValue();bool Tagged;FVector2f Role;
        if (!Materials.IsValidIndex(Slot) || !LeafRole(Near,T,Tagged,Role)) return Refuse(TEXT("source material/role seam"));
        const FString Key=FString::Printf(TEXT("%d/%d/%.9g/%.9g"),Slot,int32(Tagged),double(Role.X),double(Role.Y));
        int32* Found=PartIndices.Find(Key);
        if (!Found)
        {
            const int32 Index=Parts.AddDefaulted();auto& Part=Parts[Index];Part.Slot=Slot;Part.Tagged=Tagged;Part.Role=Role;
            Initialize(Part.Mesh,Materials,Channels);PartIndices.Add(Key,Index);Found=PartIndices.Find(Key);
        }
        if (!CopyTriangle(Near,T,Slot,Parts[*Found].Mesh)) return Refuse(TEXT("leaf partition corner copy"));
    }
    // Retain the complete source wrapper table, but do not leave unused hard
    // references to the former opaque CanopyNear/CanopyFar materials.
    FMeshDescription Exact;Initialize(Exact,Materials,Channels);
    for (auto T:Near.Triangles().GetElementIDs())
        if (!CopyTriangle(Near,T,Near.GetTrianglePolygonGroup(T).GetValue(),Exact)) return Refuse(TEXT("exact leaf repack"));
    if (GeometryHash(Exact)!=GeometryHash(Near)) return Refuse(TEXT("changed exact leaf corner multiset"));
    Levels.Reset();Levels.Add(MoveTemp(Exact));
    // Reduce each material/categorical-role island separately. A role channel is
    // a label, not a continuous UV: the reducer must never blend different labels.
    for (float Ratio:{.5f,.25f,.1f})
    {
        FMeshDescription Result;Initialize(Result,Materials,Channels);
        for (const auto& Part:Parts)
        {
            FMeshDescription Reduced;FStaticMeshAttributes(Reduced).Register();
            FMeshReductionSettings Settings;Settings.PercentTriangles=Ratio;Settings.BaseLODModel=0;
            Settings.TerminationCriterion=EStaticMeshReductionTerimationCriterion::Triangles;
            Settings.WeldingThreshold=0.f;Settings.bRecalculateNormals=false;
            Settings.bGenerateUniqueLightmapUVs=false;Settings.bVisibilityAided=false;Settings.bCullOccluded=false;
            Settings.SilhouetteImportance=EMeshFeatureImportance::Highest;
            Settings.TextureImportance=EMeshFeatureImportance::Highest;
            Settings.ShadingImportance=EMeshFeatureImportance::High;
            Settings.VertexColorImportance=EMeshFeatureImportance::Highest;
            FOverlappingCorners Overlap;FStaticMeshOperations::FindOverlappingCorners(Overlap,Part.Mesh,0.f);
            float Deviation=0.f;
            Reducer->ReduceMeshDescription(Reduced,Deviation,Part.Mesh,Overlap,Settings);
            if (!FMath::IsFinite(Deviation) || Deviation<0.f || Reduced.Triangles().Num()<1 ||
                Reduced.Triangles().Num()>Part.Mesh.Triangles().Num() || GeometryHash(Reduced).IsEmpty())
                return Refuse(TEXT("invalid reduced geometry/count/deviation"));
            FStaticMeshAttributes A(Reduced);auto UV=A.GetVertexInstanceUVs();auto Names=A.GetPolygonGroupMaterialSlotNames();
            if (UV.GetNumChannels()!=Channels) return Refuse(TEXT("lost reduced UV channel"));
            for (auto T:Reduced.Triangles().GetElementIDs())
            {
                if (Names[Reduced.GetTrianglePolygonGroup(T)]!=Materials[Part.Slot].MaterialSlotName)
                    return Refuse(TEXT("changed reduced material binding"));
                if (Part.Tagged) for (auto I:Reduced.GetTriangleVertexInstances(T))
                {
                    const auto Value=UV.Get(I,5);
                    // Only numerical roundoff on a proven constant categorical
                    // island may be restored. Changed labels/markers refuse.
                    if (FMath::Abs(Value.X-Part.Role.X)>1.e-5f || FMath::Abs(Value.Y-Part.Role.Y)>1.e-5f)
                        return Refuse(TEXT("interpolated categorical role/opacity seam"));
                    UV.Set(I,5,Part.Role);
                }
                if (!CopyTriangle(Reduced,T,Part.Slot,Result)) return Refuse(TEXT("reduced leaf corner copy"));
            }
        }
        if (Result.Triangles().Num()>Levels.Last().Triangles().Num()) return Refuse(TEXT("nonmonotonic leaf LODs"));
        UE_LOG(LogTemp,Display,TEXT("FOLIAGE RESIDENCY authored leaf LOD ratio=%.2f triangles=%d source=%d reducer=%s"),
            double(Ratio),Result.Triangles().Num(),Near.Triangles().Num(),*Version);
        Levels.Add(MoveTemp(Result));
    }
    return Levels.Num()==4 && GeometryHash(Levels[0])==GeometryHash(Near);
}
enum class ECollision { None, SimpleTrunk, Rigid };
FMeshBuildSettings BuildSettings()
{
    FMeshBuildSettings B;B.bRecomputeNormals=false;B.bRecomputeTangents=true;
    B.bRemoveDegenerates=false;B.bGenerateLightmapUVs=false;B.bUseFullPrecisionUVs=true;
    B.DistanceFieldResolutionScale=0;B.MaxLumenMeshCards=0;return B;
}
UStaticMesh* Build(const FString& Destination,TArray<FMeshDescription>& Descriptions,
    const TArray<FStaticMaterial>& Materials,const TArray<float>& Screens,ECollision Collision,
    const FKAggregateGeom& Trunk,const UBodySetup* OriginalBody=nullptr,UStaticMesh* CollisionProxy=nullptr)
{
    const FString Name=FPackageName::GetLongPackageAssetName(Destination);
    UPackage* Package=CreatePackage(*Destination);Package->FullyLoad();
    UStaticMesh* Mesh=FindObject<UStaticMesh>(Package,*Name);
    if (!Mesh)
    { Mesh=NewObject<UStaticMesh>(Package,*Name,RF_Public|RF_Standalone);FAssetRegistryModule::AssetCreated(Mesh); }
    FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    TArray<FString> Expected;TArray<const FMeshDescription*> Pointers;
    bool Current=Mesh->GetNumSourceModels()==Descriptions.Num() && Mesh->GetStaticMaterials()==Materials &&
        !Mesh->GetAutoComputeLODScreenSize() && !Mesh->bGenerateMeshDistanceField && !Mesh->bAllowCPUAccess &&
        !Mesh->GetNaniteSettings().bEnabled;
    for (int32 L=0;L<Descriptions.Num();++L)
    {
        const FString Hash=GeometryHash(Descriptions[L]);if (Hash.IsEmpty()) return nullptr;Expected.Add(Hash);
        const auto* Existing=Current?Mesh->GetMeshDescription(L):nullptr;
        if (!Existing || GeometryHash(*Existing)!=Hash) Current=false;
        if (Current)
        {
            const auto& Model=Mesh->GetSourceModel(L);FMeshReductionSettings Reduction;Reduction.BaseLODModel=L;
            Current=Model.ScreenSize.Default==Screens[L] && Model.BuildSettings==BuildSettings() &&
                Model.ReductionSettings==Reduction;
        }
    }
    Mesh->Modify();Mesh->GetStaticMaterials()=Materials;Mesh->SetNumSourceModels(Descriptions.Num());
    for (int32 L=0;L<Descriptions.Num();++L)
    {
        Pointers.Add(&Descriptions[L]);auto& Model=Mesh->GetSourceModel(L);
        Model.ReductionSettings=FMeshReductionSettings{};Model.ReductionSettings.BaseLODModel=L;
        Model.BuildSettings=BuildSettings();Model.ScreenSize.Default=Screens[L];
    }
    Mesh->SetAutoComputeLODScreenSize(false);Mesh->bGenerateMeshDistanceField=false;Mesh->bAllowCPUAccess=false;Mesh->GetNaniteSettings().bEnabled=false;
    Mesh->ComplexCollisionMesh=CollisionProxy;Mesh->MarkAsNotHavingNavigationData();Mesh->CreateBodySetup();
    auto* Body=Mesh->GetBodySetup();if (!Body || Body->GetOuter()!=Mesh || Body->CurrentCookHelper) return nullptr;
    Body->ClearPhysicsMeshes();Body->AggGeom.EmptyElements();Body->BuildScale3D=FVector::OneVector;
    Body->bNeverNeedsCookedCollisionData=Collision==ECollision::None;
    if (OriginalBody && Collision!=ECollision::None)
    {
        Body->bDoubleSidedGeometry=OriginalBody->bDoubleSidedGeometry;
        Body->PhysMaterial=OriginalBody->PhysMaterial;Body->WalkableSlopeOverride=OriginalBody->WalkableSlopeOverride;
    }
    Body->CollisionTraceFlag=Collision==ECollision::Rigid?CTF_UseComplexAsSimple:CTF_UseSimpleAsComplex;
    if (Collision==ECollision::SimpleTrunk)
    {
        Body->AggGeom=Trunk;Body->BuildScale3D=FVector::OneVector;
    }
    UStaticMesh::FBuildMeshDescriptionsParams Params;
    if (!Current && !Mesh->BuildFromMeshDescriptions(Pointers,Params)) return nullptr;
    UE_LOG(LogTemp,Display,TEXT("FOLIAGE RESIDENCY native %s: %s"),Current?TEXT("readback"):TEXT("build"),*Destination);
    Mesh->SetLightMapCoordinateIndex(0);FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    // Fresh native readback proves the emitted corner stream, rather than counts alone.
    if (!Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.Num()!=Descriptions.Num()) return nullptr;
    for (int32 L=0;L<Descriptions.Num();++L)
    {
        const auto* D=Mesh->GetMeshDescription(L);
        if (!D || GeometryHash(*D)!=Expected[L] ||
            Mesh->GetRenderData()->LODResources[L].GetNumTriangles()!=uint32(Descriptions[L].Triangles().Num()) ||
            Mesh->GetRenderData()->ScreenSize[L].GetValue()!=Screens[L]) return nullptr;
    }
    if (Mesh->GetNavCollision() || Mesh->ComplexCollisionMesh!=CollisionProxy || Body!=Mesh->GetBodySetup() ||
        Body->BuildScale3D!=FVector::OneVector || Body->bNeverNeedsCookedCollisionData!=(Collision==ECollision::None) ||
        Body->CollisionTraceFlag!=(Collision==ECollision::Rigid?CTF_UseComplexAsSimple:CTF_UseSimpleAsComplex)) return nullptr;
    if (Collision==ECollision::None)
    { Body->ClearPhysicsMeshes();if (!Body->TriMeshGeometries.IsEmpty() || Body->AggGeom.GetElementCount()) return nullptr; }
    else
    {
        Mesh->LODForCollision=0;
        for (int32 L=0;L<Mesh->GetRenderData()->LODResources.Num();++L)
            for (int32 Section=0;Section<Mesh->GetRenderData()->LODResources[L].Sections.Num();++Section)
            { auto Info=Mesh->GetSectionInfoMap().Get(L,Section);Info.bEnableCollision=Collision==ECollision::Rigid;
              Mesh->GetSectionInfoMap().Set(L,Section,Info); }
        Body->InvalidatePhysicsData();Body->CreatePhysicsMeshes();
        if (!Body->bCreatedPhysicsMeshes || Body->bFailedToCreatePhysicsMeshes ||
            (Collision==ECollision::Rigid && Body->TriMeshGeometries.IsEmpty()) ||
            (Collision==ECollision::SimpleTrunk && Body->AggGeom.GetElementCount()==0)) return nullptr;
        if (Collision==ECollision::Rigid)
        {
            int64 Triangles=0;for (const auto& Geometry:Body->TriMeshGeometries)
            { if (!Geometry) return nullptr;Triangles+=Geometry->Elements().GetNumTriangles(); }
            if (Triangles!=(CollisionProxy?CollisionProxy->GetNumTriangles(0):Descriptions[0].Triangles().Num()) || Body->AggGeom.GetElementCount()!=0) return nullptr;
        }
        else
        {
            // Reflected authored shape data excludes transient Chaos pointers.
            TArray<uint8> Actual,Requested;FMemoryWriter A(Actual),B(Requested);
            FKAggregateGeom::StaticStruct()->SerializeItem(A,&Body->AggGeom,nullptr);
            FKAggregateGeom::StaticStruct()->SerializeItem(B,const_cast<FKAggregateGeom*>(&Trunk),nullptr);
            if (A.IsError() || B.IsError() || Actual!=Requested || !Body->TriMeshGeometries.IsEmpty()) return nullptr;
        }
    }
    Mesh->MarkPackageDirty();return Mesh;
}
}
#endif

FString UYorimichiFoliageResidencyBuilder::Compact(UStaticMesh* Source,UStaticMesh* Prepared,UStaticMesh* PreparedShadow,
    const FString& Classification,const TArray<int32>& LeafSlots,int32 ExpectedRigidTriangles,
    bool SimpleTrunk,const TArray<int32>& SourceLODs,const TArray<float>& TrunkBounds,
    const FString& Directory,UMaterialInterface* NearInteraction,bool Passable)
{
#if WITH_EDITOR
    if (!IsInGameThread() || !Source || !Prepared || !PreparedShadow || (ExpectedRigidTriangles<0 && !(ExpectedRigidTriangles==-1 && Classification==TEXT("authored-material"))) ||
        !Directory.StartsWith(TEXT("/Game/FoliageResident/")) || !FPackageName::IsValidLongPackageName(Directory) ||
        Prepared->GetNumSourceModels()!=4 || PreparedShadow->GetNumSourceModels()!=1) return {};
    if (Source==Prepared || Source==PreparedShadow || Prepared==PreparedShadow ||
        (SimpleTrunk && (Classification==TEXT("authored") || Passable))) return {};
    if (SourceLODs.Num()!=4) return {};
    for (int32 L:SourceLODs) if (L<0 || L>=Source->GetNumSourceModels()) return {};
    FStaticMeshCompilingManager::Get().FinishCompilation({Source,Prepared,PreparedShadow});
    TSet<int32> Slots;for (int32 Slot:LeafSlots) { if (!Source->GetStaticMaterials().IsValidIndex(Slot)) return {};Slots.Add(Slot); }
    bool TrunkLODs=false;for (int32 L:SourceLODs) if (SimpleTrunk && L!=SourceLODs[0]) TrunkLODs=true;
    TArray<FMeshDescription> Canopies;Canopies.SetNum(4);TArray<FMeshDescription> Rigid;Rigid.SetNum(TrunkLODs?4:1);
    TArray<float> Screens;TArray<int32> Counts;int32 RigidCount=0;FMeshDescription AuthoredNear;
    for (int32 L=0;L<4;++L)
    {
        int32 Removed=0;if (!Split(Prepared,L,Source,SourceLODs[L],Classification,Slots,Canopies[L],TrunkLODs?&Rigid[L]:(L==0?&Rigid[0]:nullptr),Removed,L==0?&AuthoredNear:nullptr)) return {};
        if (L==0) RigidCount=Removed;Counts.Add(Canopies[L].Triangles().Num());
        Screens.Add(Prepared->GetSourceModel(L).ScreenSize.Default);
    }
    if (ExpectedRigidTriangles>=0 && RigidCount!=ExpectedRigidTriangles)
    { UE_LOG(LogTemp,Error,TEXT("FOLIAGE RESIDENCY rigid count mismatch %s expected=%d actual=%d"),*Source->GetPathName(),ExpectedRigidTriangles,RigidCount);return {}; }
    TArray<FMeshDescription> Shadow;Shadow.SetNum(1);int32 Removed=0;
    if (!Split(PreparedShadow,0,Source,SourceLODs.Last(),Classification,Slots,Shadow[0],nullptr,Removed)) return {};
    TArray<FStaticMaterial> CanopyMaterials=Prepared->GetStaticMaterials();
    if (CanopyMaterials.Num()<Source->GetStaticMaterials().Num()) return {};
    CanopyMaterials.SetNum(Source->GetStaticMaterials().Num());
    // Authored leaves use the original opacity/texture/wind wrappers; the old
    // volume material is intentionally unused by this representation.
    static_cast<void>(NearInteraction);
    FString ReducerVersion;TArray<float> RigidScreens=Screens;TArray<int32> LeafSources,OriginalLeafCounts;
    const auto* Render=Source->GetRenderData();const int32 SourceCount=Source->GetNumSourceModels();
    if (!Render || SourceCount<1 || SourceCount>8 || Render->LODResources.Num()!=SourceCount) return {};
    if (SourceCount>1)
    {
        const int32 Channels=FStaticMeshConstAttributes(AuthoredNear).GetVertexInstanceUVs().GetNumChannels();
        Canopies.Reset();Canopies.SetNum(SourceCount);Screens.Reset();
        if (SimpleTrunk && RigidCount) { Rigid.Reset();Rigid.SetNum(SourceCount); }
        for (int32 L=0;L<SourceCount;++L)
        {
            const float Screen=Render->ScreenSize[L].GetValue();
            if (!FMath::IsFinite(Screen) || Screen<0.f || Screen>1.f || (L==0 && Screen<=0.f) ||
                (L>0 && Screen>Screens.Last())) return {};
            if (!OriginalParts(Source,L,Classification,Slots,CanopyMaterials,Channels,Canopies[L],
                SimpleTrunk && RigidCount?&Rigid[L]:nullptr)) return {};
            if (L==0 && GeometryHash(Canopies[L])!=GeometryHash(AuthoredNear)) return {};
            for (auto T:Canopies[L].Triangles().GetElementIDs())
            { bool Tagged;FVector2f Role;if (!LeafRole(Canopies[L],T,Tagged,Role)) return {}; }
            Screens.Add(Screen);LeafSources.Add(L);OriginalLeafCounts.Add(Canopies[L].Triangles().Num());
        }
        if (SimpleTrunk && RigidCount) { TrunkLODs=true;RigidScreens=Screens; }
        ReducerVersion=TEXT("authored-source-lods");
    }
    else
    {
        if (!LeafLevels(AuthoredNear,CanopyMaterials,Canopies,ReducerVersion)) return {};
        LeafSources.Init(0,Canopies.Num());OriginalLeafCounts.Add(AuthoredNear.Triangles().Num());
    }
    Counts.Reset();for (const auto& D:Canopies) Counts.Add(D.Triangles().Num());
    FKAggregateGeom Trunk;
    if (SimpleTrunk)
    {
        if (TrunkBounds.Num()==7)
        {
            for (float Value:TrunkBounds) if (!FMath::IsFinite(Value)) return {};
            const FVector A(TrunkBounds[1],TrunkBounds[2],TrunkBounds[3]);
            const FVector B(TrunkBounds[4],TrunkBounds[5],TrunkBounds[6]);
            if (TrunkBounds[0]<=0.f || (B-A).Size()<1.f) return {};
            FKSphylElem Shape;Shape.Center=(A+B)*.5;Shape.Radius=TrunkBounds[0];
            Shape.Length=(B-A).Size();Shape.Rotation=FQuat::FindBetweenNormals(FVector::UpVector,(B-A).GetSafeNormal()).Rotator();
            Trunk.SphylElems.Add(Shape);
        }
        else
        {
            // A standalone unmanifested tree may use only the lower classified trunk,
            // never the crown or a mixed district. Refuse ambiguous/broad shapes.
            if (!TrunkBounds.IsEmpty() || Rigid[0].Triangles().Num()==0) return {};
            FStaticMeshConstAttributes A(Rigid[0]);auto P=A.GetVertexPositions();FBox3f Whole(ForceInit);
            for (auto V:Rigid[0].Vertices().GetElementIDs()) Whole+=P[V];
            FBox3f Low(ForceInit);const float Top=Whole.Min.Z+(Whole.Max.Z-Whole.Min.Z)*.2f;
            for (auto V:Rigid[0].Vertices().GetElementIDs()) if (P[V].Z<=Top) Low+=P[V];
            const FVector3f Extent=Low.GetExtent();const float Radius=FMath::Max(Extent.X,Extent.Y);
            if (!Low.IsValid || Radius<1.f || Radius>(Whole.Max.Z-Whole.Min.Z)*.15f) return {};
            FKSphylElem Shape;Shape.Center=FVector(Low.GetCenter());Shape.Center.Z=(Whole.Min.Z+Top)*.5f;Shape.Radius=Radius;
            Shape.Length=FMath::Max(1.f,Top-Whole.Min.Z);Trunk.SphylElems.Add(Shape);
        }
    }
    const FString Base=Directory/Source->GetName();
    UStaticMesh* Carrier=nullptr;
    if (RigidCount) Carrier=Build(Base,Rigid,Source->GetStaticMaterials(),TrunkLODs?RigidScreens:TArray<float>{1.f},Passable?ECollision::None:(SimpleTrunk?ECollision::SimpleTrunk:ECollision::Rigid),Trunk,Source->GetBodySetup());
    UStaticMesh* Proxy=Classification==TEXT("authored")?Source->ComplexCollisionMesh.Get():nullptr;
    if (Proxy && (Proxy==Source || Proxy==Prepared || Proxy==PreparedShadow || Proxy->ComplexCollisionMesh)) return {};
    if (Proxy) FStaticMeshCompilingManager::Get().FinishCompilation({Proxy});
    auto* Canopy=Build(Base+TEXT("_Canopy"),Canopies,CanopyMaterials,Screens,
        Proxy?ECollision::Rigid:(SimpleTrunk && !RigidCount?ECollision::SimpleTrunk:ECollision::None),Trunk,Source->GetBodySetup(),Proxy);
    auto* ShadowMesh=Build(Base+TEXT("_Shadow"),Shadow,PreparedShadow->GetStaticMaterials(),{1.f},ECollision::None,Trunk);
    if ((RigidCount && !Carrier) || !Canopy || !ShadowMesh) return {};
    auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("rigid"),Carrier?Carrier->GetPathName():TEXT(""));
    Row->SetNumberField(TEXT("rigid_triangles"),RigidCount);
    TArray<TSharedPtr<FJsonValue>> RigidCounts;if (Carrier) for (const auto& D:Rigid)
        RigidCounts.Add(MakeShared<FJsonValueNumber>(D.Triangles().Num()));
    TArray<TSharedPtr<FJsonValue>> LeafScreens,LeafSourceRows,SourceLeafRows;
    for (float Value:Screens) LeafScreens.Add(MakeShared<FJsonValueNumber>(Value));
    for (int32 Value:LeafSources) LeafSourceRows.Add(MakeShared<FJsonValueNumber>(Value));
    for (int32 Value:OriginalLeafCounts) SourceLeafRows.Add(MakeShared<FJsonValueNumber>(Value));
    Row->SetArrayField(TEXT("leaf_screens"),LeafScreens);Row->SetArrayField(TEXT("leaf_source_lods"),LeafSourceRows);
    Row->SetArrayField(TEXT("source_leaf_lod_triangles"),SourceLeafRows);
    Row->SetArrayField(TEXT("rigid_lod_triangles"),RigidCounts);Row->SetBoolField(TEXT("simple_trunk"),SimpleTrunk);Row->SetBoolField(TEXT("passable"),Passable);
    Row->SetStringField(TEXT("collision"),Proxy?Proxy->GetPathName():TEXT(""));
    Row->SetStringField(TEXT("optimized"),Canopy->GetPathName());Row->SetStringField(TEXT("shadow"),ShadowMesh->GetPathName());
    Row->SetStringField(TEXT("leaf_reducer"),ReducerVersion);Row->SetNumberField(TEXT("source_leaf_triangles"),AuthoredNear.Triangles().Num());
    Row->SetNumberField(TEXT("shadow_triangles"),Shadow[0].Triangles().Num());
    TArray<TSharedPtr<FJsonValue>> Values;for (int32 Count:Counts) Values.Add(MakeShared<FJsonValueNumber>(Count));
    Row->SetArrayField(TEXT("triangles"),Values);FString Result;
    if (!FJsonSerializer::Serialize(Row,TJsonWriterFactory<>::Create(&Result))) return {};
    return Result;
#else
    return {};
#endif
}


bool UYorimichiFoliageResidencyBuilder::SelfTest()
{
#if WITH_EDITOR
    if (!IsInGameThread()) return false;
    const FString Directory=TEXT("/Game/FoliageResident/_ReceivingFixture_")+FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const auto* Default=UMaterial::GetDefaultMaterial(MD_Surface);
    TArray<FStaticMaterial> Materials={FStaticMaterial(const_cast<UMaterial*>(Default),TEXT("Rigid")),
        FStaticMaterial(const_cast<UMaterial*>(Default),TEXT("Leaf"))};
    TArray<FMeshDescription> Levels;Levels.SetNum(1);Initialize(Levels[0],Materials,6);
    FStaticMeshAttributes A(Levels[0]);auto P=A.GetVertexPositions();auto N=A.GetVertexInstanceNormals();
    auto C=A.GetVertexInstanceColors();auto UV=A.GetVertexInstanceUVs();
    for (int32 Face=0;Face<2;++Face)
    {
        TArray<FVertexInstanceID> Corners;
        for (int32 I=0;I<3;++I)
        {
            auto V=Levels[0].CreateVertex();P[V]=FVector3f(I==1?10.f:0.f,I==2?10.f:0.f,Face*100.f);
            auto Corner=Levels[0].CreateVertexInstance(V);N[Corner]=FVector3f(0,0,1);C[Corner]=FVector4f(.2f,.4f,.6f,.8f);
            for (int32 Channel=0;Channel<6;++Channel) UV.Set(Corner,Channel,FVector2f(Channel==5?float(Face):.125f,Channel==5?73.125f:.875f));
            Corners.Add(Corner);
        }
        Levels[0].CreateTriangle(FPolygonGroupID(Face),Corners);
    }
    // A real reduced leaf sheet with two categorical roles in the SAME material
    // slot exercises UV seams independently of material-boundary preservation.
    FMeshDescription Grid;Initialize(Grid,Materials,6);FStaticMeshAttributes GA(Grid);
    auto GP=GA.GetVertexPositions();auto GN=GA.GetVertexInstanceNormals();auto GC=GA.GetVertexInstanceColors();auto GU=GA.GetVertexInstanceUVs();
    for (int32 Role:{1,2}) for (int32 Y=0;Y<8;++Y) for (int32 X=0;X<8;++X)
        for (const TArray<FIntPoint>& Points:{TArray<FIntPoint>{{0,0},{1,0},{1,1}},TArray<FIntPoint>{{0,0},{1,1},{0,1}}})
        {
            TArray<FVertexInstanceID> Corners;
            for (const auto& Point:Points)
            {
                const auto V=Grid.CreateVertex();GP[V]=FVector3f((X+Point.X)*20.f+Role*200.f,(Y+Point.Y)*20.f,0.f);
                const auto I=Grid.CreateVertexInstance(V);GN[I]=FVector3f(0,0,1);GC[I]=FVector4f(.2f,.4f,.6f,.8f);
                for (int32 Channel=0;Channel<6;++Channel)
                    GU.Set(I,Channel,Channel==5?FVector2f(float(Role),73.125f):FVector2f((X+Point.X)*.125f,(Y+Point.Y)*.125f));
                Corners.Add(I);
            }
            Grid.CreateTriangle(FPolygonGroupID(1),Corners);
        }
    TArray<FMeshDescription> ReducedLeaves;FString ReductionVersion;
    bool ReductionProof=LeafLevels(Grid,Materials,ReducedLeaves,ReductionVersion) && ReducedLeaves.Num()==4 &&
        GeometryHash(Grid)==GeometryHash(ReducedLeaves[0]) && ReducedLeaves.Last().Triangles().Num()<Grid.Triangles().Num();
    for (const auto& D:ReducedLeaves) for (auto T:D.Triangles().GetElementIDs())
    {
        bool Tagged;FVector2f Role;
        ReductionProof=ReductionProof && D.GetTrianglePolygonGroup(T)==FPolygonGroupID(1) && LeafRole(D,T,Tagged,Role) && Tagged &&
            (Role.X==1.f || Role.X==2.f) && Role.Y==73.125f;
    }
    FMeshDescription BadRole=Grid;const auto Corner=BadRole.GetTriangleVertexInstances(FTriangleID(0))[0];
    FStaticMeshAttributes(BadRole).GetVertexInstanceUVs().Set(Corner,5,FVector2f(1.5f,73.125f));
    bool Tagged;FVector2f Role;
    ReductionProof=ReductionProof && !LeafRole(BadRole,FTriangleID(0),Tagged,Role);
    // Prove UV0 normalization and exact duplicate multiplicity independently of
    // physics cooking, which may legitimately deduplicate coincident triangles.
    FMeshDescription Narrow=Levels[0];FStaticMeshAttributes(Narrow).GetVertexInstanceUVs().SetNumChannels(1);
    FMeshDescription SignedZero=Narrow,NonZero=Narrow;
    FStaticMeshAttributes(SignedZero).GetVertexPositions()[FVertexID(0)].X=-0.f;
    FStaticMeshAttributes(NonZero).GetVertexPositions()[FVertexID(0)].X=1.e-20f;
    const bool ZeroProof=TriangleKey(SignedZero,FTriangleID(0),0)==TriangleKey(Narrow,FTriangleID(0),0) &&
        GeometryHash(SignedZero)!=GeometryHash(Narrow) &&
        TriangleKey(NonZero,FTriangleID(0),0)!=TriangleKey(Narrow,FTriangleID(0),0);
    FMeshDescription Duplicate=Narrow;
    // This fixture creates triangle IDs 0 and 1 directly above.
    if (!CopyTriangle(Narrow,FTriangleID(0),0,Duplicate)) return false;
    FMeshDescription Expanded=Duplicate;auto ExpandedUV=FStaticMeshAttributes(Expanded).GetVertexInstanceUVs();
    ExpandedUV.SetNumChannels(6);
    for (auto I:Expanded.VertexInstances().GetElementIDs())
        for (int32 Channel=1;Channel<6;++Channel) ExpandedUV.Set(I,Channel,ExpandedUV.Get(I,0));
    auto* MembershipSource=NewObject<UStaticMesh>();MembershipSource->GetStaticMaterials()=Materials;
    MembershipSource->SetNumSourceModels(1);MembershipSource->CreateMeshDescription(0,Duplicate);MembershipSource->CommitMeshDescription(0);
    auto* MembershipInput=NewObject<UStaticMesh>();MembershipInput->GetStaticMaterials()=Materials;
    MembershipInput->SetNumSourceModels(1);MembershipInput->CreateMeshDescription(0,Expanded);MembershipInput->CommitMeshDescription(0);
    FMeshDescription LeafProof,RigidProof;int32 Removed=0;TSet<int32> LeafSlots;LeafSlots.Add(1);
    bool Membership=ZeroProof && ReductionProof && Split(MembershipInput,0,MembershipSource,0,TEXT("material"),LeafSlots,LeafProof,&RigidProof,Removed) &&
        Removed==2 && LeafProof.Triangles().Num()==1 && RigidProof.Triangles().Num()==2;
    MembershipInput->CreateMeshDescription(0,Narrow);MembershipInput->CommitMeshDescription(0);
    FMeshDescription MissingLeaf,MissingRigid;
    Membership=Membership && !Split(MembershipInput,0,MembershipSource,0,TEXT("material"),LeafSlots,MissingLeaf,&MissingRigid,Removed);
    MembershipInput->MarkAsGarbage();MembershipSource->MarkAsGarbage();
    FKAggregateGeom Empty;TArray<UStaticMesh*> Objects;
    auto* Source=Build(Directory/TEXT("FixtureTree"),Levels,Materials,{1.f},ECollision::None,Empty);Objects.Add(Source);
    Materials.Add(FStaticMaterial(const_cast<UMaterial*>(Default),TEXT("CanopyNear")));
    Materials.Add(FStaticMaterial(const_cast<UMaterial*>(Default),TEXT("CanopyFar")));
    TArray<FMeshDescription> Prepared;Prepared.SetNum(4);
    for (auto& D:Prepared)
    { D=Levels[0];FStaticMeshAttributes Attr(D);auto Names=Attr.GetPolygonGroupMaterialSlotNames();
      Names[D.CreatePolygonGroup()]=TEXT("CanopyNear");Names[D.CreatePolygonGroup()]=TEXT("CanopyFar"); }
    auto* Input=Build(Directory/TEXT("Input"),Prepared,Materials,{1.f,.24f,.07f,.018f},ECollision::None,Empty);Objects.Add(Input);
    TArray<FMeshDescription> Shadow={Prepared.Last()};
    auto* InputShadow=Build(Directory/TEXT("InputShadow"),Shadow,Materials,{1.f},ECollision::None,Empty);Objects.Add(InputShadow);
    bool Passed=Membership && Source && Input && InputShadow;
    for (bool Simple:{false,true})
    {
        if (!Passed) break;
        const FString Row=Compact(Source,Input,InputShadow,TEXT("roles"),{},1,Simple,{0,0,0,0},
            Simple?TArray<float>{2.f,0.f,0.f,0.f,0.f,0.f,10.f}:TArray<float>{},
            Directory/(Simple?TEXT("Simple"):TEXT("Mixed")),nullptr);
        Passed=!Row.IsEmpty();
        auto* Carrier=LoadObject<UStaticMesh>(nullptr,*(Directory/(Simple?TEXT("Simple"):TEXT("Mixed"))/TEXT("FixtureTree.FixtureTree")));
        auto* Canopy=LoadObject<UStaticMesh>(nullptr,*(Directory/(Simple?TEXT("Simple"):TEXT("Mixed"))/TEXT("FixtureTree_Canopy.FixtureTree_Canopy")));
        auto* Shade=LoadObject<UStaticMesh>(nullptr,*(Directory/(Simple?TEXT("Simple"):TEXT("Mixed"))/TEXT("FixtureTree_Shadow.FixtureTree_Shadow")));
        Objects.Append({Carrier,Canopy,Shade});
        Passed=Passed && Carrier && Canopy && Shade && Carrier->GetNumTriangles(0)==1 &&
            Canopy->GetNumTriangles(0)==1 && Shade->GetNumTriangles(0)==1 &&
            Canopy->GetBodySetup()->AggGeom.GetElementCount()==0 && Canopy->GetBodySetup()->TriMeshGeometries.IsEmpty();
        if (Passed && Simple)
        { const auto& Shapes=Carrier->GetBodySetup()->AggGeom;
          Passed=Shapes.GetElementCount()==1 && Shapes.SphylElems.Num()==1 &&
              Shapes.SphylElems[0].Center.Z+Shapes.SphylElems[0].Length*.5+Shapes.SphylElems[0].Radius<100.f; }
    }
    if (Passed)
    {
        TArray<FMeshDescription> TwoLevels;TwoLevels.Init(Levels[0],2);
        Source=Build(Directory/TEXT("FixtureTree"),TwoLevels,Source->GetStaticMaterials(),{1.f,.13f},ECollision::None,Empty);
        if (!Source) return false;
        const FString Row=Compact(Source,Input,InputShadow,TEXT("roles"),{},1,true,{0,0,1,1},
            {2.f,0.f,0.f,0.f,0.f,0.f,10.f},Directory/TEXT("TrunkLODs"),nullptr);
        auto* Carrier=LoadObject<UStaticMesh>(nullptr,*(Directory/TEXT("TrunkLODs/FixtureTree.FixtureTree")));
        auto* Canopy=LoadObject<UStaticMesh>(nullptr,*(Directory/TEXT("TrunkLODs/FixtureTree_Canopy.FixtureTree_Canopy")));
        auto* Shade=LoadObject<UStaticMesh>(nullptr,*(Directory/TEXT("TrunkLODs/FixtureTree_Shadow.FixtureTree_Shadow")));
        Objects.Append({Carrier,Canopy,Shade});Passed=!Row.IsEmpty() && Carrier && Canopy && Carrier->GetNumSourceModels()==2 &&
            Canopy->GetNumSourceModels()==2 && Canopy->GetRenderData()->ScreenSize[1].GetValue()==.13f;
    }
    if (Passed)
    {
        TArray<FMeshDescription> RenderLevels;RenderLevels.Init(Levels[0],4);
        auto* Generated=Build(Directory/TEXT("GeneratedTree"),RenderLevels,Source->GetStaticMaterials(),
            {1.f,.24f,.07f,.018f},ECollision::None,Empty);Objects.Add(Generated);
        if (!Generated) Passed=false;
        else
        {
            // The real producer exports each generated source LOD's render
            // data, including its quantized colours/normals. Its certified
            // prepared corners therefore come from that exact readback, not
            // from the pre-render LOD0 float colours used by the other fixtures.
            TArray<FMeshDescription> GeneratedPrepared;GeneratedPrepared.SetNum(4);
            GeneratedPrepared[0]=Levels[0];
            for (int32 L=1;L<4;++L)
            {
                Generated->ExportStaticMeshLOD(Generated->GetRenderData()->LODResources[L],GeneratedPrepared[L]);
                auto Names=FStaticMeshAttributes(GeneratedPrepared[L]).GetPolygonGroupMaterialSlotNames();
                // Both fixture sections are populated, in explicit Rigid/Leaf order.
                for (auto G:GeneratedPrepared[L].PolygonGroups().GetElementIDs())
                    Names[G]=Materials[G.GetValue()].MaterialSlotName;
            }
            for (auto& D:GeneratedPrepared)
            {
                auto Names=FStaticMeshAttributes(D).GetPolygonGroupMaterialSlotNames();
                Names[D.CreatePolygonGroup()]=TEXT("CanopyNear");Names[D.CreatePolygonGroup()]=TEXT("CanopyFar");
            }
            auto* GeneratedInput=Build(Directory/TEXT("GeneratedInput"),GeneratedPrepared,Materials,
                {1.f,.24f,.07f,.018f},ECollision::None,Empty);Objects.Add(GeneratedInput);
            TArray<FMeshDescription> GeneratedShadow={GeneratedPrepared.Last()};
            auto* GeneratedShade=Build(Directory/TEXT("GeneratedShade"),GeneratedShadow,Materials,
                {1.f},ECollision::None,Empty);Objects.Add(GeneratedShade);
            // Retain compiled LOD resources while dropping higher stored source
            // descriptions: the same state produced by SetLods reduction.
            Generated->SetNumSourceModels(1);Generated->SetNumSourceModels(4);
            Passed=GeneratedInput && GeneratedShade && Generated->GetMeshDescription(1)==nullptr && Generated->GetRenderData()->LODResources.Num()==4;
            const FString Row=Passed?Compact(Generated,GeneratedInput,GeneratedShade,TEXT("roles"),{},1,false,{0,1,2,3},{},
                Directory/TEXT("GeneratedLODs"),nullptr):FString{};
            for (const TCHAR* Suffix:{TEXT(""),TEXT("_Canopy"),TEXT("_Shadow")})
            {
                const FString Asset=Directory/TEXT("GeneratedLODs")/(FString(TEXT("GeneratedTree"))+Suffix);
                Objects.Add(LoadObject<UStaticMesh>(nullptr,*(Asset+TEXT(".")+FPackageName::GetLongPackageAssetName(Asset))));
            }
            Passed=Passed && !Row.IsEmpty();
        }
    }
    if (Passed)
    {
        // Five real authored levels retain their fifth transition and far leaf
        // shape. A second pass proves an intentionally empty far leaf level.
        TArray<FMeshDescription> Chain;Chain.Init(Levels[0],5);
        auto FarPositions=FStaticMeshAttributes(Chain[4]).GetVertexPositions();
        for (auto I:Chain[4].GetTriangleVertexInstances(FTriangleID(1)))
            FarPositions[Chain[4].GetVertexInstanceVertex(I)].X+=25.f;
        auto FarUV=FStaticMeshAttributes(Chain[4]).GetVertexInstanceUVs();FarUV.SetNumChannels(8);
        for (auto I:Chain[4].VertexInstances().GetElementIDs())
        { FarUV.Set(I,6,FVector2f(.321f,.654f));FarUV.Set(I,7,FVector2f(.246f,.135f)); }
        const TArray<float> AuthoredScreens={1.f,.31f,.12f,.04f,.009f};
        for (bool EmptyFar:{false,true})
        {
            if (!Passed) break;
            if (EmptyFar)
            {
                FMeshDescription RigidOnly;Initialize(RigidOnly,Source->GetStaticMaterials(),6);
                if (!CopyTriangle(Levels[0],FTriangleID(0),0,RigidOnly)) return false;
                Chain[4]=MoveTemp(RigidOnly);
            }
            auto* Authored=Build(Directory/TEXT("AuthoredTree"),Chain,Source->GetStaticMaterials(),AuthoredScreens,ECollision::None,Empty);
            Objects.Add(Authored);if (!Authored) { Passed=false;break; }
            const FString Scope=Directory/(EmptyFar?TEXT("EmptyFar"):TEXT("AuthoredFive"));
            const FString Row=Compact(Authored,Input,InputShadow,TEXT("roles"),{},1,true,{0,1,3,4},
                {2.f,0.f,0.f,0.f,0.f,0.f,10.f},Scope,nullptr);
            auto* Leaves=LoadObject<UStaticMesh>(nullptr,*(Scope/TEXT("AuthoredTree_Canopy.AuthoredTree_Canopy")));
            auto* RigidMesh=LoadObject<UStaticMesh>(nullptr,*(Scope/TEXT("AuthoredTree.AuthoredTree")));
            auto* ShadowMesh=LoadObject<UStaticMesh>(nullptr,*(Scope/TEXT("AuthoredTree_Shadow.AuthoredTree_Shadow")));
            Objects.Append({Leaves,RigidMesh,ShadowMesh});
            Passed=!Row.IsEmpty() && Leaves && RigidMesh && Leaves->GetNumSourceModels()==5 && RigidMesh->GetNumSourceModels()==5;
            if (Passed) for (int32 L=0;L<5;++L)
                Passed=Passed && Leaves->GetRenderData()->ScreenSize[L].GetValue()==AuthoredScreens[L] &&
                    RigidMesh->GetRenderData()->ScreenSize[L].GetValue()==AuthoredScreens[L] &&
                    Leaves->GetRenderData()->LODResources[L].GetNumTriangles()==uint32(EmptyFar && L==4?0:1);
            if (Passed && !EmptyFar)
            {
                const auto* Far=Leaves->GetMeshDescription(4);
                Passed=Far && FStaticMeshConstAttributes(*Far).GetVertexInstanceUVs().GetNumChannels()==8 &&
                    TriangleKey(*Far,FTriangleID(0),1)==TriangleKey(Chain[4],FTriangleID(1),1);
            }
        }
    }
    for (auto* Object:Objects) if (Object)
    { FAssetRegistryModule::AssetDeleted(Object);Object->ClearFlags(RF_Public|RF_Standalone);Object->MarkAsGarbage(); }
    return Passed;
#else
    return false;
#endif
}
