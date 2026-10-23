#include "AtomicMeshBounds.h"
#include "BikeMeshComponent.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Misc/AutomationTest.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "MeshDescription.h"
#include "StaticMeshAttributes.h"
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
        Mesh->AddSourceModel();FMeshDescription Description;FStaticMeshAttributes Attributes(Description);Attributes.Register();
        TArray<FVertexInstanceID> Corners;
        for (int32 Corner=0;Corner<3;++Corner)
        {
            const FVertexID Vertex=Description.CreateVertex();Attributes.GetVertexPositions()[Vertex]=Positions[Index][0];
            Corners.Add(Description.CreateVertexInstance(Vertex));
        }
        Description.CreateTriangle(Description.CreatePolygonGroup(),Corners);
        Mesh->CreateMeshDescription(0,MoveTemp(Description));
    }
    FBoxSphereBounds Bound(ForceInit);
    TestTrue(TEXT("Complete actual source descriptions observed"),AtomicMeshBounds::MeasureLod0PartsBounds(Parts,Bound));
    TestEqual(TEXT("Exact imported center"),Bound.Origin,FVector(2.,1.,0.));
    TestEqual(TEXT("Exact imported extent"),Bound.BoxExtent,FVector(2.,1.,0.));
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
    TestFalse(TEXT("Missing component mesh cannot borrow group bounds"),Component->UseSavedSteeringBounds(Parts));
    Component->SetStaticMesh(Parts[0]);
    TestTrue(TEXT("Actual member uses complete saved group"),Component->UseSavedSteeringBounds(Parts));
    TestFalse(TEXT("Incomplete group refuses even with stored metadata"),Component->UseSavedSteeringBounds(Missing));
    TestFalse(TEXT("Refusal does not retain stale override"),Component->HasLogicalBoundsOverride());
    TestTrue(TEXT("Complete group configures again"),Component->UseSavedSteeringBounds(Parts));
    Component->BoundsScale=1.f;
    TestTrue(TEXT("Typed actual logical override exposed"),Component->HasLogicalBoundsOverride());
    TestEqual(TEXT("CalcBounds keeps true sphere"),Component->CalcBounds(FTransform::Identity).SphereRadius,2.);
    Component->BoundsScale=2.f;
    TestEqual(TEXT("Original BoundsScale applies to sphere"),Component->CalcBounds(FTransform::Identity).SphereRadius,4.);
    // The imported asset caches FMeshDescription::GetBounds in double precision;
    // float32 render bounds differ even for the same non-binary vertex positions.
    FMeshDescription Whole;FStaticMeshAttributes WholeAttributes(Whole);WholeAttributes.Register();
    for (int32 Index=0;Index<Parts.Num();++Index)
    {
        FMeshDescription* Description=Parts[Index]->GetMeshDescription(0);
        auto SourcePositions=FStaticMeshAttributes(*Description).GetVertexPositions();TArray<FVertexInstanceID> Corners;
        for (const FVertexID Vertex:Description->Vertices().GetElementIDs())
        {
            SourcePositions[Vertex]+=FVector3f(.1f*Index,.2f*Index,.3f*Index);
            const FVertexID Joined=Whole.CreateVertex();WholeAttributes.GetVertexPositions()[Joined]=SourcePositions[Vertex];
            Corners.Add(Whole.CreateVertexInstance(Joined));
        }
        Whole.CreateTriangle(Whole.CreatePolygonGroup(),Corners);
    }
    TestTrue(TEXT("Fractional imported union observed"),AtomicMeshBounds::MeasureLod0PartsBounds(Parts,Bound));
    const FBoxSphereBounds Expected=Whole.GetBounds();
    TestEqual(TEXT("Original engine description center"),Bound.Origin,Expected.Origin);
    TestEqual(TEXT("Original engine description extent"),Bound.BoxExtent,Expected.BoxExtent);
    TestEqual(TEXT("Original engine description true sphere"),Bound.SphereRadius,Expected.SphereRadius);
    return true;
}
#endif
