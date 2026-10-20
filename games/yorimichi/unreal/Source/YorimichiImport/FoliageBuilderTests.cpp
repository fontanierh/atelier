#include "FoliageBuilder.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Engine/StaticMesh.h"
#include "StaticMeshAttributes.h"
#include "MeshDescription.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageImportRolesTest,"Yorimichi.Foliage.ImportRoles",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageImportRolesTest::RunTest(const FString&)
{
    auto* Mesh=NewObject<UStaticMesh>();
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
    D.CreateTriangle(Group,Corners);Mesh->CreateMeshDescription(0,MoveTemp(D));
    TestTrue(TEXT("Valid imported thin foliage role certifies"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    TestEqual(TEXT("Cooked slot advertises foliage"),Mesh->GetStaticMaterials()[0].MaterialSlotName,FName(TEXT("FoliageRoles_TH_flat")));
    TestEqual(TEXT("Imported binding identity remains exact"),Mesh->GetStaticMaterials()[0].ImportedMaterialSlotName,Imported);
    TestTrue(TEXT("Certification is idempotent"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    auto* Stored=Mesh->GetMeshDescription(0);FStaticMeshAttributes B(*Stored);auto Channels=B.GetVertexInstanceUVs();
    TestTrue(TEXT("Visible texture coordinates preserved"),Channels.Get(Corners[0],0)==FVector2f(.2f,.3f));
    for (const auto C:Corners)Channels.Set(C,5,FVector2f(3.f,-72.125f));
    TestTrue(TEXT("Explicit authored surfaces certify"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    TestEqual(TEXT("Authored policy is discoverable"),Mesh->GetStaticMaterials()[0].MaterialSlotName,FName(TEXT("FoliageAuthored_TH_flat")));
    Channels.Set(Corners[0],5,FVector2f(3.f,0.f));
    TestFalse(TEXT("Partial role channel refuses"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    for (const auto C:Corners)Channels.Set(C,5,FVector2f::ZeroVector);
    TestTrue(TEXT("Removing authoring roles clears cooked stamp"),UYorimichiFoliageBuilder::StampSourceRoles(Mesh));
    TestEqual(TEXT("Original cooked slot restored"),Mesh->GetStaticMaterials()[0].MaterialSlotName,Imported);
    return true;
}
#endif
