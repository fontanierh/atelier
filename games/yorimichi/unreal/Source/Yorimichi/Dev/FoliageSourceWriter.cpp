#include "FoliageSourceWriter.h"
#if WITH_EDITOR
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

#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Policies/CondensedJsonPrintPolicy.h"
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

}
#endif

bool UYorimichiFoliageSourceWriter::ExportSource(UStaticMesh* Source, const TArray<int32>& LeafSlots,
    const FString& Classification, const FString& Kind, const FString& Path,int32 LODIndex)
{
#if WITH_EDITOR
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
    // Imported meshes can retain unused seed-material slots. They still belong
    // in the slot table, but no exported corner samples their palette.
    TSet<int32> UsedSlots;
    for (const FTriangleID Triangle : Description.Triangles().GetElementIDs())
    {
        const FName Name=SlotNames[Description.GetTrianglePolygonGroup(Triangle)];
        int32 Used=Source->GetMaterialIndex(Name);
        if (Used==INDEX_NONE)
            for (int32 I=0;I<Source->GetStaticMaterials().Num();++I)
                if (Source->GetStaticMaterials()[I].ImportedMaterialSlotName==Name) { Used=I;break; }
        if (!Source->GetStaticMaterials().IsValidIndex(Used)) return false;
        UsedSlots.Add(Used);
    }
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
        if (UsedSlots.Contains(I) && (LeafSlots.Contains(I) || (Classification!=TEXT("material") && Classification!=TEXT("authored"))) && !MaterialColour(Material,Colour)) return false;
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
    auto& Files=IFileManager::Get();
    const FString Temporary=FPaths::CreateTempFilename(*FPaths::GetPath(Path),TEXT("foliage-json-"),TEXT(".tmp"));
    TUniquePtr<FArchive> File(Files.CreateFileWriter(*Temporary));
    if (!File) return false;
    bool Saved=FJsonSerializer::Serialize(Root,TJsonWriterFactory<UTF8CHAR,TCondensedJsonPrintPolicy<UTF8CHAR>>::Create(File.Get()));
    Saved=File->Close() && Saved && !File->IsError();
    File.Reset();
    if (Saved) Saved=Files.Move(*Path,*Temporary,true,false);
    if (!Saved) Files.Delete(*Temporary,false,false);
    return Saved;
#else
    return false;
#endif
}
