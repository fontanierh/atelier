#include "FoliagePreparation.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Engine/StaticMesh.h"
#include "HAL/FileManager.h"
#include "MeshDescription.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "StaticMeshAttributes.h"
#include "UObject/StrongObjectPtr.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMeshGeometrySnapshotTest,"Yorimichi.Foliage.GeometrySnapshot",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FMeshGeometrySnapshotTest::RunTest(const FString&)
{
    auto* Mesh=NewObject<UStaticMesh>();TStrongObjectPtr<UStaticMesh> Keep(Mesh);
    Mesh->SetNumSourceModels(1);
    Mesh->GetStaticMaterials().Add(FStaticMaterial(nullptr,TEXT("Slot")));
    FMeshDescription D;FStaticMeshAttributes A(D);A.Register();
    auto UV=A.GetVertexInstanceUVs();UV.SetNumChannels(2);
    const auto Group=D.CreatePolygonGroup();A.GetPolygonGroupMaterialSlotNames()[Group]=TEXT("Slot");
    TArray<FVertexInstanceID> Corners;
    for (int32 I=0;I<3;++I)
    {
        const auto V=D.CreateVertex();A.GetVertexPositions()[V]=FVector3f(float(I),float(I)+.25f,float(-I));
        const auto C=D.CreateVertexInstance(V);Corners.Add(C);
        A.GetVertexInstanceNormals()[C]=FVector3f(0,0,1);
        A.GetVertexInstanceColors()[C]=FVector4f(1,.5f,.25f,1);
        UV.Set(C,0,FVector2f(float(I)/2,0));UV.Set(C,1,FVector2f(.1f,.2f));
    }
    D.CreateTriangle(Group,Corners);Mesh->CreateMeshDescription(0,MoveTemp(D));
    const FString Path=FPaths::ProjectSavedDir()/TEXT("MeshGeometrySnapshotTest.bin");
    if (!TestTrue(TEXT("Stored geometry exports"),UYorimichiFoliagePreparation::ExportGeometrySnapshot(Mesh,Path))) return false;
    TArray<uint8> Bytes;
    if (!TestTrue(TEXT("Snapshot readable"),FFileHelper::LoadFileToArray(Bytes,*Path))) return false;
    // Independent Python struct.pack('<...') golden for exactly this fixture.
    const FString Expected=TEXT("4154454c4945522d4d4553482d310a01000000020000000100000000000000000000000000803e0000000000000000000000000000803f0000803f0000003f0000803e0000803f0000000000000000cdcccc3dcdcc4c3e0000803f0000a03f000080bf00000000000000000000803f0000803f0000003f0000803e0000803f0000003f00000000cdcccc3dcdcc4c3e0000004000001040000000c000000000000000000000803f0000803f0000003f0000803e0000803f0000803f00000000cdcccc3dcdcc4c3e");
    TestEqual(TEXT("Exact Python/native binary parity"),BytesToHex(Bytes.GetData(),Bytes.Num()).ToLower(),Expected);
    auto* Stored=Mesh->GetMeshDescription(0);FStaticMeshAttributes B(*Stored);
    B.GetVertexInstanceNormals()[Corners[0]]=FVector3f(1,0,0);
    TestTrue(TEXT("Changed geometry still exports"),UYorimichiFoliagePreparation::ExportGeometrySnapshot(Mesh,Path));
    TArray<uint8> Changed;FFileHelper::LoadFileToArray(Changed,*Path);
    TestTrue(TEXT("Normal mutation changes proof"),Changed!=Bytes);
    Stored->CreateVertex();
    TestFalse(TEXT("Unexpected topology refuses proof"),UYorimichiFoliagePreparation::ExportGeometrySnapshot(Mesh,Path));
    TestFalse(TEXT("Null mesh refuses proof"),UYorimichiFoliagePreparation::ExportGeometrySnapshot(nullptr,Path));
    IFileManager::Get().Delete(*Path);
    return true;
}
#endif
