#include "FoliageBuilder.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInterface.h"
#include "Materials/Material.h"
#include "StaticMeshResources.h"
#include "StaticMeshAttributes.h"
#include "MeshDescription.h"
#include "StaticMeshCompiler.h"
#include "ImageCore.h"
#include "UObject/GarbageCollection.h"
#include "UObject/Package.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "EngineUtils.h"

int32 UYorimichiFoliageBuilder::RegisterReviewInstances(UWorld* World)
{
    if (!World || !World->IsGameWorld() || World->GetOutermost()->GetName()!=TEXT("/Engine/Maps/Entry")) return 0;
    int32 Count=0;
    for (TActorIterator<AActor> It(World);It;++It)
    {
        TInlineComponentArray<UHierarchicalInstancedStaticMeshComponent*> Components;
        It->GetComponents(Components);
        for (auto* Component:Components)
        {
            Component->RegisterComponentWithWorld(World);
            Component->BuildTreeIfOutdated(false,true);
            Component->UpdateBounds();
            Count+=Component->GetInstanceCount();
        }
    }
    return Count;
}

namespace
{
TSharedPtr<FJsonValue> Number(double V) { return MakeShared<FJsonValueNumber>(V); }
TArray<TSharedPtr<FJsonValue>> Values(std::initializer_list<double> V)
{
    TArray<TSharedPtr<FJsonValue>> Result;
    for (double X : V) Result.Add(Number(X));
    return Result;
}

float PaletteLinear(float C)
{
    return C<=.04045f?C/12.92f:FMath::Pow((C+.055f)/1.055f,2.4f);
}

float Scalar(UMaterialInterface* Material,const TCHAR* Key,float Default)
{
    float Value=Default;Material->GetScalarParameterValue(FMaterialParameterInfo(Key),Value);return Value;
}

bool MaterialColour(UMaterialInterface* Material,FLinearColor& Colour)
{
    // These are the source graph interfaces, not a blanket "texture times tint"
    // rule: Brinecove selects Colour OR texture with UseTex; world foliage uses
    // Tex * Tint; imported glTF uses BaseColorTexture * BaseColorFactor.
    Colour=FLinearColor::White;FLinearColor Tint;bool Known=false;
    const FString Parent=Material->GetMaterial()->GetName();
    for (const TCHAR* Key:{TEXT("Colour"),TEXT("Tint"),TEXT("BaseColorFactor")})
        if (Material->GetVectorParameterValue(FMaterialParameterInfo(Key),Tint)) { Colour*=Tint;Known=true; }
    if (const auto* Data=Material->GetMaterial()->GetEditorOnlyData();Data && Data->BaseColor.UseConstant)
    { Colour*=Data->BaseColor.Constant;Known=true; }
    UTexture* Texture=nullptr;
    for (const TCHAR* Key:{TEXT("Tex"),TEXT("BaseColorTexture"),TEXT("Base")})
        if (Material->GetTextureParameterValue(FMaterialParameterInfo(Key),Texture) && Texture) break;
    float UseTex=0;
    const bool SelectTexture=Material->GetScalarParameterValue(FMaterialParameterInfo(TEXT("UseTex")),UseTex);
    FLinearColor TextureColour=FLinearColor::White;
    if (Texture && (!SelectTexture || UseTex>0))
    {
        UTexture2D* Image=Cast<UTexture2D>(Texture);FImage Raw,Linear;
        if (!Image || !Image->Source.GetMipImage(Raw,0))
        { UE_LOG(LogTemp,Error,TEXT("FOLIAGE palette cannot read texture: %s"),*Material->GetPathName());return false; }
        Raw.GammaSpace=Image->SRGB?EGammaSpace::sRGB:EGammaSpace::Linear;
        Raw.CopyTo(Linear,ERawImageFormat::RGBA32F,EGammaSpace::Linear);
        const FLinearColor* Pixels=reinterpret_cast<const FLinearColor*>(Linear.RawData.GetData());
        FLinearColor Sum(0,0,0,0);double Weight=0.;
        for (int64 I=0;I<int64(Linear.SizeX)*Linear.SizeY;++I)
            if (Pixels[I].A>.4f) { Sum+=Pixels[I]*Pixels[I].A;Weight+=Pixels[I].A; }
        if (Weight<=0.) { UE_LOG(LogTemp,Error,TEXT("FOLIAGE palette has no covered texels: %s"),*Material->GetPathName());return false; }
        TextureColour=Sum/float(Weight);Known=true;
    }
    if (SelectTexture) Colour=FMath::Lerp(Colour,TextureColour,FMath::Clamp(UseTex,0.f,1.f));
    else if (Parent==TEXT("M_HDCity"))
    {
        const float Strength=Scalar(Material,TEXT("Strength"),1.f),Macro=Scalar(Material,TEXT("Macro"),.5f);
        TextureColour*=2.f;
        Colour=FMath::Lerp(FLinearColor::White,TextureColour*FMath::Lerp(FLinearColor::White,TextureColour,.35f*Macro),Strength)
            *Scalar(Material,TEXT("Gain"),1.f);Known=true;
    }
    else Colour*=TextureColour;
    if (Parent==TEXT("M_Arcade") || Parent==TEXT("M_ArcadePaving") || Parent==TEXT("M_PlazaPaving") ||
        Parent==TEXT("M_Village") || Parent==TEXT("M_Harbor")) { Colour=FLinearColor::White;Known=true; }
    if (!Known) { UE_LOG(LogTemp,Error,TEXT("FOLIAGE needs a material palette adapter: %s"),*Material->GetPathName());return false; }
    Colour.A=Scalar(Material,TEXT("Glow"),0.f);
    return true;
}

FLinearColor VertexSample(UMaterialInterface* Material,const FString& Parent,const FLinearColor& Palette,const FVector4f& Vertex)
{
    FLinearColor Result=Palette;
    if (Parent==TEXT("M_ArcadePaving") || Parent==TEXT("M_PlazaPaving"))
    {
        // Both paving graphs select linear vertex paint for their coloured leaf
        // surfaces. Rigid paving keeps its original texture/material unchanged.
        Result.R=PaletteLinear(Vertex.X);Result.G=PaletteLinear(Vertex.Y);Result.B=PaletteLinear(Vertex.Z);
        Result.A=0.f;
        if (Parent==TEXT("M_ArcadePaving"))
        {
            const bool Lamp=Result.R>=.82f && Result.G>=.45f && Result.G<=.68f && Result.B<=.30f;
            const bool Canvas=Result.R>=.70f && Result.R<=.79f && Result.G>=.55f && Result.B>=.35f;
            const bool Leaf=Result.R>=.4f && Result.G>=.24f && Result.B<=.07f;
            const bool Shop=Result.R>=.18f && Result.R<=.22f && Result.G>=.08f && Result.G<=.11f && Result.B>=.02f && Result.B<=.04f;
            Result.A=.045f+(Lamp?.9f:0.f)+(Canvas?.20f:0.f)+(Leaf?.38f:0.f)+(Shop?.15f:0.f);
        }
    }
    else if (Parent==TEXT("M_Arcade") || Parent==TEXT("M_HDCity"))
    {
        Result.R*=PaletteLinear(Vertex.X);Result.G*=PaletteLinear(Vertex.Y);Result.B*=PaletteLinear(Vertex.Z);
        const bool Leaf=PaletteLinear(Vertex.X)>=.4f && PaletteLinear(Vertex.Y)>=.24f && PaletteLinear(Vertex.Z)<=.07f;
        Result.A=.045f+(Leaf?.38f:0.f);
    }
    else if (Parent==TEXT("M_TreeHouse"))
    {
        const float Gain=Scalar(Material,TEXT("Gain"),2.f);
        Result.R*=PaletteLinear(PaletteLinear(Vertex.X))*Gain;
        Result.G*=PaletteLinear(PaletteLinear(Vertex.Y))*Gain;
        Result.B*=PaletteLinear(PaletteLinear(Vertex.Z))*Gain;
        Result.A+=.06f;
    }
    else if (Parent==TEXT("M_Village") || Parent==TEXT("M_Harbor"))
    {
        Result.R*=PaletteLinear(Vertex.X);Result.G*=PaletteLinear(Vertex.Y);Result.B*=PaletteLinear(Vertex.Z);
        Result.A=Parent==TEXT("M_Village")?.06f:.025f;
    }
    else if (Parent==TEXT("M_Pier_concrete"))
    {
        // Sunset Pier: linearize vertex paint, multiply linear albedo and gain 2.
        Result.R*=PaletteLinear(Vertex.X)*2.f;Result.G*=PaletteLinear(Vertex.Y)*2.f;
        Result.B*=PaletteLinear(Vertex.Z)*2.f;Result.A=.035f;
    }
    else if (Parent==TEXT("M_CP_Flat") || Parent==TEXT("M_CP_Textured"))
    {
        // Crater Park uses vertex red as encoded baked cavity, not vertex paint.
        const float Shade=FMath::Lerp(1.f,PaletteLinear(Vertex.X),Scalar(Material,TEXT("Cavity"),.3f));
        Result.R*=Shade;Result.G*=Shade;Result.B*=Shade;Result.A=0.f;
    }
    else if (Parent==TEXT("M_Foliage") || Parent==TEXT("M_Grass"))
    { const float Shade=.5f+.5f*Vertex.Y;Result.R*=Shade;Result.G*=Shade;Result.B*=Shade; }
    return Result;
}

bool Read(const FString& Path, TSharedPtr<FJsonObject>& Object)
{
    FString Text;
    return FFileHelper::LoadFileToString(Text,*Path) &&
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(MoveTemp(Text)), Object) && Object.IsValid();
}
}

bool UYorimichiFoliageBuilder::StampSourceRoles(UStaticMesh* Source)
{
    if (!Source || !IsInGameThread()) return false;
    FStaticMeshCompilingManager::Get().FinishCompilation({Source});
    const FMeshDescription* D=Source->GetMeshDescription(0);
    if (!D) return false;
    FStaticMeshConstAttributes A(*D);const auto UV=A.GetVertexInstanceUVs();
    bool Marked=false,Valid=true,Authored=true,Rigid=true;
    if (UV.GetNumChannels()>5)
        for (const auto I:D->VertexInstances().GetElementIDs())
        {
            const FVector2f V=UV.Get(I,5);
            const bool Marker=FMath::IsNearlyEqual(V.Y,73.125f,.01f) || FMath::IsNearlyEqual(V.Y,-72.125f,.01f);
            Marked|=Marker;Valid&=Marker && (V.X==0.f || V.X==1.f || V.X==2.f || V.X==3.f);Authored&=V.X==3.f;Rigid&=V.X==0.f;
        }
    if (Marked && !Valid) return false;
    const FString Prefix=Marked && Rigid?TEXT("FoliageRigid_"):Marked && Authored?TEXT("FoliageAuthored_"):TEXT("FoliageRoles_");bool Changed=false;
    for (auto& Slot:Source->GetStaticMaterials())
    {
        FString Name=Slot.MaterialSlotName.ToString();
        for (const TCHAR* Previous:{TEXT("FoliageRoles_"),TEXT("FoliageAuthored_"),TEXT("FoliageRigid_")})
            if (Name.StartsWith(Previous)) { Name.RightChopInline(FCString::Strlen(Previous));break; }
        const FName Desired(*(Marked?Prefix+Name:Name));
        if (Slot.MaterialSlotName!=Desired) { Slot.MaterialSlotName=Desired;Changed=true; }
    }
    if (Changed) Source->MarkPackageDirty();
    return true;
}

void UYorimichiFoliageBuilder::CollectUnused()
{
    // Python's CollectGarbage only requests a future engine tick. This owner is
    // a synchronous commandlet; saved, unreferenced mesh packages must leave now.
    ::CollectGarbage(RF_NoFlags,true);
}

bool UYorimichiFoliageBuilder::MaterialIsMasked(UMaterialInterface* Material)
{
    return Material && Material->GetBlendMode()==BLEND_Masked;
}

bool UYorimichiFoliageBuilder::MaterialUsesFoliageShading(UMaterialInterface* Material)
{
    return Material && Material->GetShadingModels().HasShadingModel(MSM_TwoSidedFoliage);
}

bool UYorimichiFoliageBuilder::ExportSource(UStaticMesh* Source, const TArray<int32>& LeafSlots,
    const FString& Classification, const FString& Kind, const FString& Path,int32 LODIndex)
{
    if (!Source || !IsInGameThread()) return false;
    FStaticMeshCompilingManager::Get().FinishCompilation({Source});
    // Export the MeshDescription rather than cook-dependent CPU buffers. Imported
    // originals deliberately need not retain render buffers on the CPU.
    FMeshDescription Description;
    if (const FMeshDescription* Stored = Source->GetMeshDescription(LODIndex)) Description = *Stored;
    else if (Source->GetRenderData() && Source->GetRenderData()->LODResources.IsValidIndex(LODIndex))
        Source->ExportStaticMeshLOD(Source->GetRenderData()->LODResources[LODIndex], Description);
    else return false;
    FStaticMeshAttributes Attributes(Description);
    const auto Positions = Attributes.GetVertexPositions();
    const auto Normals = Attributes.GetVertexInstanceNormals();
    const auto UVs = Attributes.GetVertexInstanceUVs();
    const auto Colours = Attributes.GetVertexInstanceColors();
    const auto SlotNames = Attributes.GetPolygonGroupMaterialSlotNames();
    auto Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("path"),Source->GetPathName()); Root->SetStringField(TEXT("kind"),Kind);
    Root->SetNumberField(TEXT("uv_channels"), UVs.GetNumChannels());
    Root->SetStringField(TEXT("classification"),Classification);
    TArray<TSharedPtr<FJsonValue>> Materials, Vertices, Faces;
    TArray<FLinearColor> Palette;
    TArray<FString> MaterialParents;
    for (int32 I = 0; I < Source->GetStaticMaterials().Num(); ++I)
    {
        UMaterialInterface* Material = Source->GetMaterial(I);
        if (!Material) return false;
        MaterialParents.Add(Material->GetMaterial()->GetName());
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("path"),Material->GetPathName());
        Entry->SetBoolField(TEXT("foliage"),LeafSlots.Contains(I));
        Materials.Add(MakeShared<FJsonValueObject>(Entry));
        FLinearColor Colour=FLinearColor::White;
        if ((LeafSlots.Contains(I) || (Classification!=TEXT("material") && Classification!=TEXT("authored"))) && !MaterialColour(Material,Colour)) return false;
        Palette.Add(Colour);
    }
    TMap<FVertexInstanceID,int32> Remap;
    int32 Slot = INDEX_NONE;
    for (const FTriangleID Triangle : Description.Triangles().GetElementIDs())
    {
        const FPolygonGroupID Group = Description.GetTrianglePolygonGroup(Triangle);
        Slot = Source->GetMaterialIndex(SlotNames[Group]);
        if (Slot==INDEX_NONE)
            for (int32 I=0;I<Source->GetStaticMaterials().Num();++I)
                if (Source->GetStaticMaterials()[I].ImportedMaterialSlotName==SlotNames[Group]) { Slot=I;break; }
        if (!Palette.IsValidIndex(Slot)) return false;
        TArray<TSharedPtr<FJsonValue>> Indices;
        bool IsLeaf = LeafSlots.Contains(Slot);
        for (const FVertexInstanceID Instance : Description.GetTriangleVertexInstances(Triangle))
        {
            const FVector3f P = Positions[Description.GetVertexInstanceVertex(Instance)];
            const FVector4f C = Colours[Instance];
            if (!Remap.Contains(Instance))
            {
                Remap.Add(Instance, Vertices.Num());
                const FVector3f N = Normals[Instance]; const FVector2f UV = UVs.Get(Instance,0);
                auto V = MakeShared<FJsonObject>();
                V->SetArrayField(TEXT("p"),Values({P.X,P.Y,P.Z}));
                V->SetArrayField(TEXT("n"),Values({N.X,N.Y,N.Z}));
                V->SetArrayField(TEXT("uv"),Values({UV.X,UV.Y}));
                V->SetArrayField(TEXT("c"),Values({C.X,C.Y,C.Z,C.W}));
                // Vertex-painted trees carry their colour in the source vertex;
                // texture-based crowns use their alpha-weighted linear palette.
                auto* Material=Source->GetMaterial(Slot);
                const FString& Parent=MaterialParents[Slot];
                const bool RoleLeaf=Classification==TEXT("roles") && UVs.GetNumChannels()>5 &&
                    UVs.Get(Instance,5).X>0.f;
                if ((IsLeaf || RoleLeaf) && (Parent==TEXT("M_ArcadePaving") || Parent==TEXT("M_PlazaPaving")))
                {
                    const FVector3f Linear(PaletteLinear(C.X),PaletteLinear(C.Y),PaletteLinear(C.Z));
                    if (Linear.GetMax()-Linear.GetMin()<.07f)
                    { UE_LOG(LogTemp,Error,TEXT("FOLIAGE paving leaf uses the unsupported textured branch: %s"),*Material->GetPathName());return false; }
                }
                const FLinearColor Sample=VertexSample(Material,Parent,Palette[Slot],C);
                V->SetArrayField(TEXT("sample"),Values({Sample.R,Sample.G,Sample.B,Sample.A}));
                TArray<TSharedPtr<FJsonValue>> Channels;
                for (int32 Channel=0;Channel<UVs.GetNumChannels();++Channel)
                { const FVector2f U=UVs.Get(Instance,Channel);Channels.Add(MakeShared<FJsonValueArray>(Values({U.X,U.Y}))); }
                V->SetArrayField(TEXT("uvs"),Channels);
                Vertices.Add(MakeShared<FJsonValueObject>(V));
            }
            Indices.Add(Number(Remap[Instance]));
        }
        auto Face=MakeShared<FJsonObject>();Face->SetArrayField(TEXT("v"),Indices);
        Face->SetNumberField(TEXT("s"),Slot);Face->SetBoolField(TEXT("foliage"),IsLeaf);
        Faces.Add(MakeShared<FJsonValueObject>(Face));
    }
    Root->SetArrayField(TEXT("vertices"),Vertices);Root->SetArrayField(TEXT("faces"),Faces);Root->SetArrayField(TEXT("materials"),Materials);
    FString Text;
    return FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Text)) && FFileHelper::SaveStringToFile(Text,*Path);
}

UStaticMesh* UYorimichiFoliageBuilder::BuildVariant(UStaticMesh* Source, const FString& JsonPath,
    const FString& Destination, UMaterialInterface* NearCanopy, UMaterialInterface* FarCanopy, bool ShadowOnly)
{
    TSharedPtr<FJsonObject> Root;
    if (!Source || !NearCanopy || !FarCanopy || !Read(JsonPath,Root) ||
        Root->GetStringField(TEXT("source"))!=Source->GetPathName()) return nullptr;
    const FString Name=FPackageName::GetLongPackageAssetName(Destination);
    UPackage* Package=CreatePackage(*Destination);
    // Saving fully loads existing packages. Load their old contents before any
    // edits, or serialization can overwrite a newly created placeholder mesh.
    Package->FullyLoad();
    if (!Package->IsFullyLoaded()) return nullptr;
    UStaticMesh* Mesh=FindObject<UStaticMesh>(Package,*Name);
    if (!Mesh) { Mesh=NewObject<UStaticMesh>(Package,*Name,RF_Public|RF_Standalone);FAssetRegistryModule::AssetCreated(Mesh); }
    FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    Mesh->Modify(); Mesh->GetStaticMaterials()=Source->GetStaticMaterials();
    Mesh->GetStaticMaterials().Add(FStaticMaterial(NearCanopy,TEXT("CanopyNear")));
    Mesh->GetStaticMaterials().Add(FStaticMaterial(FarCanopy,TEXT("CanopyFar")));
    TArray<TSharedPtr<FJsonValue>> Levels;
    if (ShadowOnly) Levels.Add(MakeShared<FJsonValueObject>(Root->GetObjectField(TEXT("shadow"))));
    else Levels=Root->GetArrayField(TEXT("levels"));
    TArray<FMeshDescription> Descriptions; Descriptions.SetNum(Levels.Num());
    TArray<const FMeshDescription*> Pointers;
    Mesh->SetNumSourceModels(Levels.Num());
    for (int32 L=0;L<Levels.Num();++L)
    {
        FMeshDescription& D=Descriptions[L];FStaticMeshAttributes A(D);A.Register();
        auto P=A.GetVertexPositions();auto N=A.GetVertexInstanceNormals();auto UV=A.GetVertexInstanceUVs();auto C=A.GetVertexInstanceColors();
        auto Names=A.GetPolygonGroupMaterialSlotNames();UV.SetNumChannels(FMath::Max(1,Source->GetNumTexCoords(0)));
        TArray<FPolygonGroupID> Groups;
        for (const FStaticMaterial& Material:Mesh->GetStaticMaterials())
        { const FPolygonGroupID G=D.CreatePolygonGroup();Names[G]=Material.MaterialSlotName;Groups.Add(G); }
        const auto Level=Levels[L]->AsObject();
        const auto& Vertices=Level->GetArrayField(TEXT("vertices"));
        for (const auto& FaceValue:Level->GetArrayField(TEXT("faces")))
        {
            auto Face=FaceValue->AsObject();const int32 Slot=Face->GetIntegerField(TEXT("s"));
            if (!Groups.IsValidIndex(Slot)) return nullptr;
            TArray<FVertexInstanceID> Corners;
            for (const auto& Index:Face->GetArrayField(TEXT("v")))
            {
                const int32 I=Index->AsNumber();if (!Vertices.IsValidIndex(I)) return nullptr;
                auto V=Vertices[I]->AsObject();const auto& Pos=V->GetArrayField(TEXT("p"));const auto& Norm=V->GetArrayField(TEXT("n"));
                const auto& Colour=V->GetArrayField(TEXT("c"));const auto& Tex=V->GetArrayField(TEXT("uv"));
                const FVertexID Vertex=D.CreateVertex();P[Vertex]=FVector3f(Pos[0]->AsNumber(),Pos[1]->AsNumber(),Pos[2]->AsNumber());
                const FVertexInstanceID Instance=D.CreateVertexInstance(Vertex);
                N[Instance]=FVector3f(Norm[0]->AsNumber(),Norm[1]->AsNumber(),Norm[2]->AsNumber());
                C[Instance]=FVector4f(Colour[0]->AsNumber(),Colour[1]->AsNumber(),Colour[2]->AsNumber(),Colour[3]->AsNumber());
                const TArray<TSharedPtr<FJsonValue>>* Channels=nullptr;
                V->TryGetArrayField(TEXT("uvs"),Channels);
                for (int32 Channel=0;Channel<UV.GetNumChannels();++Channel)
                {
                    const auto& Pair=Channels && Channels->IsValidIndex(Channel)?(*Channels)[Channel]->AsArray():Tex;
                    UV.Set(Instance,Channel,FVector2f(Pair[0]->AsNumber(),Pair[1]->AsNumber()));
                }
                Corners.Add(Instance);
            }
            D.CreateTriangle(Groups[Slot],Corners);
        }
        Pointers.Add(&D);
        auto& Model=Mesh->GetSourceModel(L);
        // SetNumSourceModels seeds automatic .5^LOD reduction. Every supplied
        // level is already prepared, including reused assets with old settings.
        Model.ReductionSettings=FMeshReductionSettings{};
        Model.ReductionSettings.BaseLODModel=L;
        Model.BuildSettings.bRecomputeNormals=false;Model.BuildSettings.bRecomputeTangents=true;
        Model.BuildSettings.bRemoveDegenerates=false;
        Model.BuildSettings.bGenerateLightmapUVs=false;Model.BuildSettings.bUseFullPrecisionUVs=true;
        Model.BuildSettings.DistanceFieldResolutionScale=0;Model.BuildSettings.MaxLumenMeshCards=0;
        Model.ScreenSize.Default=ShadowOnly?1.f:Root->GetArrayField(TEXT("screens"))[L]->AsNumber();
    }
    Mesh->SetAutoComputeLODScreenSize(false);Mesh->bGenerateMeshDistanceField=false;
    // Every description and screen value now owns its data. Drop both JSON
    // owners before allocating the render representation.
    Levels.Empty();Root.Reset();
    UStaticMesh::FBuildMeshDescriptionsParams Params;
    if (!Mesh->BuildFromMeshDescriptions(Pointers,Params)) return nullptr;
    Mesh->SetLightMapCoordinateIndex(0);Mesh->MarkPackageDirty();
    FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    return Mesh;
}
