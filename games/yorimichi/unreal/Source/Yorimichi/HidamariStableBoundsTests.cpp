#include "HidamariStable.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Misc/AutomationTest.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/StrongObjectPtr.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FStableSelectedLodBoundsTest,"Yorimichi.Stable.SelectedLodBounds",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FStableSelectedLodBoundsTest::RunTest(const FString&)
{
    TStrongObjectPtr<UStaticMesh> Mesh(NewObject<UStaticMesh>());
    auto Data = MakeUnique<FStaticMeshRenderData>();
    for (const TArray<FVector3f>& Positions : {TArray<FVector3f>{{1.f,2.f,3.f},{5.f,7.f,11.f}},
        TArray<FVector3f>{{-100.f,-200.f,-300.f},{200.f,300.f,400.f}}})
    {
        auto* Lod = new FStaticMeshLODResources();
        Data->LODResources.Add(Lod);
        Lod->VertexBuffers.PositionVertexBuffer.Init(Positions, true);
    }
    Data->Bounds = FBoxSphereBounds(FBox(FVector(-100.,-200.,-300.),FVector(200.,300.,400.)));
    Mesh->SetRenderData(MoveTemp(Data));
    auto Read = [this](const FString& Json)
    {
        TSharedPtr<FJsonObject> Result;
        TestTrue(TEXT("Observed selected-LOD AABB is valid JSON"),FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Result));
        return Result;
    };
    const auto Base = Read(UHidamariStableMeshComponent::MeasureLodBounds(Mesh.Get(),0));
    const auto Lower = Read(UHidamariStableMeshComponent::MeasureLodBounds(Mesh.Get(),1));
    if (!Base || !Lower) return false;
    TestEqual(TEXT("Outlying lower LOD does not widen LOD0 minimum"),Base->GetArrayField(TEXT("min"))[0]->AsNumber(),1.);
    TestEqual(TEXT("LOD0 maximum is its actual render vertex"),Base->GetArrayField(TEXT("max"))[2]->AsNumber(),11.);
    TestEqual(TEXT("Requested lower LOD retains its own outlying minimum"),Lower->GetArrayField(TEXT("min"))[0]->AsNumber(),-100.);
    TestEqual(TEXT("Requested lower LOD retains its own outlying maximum"),Lower->GetArrayField(TEXT("max"))[2]->AsNumber(),400.);
    TestTrue(TEXT("Negative LOD refuses"),UHidamariStableMeshComponent::MeasureLodBounds(Mesh.Get(),-1).IsEmpty());
    TestTrue(TEXT("Missing LOD refuses"),UHidamariStableMeshComponent::MeasureLodBounds(Mesh.Get(),2).IsEmpty());
    TestTrue(TEXT("Missing render data refuses"),UHidamariStableMeshComponent::MeasureLodBounds(NewObject<UStaticMesh>(),0).IsEmpty());
    return true;
}
#endif
