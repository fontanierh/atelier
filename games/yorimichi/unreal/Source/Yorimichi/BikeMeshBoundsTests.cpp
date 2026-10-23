#include "AtomicMeshBounds.h"
#include "BikeMeshComponent.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Misc/AutomationTest.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "UObject/StrongObjectPtr.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBikeAtomicBoundsTest,"Yorimichi.Bike.AtomicLogicalBounds",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FBikeAtomicBoundsTest::RunTest(const FString&)
{
    TArray<TStrongObjectPtr<UStaticMesh>> Owners;
    TArray<UStaticMesh*> Parts;
    const TArray<TArray<FVector3f>> Positions{{{0.f,1.f,0.f}},{{4.f,1.f,0.f}},{{2.f,0.f,0.f}},{{2.f,2.f,0.f}}};
    for (int32 Index=0;Index<4;++Index)
    {
        // Exact names participate in production membership. A private transient outer
        // makes them unique without changing that original finite roster.
        UObject* Outer=NewObject<UObject>();
        Owners.Emplace(NewObject<UStaticMesh>(Outer,UBikeMeshComponent::SteeringNames()[Index]));
        UStaticMesh* Mesh=Owners.Last().Get();auto Data=MakeUnique<FStaticMeshRenderData>();
        auto* Lod=new FStaticMeshLODResources();Data->LODResources.Add(Lod);
        Lod->VertexBuffers.PositionVertexBuffer.Init(Positions[Index],true);Mesh->SetRenderData(MoveTemp(Data));Parts.Add(Mesh);
    }
    FBoxSphereBounds Bound(ForceInit);
    TestTrue(TEXT("Complete actual position buffers observed"),AtomicMeshBounds::MeasureLod0PartsBounds(Parts,Bound));
    TestEqual(TEXT("Exact float32 center"),Bound.Origin,FVector(2.,1.,0.));
    TestEqual(TEXT("Exact float32 extent"),Bound.BoxExtent,FVector(2.,1.,0.));
    TestEqual(TEXT("True vertex sphere differs from diagonal sqrt5"),Bound.SphereRadius,2.);
    TestTrue(TEXT("Complete named group persists"),UBikeMeshComponent::PrepareSteeringBounds(Parts));
    FBoxSphereBounds Saved(ForceInit);
    TestTrue(TEXT("All four persisted group records agree"),UBikeMeshComponent::ReadGroupBounds(Parts,Saved));
    TestEqual(TEXT("Persisted true sphere"),Saved.SphereRadius,2.);
    auto Duplicate=Parts;Duplicate[3]=Parts[0];
    TestFalse(TEXT("Duplicate geometry cannot certify group bounds"),AtomicMeshBounds::MeasureLod0PartsBounds(Duplicate,Saved));
    TestFalse(TEXT("Duplicate named membership refuses"),UBikeMeshComponent::PrepareSteeringBounds(Duplicate));
    auto Missing=Parts;Missing.Pop();
    TestFalse(TEXT("Missing member cannot use stored records"),UBikeMeshComponent::ReadGroupBounds(Missing,Saved));
    TStrongObjectPtr<UBikeMeshComponent> Component(NewObject<UBikeMeshComponent>());
    Component->SetLogicalBounds(Bound);Component->BoundsScale=1.f;
    TestTrue(TEXT("Typed actual logical override exposed"),Component->HasLogicalBoundsOverride());
    TestEqual(TEXT("CalcBounds keeps true sphere"),Component->CalcBounds(FTransform::Identity).SphereRadius,2.);
    Component->BoundsScale=2.f;
    TestEqual(TEXT("Original BoundsScale applies to sphere"),Component->CalcBounds(FTransform::Identity).SphereRadius,4.);
    return true;
}
#endif
