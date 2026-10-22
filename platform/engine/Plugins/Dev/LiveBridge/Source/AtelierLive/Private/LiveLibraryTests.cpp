#include "LiveLibrary.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "UObject/StrongObjectPtr.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FLiveStaticVerticesCPUOwnershipTest,"AtelierLive.StaticVerticesCPUOwnership",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FLiveStaticVerticesCPUOwnershipTest::RunTest(const FString&)
{
    TStrongObjectPtr<UStaticMesh> Asset(NewObject<UStaticMesh>());
    Asset->SetRenderData(MakeUnique<FStaticMeshRenderData>());
    Asset->GetRenderData()->LODResources.Add(new FStaticMeshLODResources);
    auto& Buffer=Asset->GetRenderData()->LODResources[0].VertexBuffers.PositionVertexBuffer;
    Buffer.Init(3,true);
    const FVector3f Points[3]={FVector3f(0,0,0),FVector3f(100,0,0),FVector3f(0,100,0)};
    for (uint32 I=0;I<3;++I) Buffer.VertexPosition(I)=Points[I];
    TStrongObjectPtr<UStaticMeshComponent> Component(NewObject<UStaticMeshComponent>());
    Component->SetStaticMesh(Asset.Get());Component->SetWorldLocation(FVector(300,400,500));
    const auto Positions=ULiveLibrary::StaticVertices(Component.Get());
    if (!TestEqual(TEXT("Owned CPU positions remain readable"),Positions.Num(),3)) return false;
    for (int32 I=0;I<3;++I)
        TestTrue(TEXT("Component transform is preserved"),Positions[I].Equals(FVector(Points[I])+FVector(300,400,500)));
    Buffer.CleanUp();
    TestFalse(TEXT("Position CPU storage released"),Buffer.GetAllowCPUAccess());
    TestEqual(TEXT("Cached vertex count survives cleanup"),Buffer.GetNumVertices(),uint32(3));
    TestTrue(TEXT("Released CPU positions refuse live inspection"),ULiveLibrary::StaticVertices(Component.Get()).IsEmpty());
    TestTrue(TEXT("Missing component refuses live inspection"),ULiveLibrary::StaticVertices(nullptr).IsEmpty());
    return true;
}
#endif
