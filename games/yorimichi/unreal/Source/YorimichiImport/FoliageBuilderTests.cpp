#include "FoliageBuilder.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Engine/StaticMesh.h"
#include "StaticMeshAttributes.h"
#include "MeshDescription.h"
#include "Misc/AutomationTest.h"
#include "StaticMeshResources.h"
#include "Materials/Material.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "FileHelpers.h"
#include "PackageTools.h"
#include "Misc/PackageName.h"
#include "StaticMeshCompiler.h"
#include "UObject/StrongObjectPtr.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageImportRolesTest,"Yorimichi.Foliage.ImportRoles",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageImportRolesTest::RunTest(const FString&)
{
    UE_LOG(LogTemp,Display,TEXT("FOLIAGE TEST creating source-role mesh fixture"));
    auto* Mesh=NewObject<UStaticMesh>();
    Mesh->SetNumSourceModels(1);
    const FName Imported=TEXT("TH_flat");Mesh->GetStaticMaterials().Add(FStaticMaterial(nullptr,Imported,Imported));
    FMeshDescription D;FStaticMeshAttributes A(D);A.Register();
    auto UV=A.GetVertexInstanceUVs();UV.SetNumChannels(6);
    auto P=A.GetVertexPositions();const auto Group=D.CreatePolygonGroup();
    A.GetPolygonGroupMaterialSlotNames()[Group]=Imported;
    TArray<FVertexInstanceID> Corners;
    for (int32 I=0;I<3;++I)
    {
        const auto V=D.CreateVertex();P[V]=FVector3f(I==1?100.f:0.f,I==2?100.f:0.f,0.f);
        const auto C=D.CreateVertexInstance(V);Corners.Add(C);UV.Set(C,0,FVector2f(.2f,.3f));
        UV.Set(C,5,FVector2f(2.f,-72.125f));
    }
    D.CreateTriangle(Group,Corners);
    if (!TestNotNull(TEXT("Fixture source mesh description"),Mesh->CreateMeshDescription(0,MoveTemp(D)))) return false;
    TestTrue(TEXT("Valid imported thin foliage role certifies"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    TestEqual(TEXT("Cooked slot advertises foliage"),Mesh->GetStaticMaterials()[0].MaterialSlotName,FName(TEXT("FoliageRoles_TH_flat")));
    TestEqual(TEXT("Imported binding identity remains exact"),Mesh->GetStaticMaterials()[0].ImportedMaterialSlotName,Imported);
    TestTrue(TEXT("Certification is idempotent"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    auto* Stored=Mesh->GetMeshDescription(0);FStaticMeshAttributes B(*Stored);auto Channels=B.GetVertexInstanceUVs();
    TestTrue(TEXT("Visible texture coordinates preserved"),Channels.Get(Corners[0],0)==FVector2f(.2f,.3f));
    for (const auto C:Corners)Channels.Set(C,5,FVector2f(3.f,-72.125f));
    TestTrue(TEXT("Explicit authored surfaces certify"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    TestEqual(TEXT("Authored policy is discoverable"),Mesh->GetStaticMaterials()[0].MaterialSlotName,FName(TEXT("FoliageAuthored_TH_flat")));
    for (const auto C:Corners)Channels.Set(C,5,FVector2f(0.f,-72.125f));
    TestTrue(TEXT("Explicit rigid use of leaf paint certifies"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    TestEqual(TEXT("Rigid paint use is discoverable"),Mesh->GetStaticMaterials()[0].MaterialSlotName,FName(TEXT("FoliageRigid_TH_flat")));
    TestEqual(TEXT("Rigid paint keeps imported material binding"),Mesh->GetStaticMaterials()[0].ImportedMaterialSlotName,Imported);
    for (const auto C:Corners)Channels.Set(C,5,FVector2f(3.f,-72.125f));
    Channels.Set(Corners[0],5,FVector2f(3.f,0.f));
    TestFalse(TEXT("Partial role channel refuses"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    for (const auto C:Corners)Channels.Set(C,5,FVector2f::ZeroVector);
    TestTrue(TEXT("Removing authoring roles clears cooked stamp"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    TestEqual(TEXT("Original cooked slot restored"),Mesh->GetStaticMaterials()[0].MaterialSlotName,Imported);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliagePavingPaletteTest,"Yorimichi.Foliage.PavingPalette",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliagePavingPaletteTest::RunTest(const FString&)
{
    auto* Source=NewObject<UStaticMesh>();Source->SetNumSourceModels(1);
    TStrongObjectPtr<UStaticMesh> KeepSource(Source);
    Source->GetStaticMaterials().Add(FStaticMaterial(nullptr,TEXT("FoliageRoles_Paving")));
    FMeshDescription D;FStaticMeshAttributes A(D);A.Register();
    auto UV=A.GetVertexInstanceUVs();UV.SetNumChannels(6);
    const auto Group=D.CreatePolygonGroup();A.GetPolygonGroupMaterialSlotNames()[Group]=TEXT("FoliageRoles_Paving");
    TArray<FVertexInstanceID> Corners;
    for (int32 I=0;I<3;++I)
    {
        const auto V=D.CreateVertex();A.GetVertexPositions()[V]=FVector3f(I==1?100.f:0.f,I==2?100.f:0.f,0.f);
        const auto C=D.CreateVertexInstance(V);Corners.Add(C);A.GetVertexInstanceNormals()[C]=FVector3f(0,0,1);
        A.GetVertexInstanceColors()[C]=FVector4f(.9f,.65f,.1f,1.f);UV.Set(C,0,FVector2f(.2f,.3f));UV.Set(C,5,FVector2f(2.f,73.125f));
    }
    Source->CreateMeshDescription(0,MoveTemp(D));
    const FString Path=FPaths::ProjectSavedDir()/TEXT("FoliagePavingPaletteTest.json");
    for (const TCHAR* Name:{TEXT("M_ArcadePaving"),TEXT("M_PlazaPaving")})
    {
        auto* Material=NewObject<UMaterial>(GetTransientPackage(),FName(Name));
        Material->GetEditorOnlyData()->BaseColor.UseConstant=false;
        // SetMaterial schedules a rebuild of this deliberately uncommitted
        // source fixture. Set the test slot directly, as the import-role fixture does.
        Source->GetStaticMaterials()[0].MaterialInterface=Material;
        if (!TestTrue(TEXT("Paving foliage palette exports without altering classification"),
            UYorimichiFoliageBuilder::ExportSource(Source,{},TEXT("roles"),TEXT("mixed"),Path))) return false;
        FString Text;TSharedPtr<FJsonObject> Root;
        if (!TestTrue(TEXT("Exported paving fixture is readable"),FFileHelper::LoadFileToString(Text,*Path) &&
            FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root))) return false;
        TestEqual(TEXT("Certified roles are retained"),Root->GetStringField(TEXT("classification")),FString(TEXT("roles")));
        const auto& Vertices=Root->GetArrayField(TEXT("vertices"));
        if (!TestEqual(TEXT("Fixture retains all triangle corners"),Vertices.Num(),3)) return false;
        const auto& Vertex=Vertices[0]->AsObject();
        const auto& Sample=Vertex->GetArrayField(TEXT("sample"));
        const auto Linear=[](float C){return FMath::Pow((C+.055f)/1.055f,2.4f);};
        TestTrue(TEXT("Leaf colour uses the source shader's linear vertex paint"),
            FMath::IsNearlyEqual(Sample[0]->AsNumber(),double(Linear(.9f)),1.e-6) &&
            FMath::IsNearlyEqual(Sample[1]->AsNumber(),double(Linear(.65f)),1.e-6) &&
            FMath::IsNearlyEqual(Sample[2]->AsNumber(),double(Linear(.1f)),1.e-6));
        TestTrue(TEXT("Arcade leaf glow and unlit plaza emission remain distinct"),
            FMath::IsNearlyEqual(Sample[3]->AsNumber(),FCString::Strcmp(Name,TEXT("M_ArcadePaving"))==0?.425:0.,1.e-6));
        FStaticMeshAttributes Stored(*Source->GetMeshDescription(0));
        TestTrue(TEXT("Visible UV and certified role are unchanged"),Stored.GetVertexInstanceUVs().Get(Corners[0],0)==FVector2f(.2f,.3f) &&
            Stored.GetVertexInstanceUVs().Get(Corners[0],5)==FVector2f(2.f,73.125f));
        for (const auto C:Corners) Stored.GetVertexInstanceColors()[C]=FVector4f(.5f,.5f,.5f,1.f);
        AddExpectedError(TEXT("FOLIAGE paving leaf uses the unsupported textured branch"),EAutomationExpectedErrorFlags::Contains,1);
        TestFalse(TEXT("Unsupported textured foliage refuses instead of taking the vertex-colour branch"),
            UYorimichiFoliageBuilder::ExportSource(Source,{},TEXT("roles"),TEXT("mixed"),Path));
        for (const auto C:Corners) Stored.GetVertexInstanceColors()[C]=FVector4f(.9f,.65f,.1f,1.f);
    }
    IFileManager::Get().Delete(*Path);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageAuthoredLODsTest,"Yorimichi.Foliage.AuthoredLODs",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageAuthoredLODsTest::RunTest(const FString&)
{
    auto* Material=UMaterial::GetDefaultMaterial(MD_Surface);
    auto* Source=NewObject<UStaticMesh>();Source->SetNumSourceModels(1);
    TStrongObjectPtr<UStaticMesh> KeepSource(Source);
    Source->GetStaticMaterials().Add(FStaticMaterial(Material,TEXT("Flat")));
    FMeshDescription D;FStaticMeshAttributes A(D);A.Register();
    A.GetVertexInstanceUVs().SetNumChannels(1);
    const auto Group=D.CreatePolygonGroup();A.GetPolygonGroupMaterialSlotNames()[Group]=TEXT("Flat");
    TArray<FVertexInstanceID> Corners;
    for (int32 I=0;I<3;++I)
    {
        const auto V=D.CreateVertex();A.GetVertexPositions()[V]=FVector3f(I==1?100.f:0.f,I==2?100.f:0.f,0.f);
        const auto C=D.CreateVertexInstance(V);A.GetVertexInstanceNormals()[C]=FVector3f(0,0,1);Corners.Add(C);
    }
    D.CreateTriangle(Group,Corners);
    UStaticMesh::FBuildMeshDescriptionsParams Params;
    if (!TestTrue(TEXT("Fixture source builds"),Source->BuildFromMeshDescriptions({&D},Params))) return false;
    TArray<FString> Levels;
    for (int32 L=0;L<4;++L)
    {
        TArray<FString> Vertices,Faces;
        for (int32 I=0;I<16;++I)
        {
            // Eight thin triangles with complete opposite-winding back faces.
            // Each LOD has distinct positions and UVs, so counts alone cannot pass.
            for (int32 C=0;C<3;++C)
            {
                const int32 Corner=I%2 && C>0?3-C:C;
                const float X=L*10000.f+(I/2)*200.f+(Corner==1?100.f:0.f);
                Vertices.Add(FString::Printf(TEXT("{\"p\":[%.2f,%.2f,0],\"n\":[0,0,%d],\"uv\":[%.6f,0],\"c\":[1,1,1,1]}"),
                    X,Corner==2?100.:0.,I%2?-1:1,.03125+L*.125));
            }
            Faces.Add(FString::Printf(TEXT("{\"s\":0,\"v\":[%d,%d,%d]}"),I*3,I*3+1,I*3+2));
        }
        Levels.Add(TEXT("{\"vertices\":[")+FString::Join(Vertices,TEXT(","))+TEXT("],\"faces\":[")+FString::Join(Faces,TEXT(","))+TEXT("]}"));
    }
    const FString Path=FPaths::ConvertRelativePathToFull(FPaths::ProjectDir()/TEXT("../../../build/yorimichi/foliage-tests/authored-lods.json"));
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path),true);
    const FString Json=TEXT("{\"source\":\"")+Source->GetPathName()+TEXT("\",\"screens\":[1,0.24,0.07,0.018],\"levels\":[")+
        FString::Join(Levels,TEXT(","))+TEXT("],\"shadow\":")+Levels[0]+TEXT("}");
    if (!TestTrue(TEXT("Fixture product saved"),FFileHelper::SaveStringToFile(Json,*Path))) return false;
    // A test-only mount keeps persisted fixtures outside the game's cook inventory.
    // Keep the files available for the editor's queued save validation too.
    const FString PackageDirectory=FPaths::GetPath(Path)/TEXT("packages/");
    IFileManager::Get().MakeDirectory(*PackageDirectory,true);
    FPackageName::RegisterMountPoint(TEXT("/FoliageRegression/"),PackageDirectory);
    const FString Destination=TEXT("/FoliageRegression/AuthoredLODs")+FGuid::NewGuid().ToString(EGuidFormats::Digits);
    auto Check=[&](UStaticMesh* Mesh)
    {
        if (!TestNotNull(TEXT("Prepared variant builds"),Mesh)) return false;
        const auto* Data=Mesh->GetRenderData();
        if (!TestTrue(TEXT("Four prepared LODs survive"),Data && Data->LODResources.Num()==4)) return false;
        for (int32 L=0;L<4;++L)
        {
            const auto& LOD=Data->LODResources[L];
            TestEqual(TEXT("Exact thin front/back triangle set retained"),LOD.GetNumTriangles(),uint32(16));
            float MinX=TNumericLimits<float>::Max();
            for (uint32 V=0;V<LOD.VertexBuffers.PositionVertexBuffer.GetNumVertices();++V)
            {
                MinX=FMath::Min(MinX,LOD.VertexBuffers.PositionVertexBuffer.VertexPosition(V).X);
                TestTrue(TEXT("Prepared UVs come from this LOD"),FMath::IsNearlyEqual(
                    float(LOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(V,0).X),.03125f+L*.125f));
            }
            TestEqual(TEXT("Prepared positions come from this LOD"),MinX,L*10000.f);
            TestTrue(TEXT("Prepared material identity retained"),Mesh->GetMaterial(0)==Material);
        }
        return true;
    };
    auto* Mesh=UYorimichiFoliageBuilder::BuildVariant(Source,Path,Destination,Material,Material,false);
    if (!Check(Mesh)) return false;
    for (int32 L=0;L<4;++L)
    {
        auto& Reduction=Mesh->GetSourceModel(L).ReductionSettings;
        Reduction.PercentTriangles=.25f;Reduction.PercentVertices=.25f;
        Reduction.MaxNumOfTriangles=4;Reduction.MaxNumOfVerts=6;Reduction.BaseLODModel=0;
    }
    Check(UYorimichiFoliageBuilder::BuildVariant(Source,Path,Destination,Material,Material,false));
    // Rebuild a persisted, unloaded old product too. SavePackages fully loads
    // its destination, which used to overwrite edits made to a fresh placeholder.
    for (int32 L=0;L<4;++L)
    {
        auto& Model=Mesh->GetSourceModel(L);
        Model.ReductionSettings.BaseLODModel=0;
        Model.ReductionSettings.PercentTriangles=FMath::Pow(.5f,L);
        Model.BuildSettings.bRemoveDegenerates=true;
    }
    Mesh->Build(false);FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    const auto& OldPositions=Mesh->GetRenderData()->LODResources[3].VertexBuffers.PositionVertexBuffer;
    float OldMinX=TNumericLimits<float>::Max();
    for (uint32 V=0;V<OldPositions.GetNumVertices();++V)OldMinX=FMath::Min(OldMinX,OldPositions.VertexPosition(V).X);
    TestEqual(TEXT("Old product actually uses the wrong base geometry"),OldMinX,0.f);
    auto* Package=Mesh->GetOutermost();
    if (!TestTrue(TEXT("Old product saves"),UEditorLoadingAndSavingUtils::SavePackages({Package},false))) return false;
    Mesh=nullptr;
    if (!TestTrue(TEXT("Old product unloads"),UPackageTools::UnloadPackages({Package}))) return false;
    Package=nullptr;
    const FString ObjectPath=Destination+TEXT(".")+FPackageName::GetLongPackageAssetName(Destination);
    if (!TestNull(TEXT("Old product is no longer loaded"),FindObject<UStaticMesh>(nullptr,*ObjectPath))) return false;
    Mesh=UYorimichiFoliageBuilder::BuildVariant(Source,Path,Destination,Material,Material,false);
    if (!Check(Mesh)) return false;
    if (!TestTrue(TEXT("Rebuilt persisted product saves"),UEditorLoadingAndSavingUtils::SavePackages({Mesh->GetOutermost()},false))) return false;
    // Saving must retain the prepared levels, rather than reload the old ones.
    if (!Check(Mesh)) return false;
    Package=Mesh->GetOutermost();Mesh=nullptr;
    if (!TestTrue(TEXT("Rebuilt product unloads"),UPackageTools::UnloadPackages({Package}))) return false;
    Package=nullptr;
    Check(LoadObject<UStaticMesh>(nullptr,*ObjectPath));
    auto* Shadow=UYorimichiFoliageBuilder::BuildVariant(Source,Path,Destination+TEXT("Shadow"),Material,Material,true);
    if (TestNotNull(TEXT("Shadow variant builds"),Shadow))
    {
        TestEqual(TEXT("Shadow has its single supplied level"),Shadow->GetNumLODs(),1);
        TestEqual(TEXT("Shadow retains supplied faces"),Shadow->GetRenderData()->LODResources[0].GetNumTriangles(),uint32(16));
    }
    return true;
}
#endif
