#include "CitySurfaceValidation.h"
#include "BelmonteTrainService.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCurrentSimpleBoxValidation,"Yorimichi.AtomicMeshes.SimpleBoxValidation",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FCurrentSimpleBoxValidation::RunTest(const FString&)
{
    auto* Mesh=NewObject<UStaticMesh>();
    const FBox Box(FVector(-20,-30,-40),FVector(20,30,40));
    TestEqual(TEXT("Existing owner finisher creates original box"),UBelmonteTrainImportLibrary::SetSimpleBoxes(Mesh,{Box}),1);
    TestTrue(TEXT("Current created SimpleAsComplex box body"),UCitySurfaceValidation::ValidateSimpleBoxes(Mesh,1));
    TestFalse(TEXT("Wrong expected original shape count"),UCitySurfaceValidation::ValidateSimpleBoxes(Mesh,2));
    Mesh->LODForCollision=1;
    TestFalse(TEXT("Collision may not use a reduced render LOD"),UCitySurfaceValidation::ValidateSimpleBoxes(Mesh,1));
    Mesh->LODForCollision=0;auto* Body=Mesh->GetBodySetup();
    Body->AggGeom.SphereElems.Add(FKSphereElem(1.f));
    TestFalse(TEXT("Additional foreign simple shapes refuse"),UCitySurfaceValidation::ValidateSimpleBoxes(Mesh,1));
    TestEqual(TEXT("Existing finisher explicitly removes all collision from a render-only part"),UBelmonteTrainImportLibrary::SetSimpleBoxes(Mesh,{}),0);
    TestTrue(TEXT("Explicit zero-box part stays nonblocking"),UCitySurfaceValidation::ValidateSimpleBoxes(Mesh,0));
    Body->CollisionTraceFlag=CTF_UseComplexAsSimple;
    TestFalse(TEXT("Render-only part cannot silently acquire complex collision"),UCitySurfaceValidation::ValidateSimpleBoxes(Mesh,0));
    return true;
}
#endif
