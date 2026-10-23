#include "NativeAtomicEquivalence.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAtomicRefusedProbeTest,
    "Yorimichi.AtomicMeshes.RefusedProbeIsUnavailable",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FAtomicRefusedProbeTest::RunTest(const FString&)
{
    auto Refusal=[](const FString& Text)
    {
        TSharedPtr<FJsonObject> Object;
        if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Object) || !Object)return FString();
        if(Object->HasField(TEXT("blocking")))return FString();
        FString Reason;Object->TryGetStringField(TEXT("refusal"),Reason);return Reason;
    };
    const FVector Start(0.,0.,1.),End(0.,0.,-1.);
    TestEqual(TEXT("Missing evidence is an explicit refusal, never a negative hit"),
        Refusal(UNativeAtomicEquivalence::Probe(nullptr,Start,End,FQuat::Identity,0.f,0.f,true)),
        FString(TEXT("missing_component")));
    auto* Component=NewObject<UStaticMeshComponent>();
    Component->SetStaticMesh(NewObject<UStaticMesh>());
    TestEqual(TEXT("Unregistered fixture components remain unavailable"),
        Refusal(UNativeAtomicEquivalence::Probe(Component,Start,End,FQuat::Identity,0.f,0.f,true)),
        FString(TEXT("unregistered_component")));
    return true;
}
#endif
