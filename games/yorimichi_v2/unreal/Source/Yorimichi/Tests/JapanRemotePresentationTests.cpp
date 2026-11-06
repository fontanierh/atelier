#include "HorseComponent.h"
#include "SkateComponent.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "WandererCharacter.h"
#include "JapanMap.h"
#include "JapanSession.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"
#include "Serialization/MemoryWriter.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRemoteVehiclePresentationTest, "Yorimichi.Network.RemotePresentation",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRemoteVehiclePresentationTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Native game world"), World)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = World->SpawnActor<AWandererCharacter>(FVector(20000,30000,10000), FRotator::ZeroRotator, Spawn);
    ON_SCOPE_EXIT { if (Rider) Rider->Destroy(); };
    if (!TestNotNull(TEXT("Deferred rider"), Rider)) return false;
    auto* Skate = Rider->GetSkate();
    Skate->Rider = Rider; Skate->bNetworkProxy = true;
    auto* Mesh = Rider->GetMesh();
    const FVector At = Rider->GetActorLocation();
    const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const FVector Base(0,0,-Half);
    Rider->CacheInitialMeshOffset(Base, FRotator(0,-90,0));
    for (bool HasBones : {true,false})
    {
        if (HasBones) Skate->RiderPose.Add(FTransform::Identity);
        else Skate->RiderPose.Reset();
        Mesh->SetAbsolute(true,true,true);
        Mesh->SetWorldLocation(FVector(-60000,5000,200));
        Skate->StowImmediately();
        Skate->ClearNetworkPose(); // Repeated releases are harmless.
        TestFalse(TEXT("Travel releases absolute position with or without bones"), Mesh->IsUsingAbsoluteLocation());
        TestFalse(TEXT("Travel releases absolute rotation"), Mesh->IsUsingAbsoluteRotation());
        TestTrue(TEXT("The body returns to its authored capsule frame"), Mesh->GetRelativeLocation().Equals(Base,.001));
        TestTrue(TEXT("Stow never moves the authoritative capsule"), Rider->GetActorLocation().Equals(At,.001));
        TestEqual(TEXT("A proxy never restores uninitialized local ride dimensions"), Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight(), Half);
        Rider->SetActorLocation(At+FVector(500,0,0));
        TestTrue(TEXT("The released mesh follows subsequent movement"), Mesh->GetComponentLocation().Equals(Rider->GetActorLocation()+Base,.001));
        Rider->SetActorLocation(At);
    }
    auto* Horse = Rider->GetHorse(); Horse->Rider = Rider; Horse->bAssetsReady = true;
    Horse->Phase = UHorseComponent::EPhase::Riding; Horse->Role = EHorseRole::Gallop;
    Horse->Speed = 900.f; Horse->GaitPhase = .8f;
    FJapanHorseState Before = Horse->CaptureNetworkState();
    FJapanHorseState Earlier = Before; Earlier.GaitPhase = .2f; Earlier.Speed = 500.f;
    Horse->ReceiveNetworkPresentation(Rider->GetActivityEpoch(), World->GetTimeSeconds(), Earlier);
    Horse->PresentNetwork(0.f); // Exercise sampling/restoration without loading art.
    FJapanHorseState After = Horse->CaptureNetworkState();
    TArray<uint8> A,B; FMemoryWriter WA(A),WB(B); Before.SerializeCheckpoint(WA); After.SerializeCheckpoint(WB);
    TestTrue(TEXT("Listen-host visual sampling leaves authoritative checkpoint byte-identical"), A == B);
    TestTrue(TEXT("Host rider animation consumes the buffered visual state"), Horse->HasPresentedNetworkState());
    TestEqual(TEXT("Presented clock differs from current authority clock"), Horse->PresentedNetworkState.GaitPhase, .2f);
    // A single stable session identity follows its replacement pawn and is
    // removed on departure, without opening the UI or loading world artwork.
    auto* OriginalState = World->GetGameState();
    auto* State = World->SpawnActor<AJapanGameState>(Spawn);
    auto* Player = World->SpawnActor<AJapanPlayerState>(Spawn);
    auto* Replacement = World->SpawnActor<AWandererCharacter>(At,FRotator::ZeroRotator,Spawn);
    ON_SCOPE_EXIT
    {
        World->SetGameState(OriginalState);
        if (Replacement) Replacement->Destroy();
        if (Player) Player->Destroy();
        if (State) State->Destroy();
    };
    if (!State || !Player || !Replacement) return false;
    World->SetGameState(State);
    State->PlayerArray.AddUnique(Player);
    Player->SessionPlayerId = TEXT("0123456789abcdef0123456789abcdef");
    Player->RiderName = TEXT("cairo"); Player->bWorldReady = true;
    Replacement->bReady = true; Replacement->SetPlayerState(Player);
    auto* Map = NewObject<UJapanMap>(Rider); Map->Owner = Rider;
    const FString Key = TEXT("player_")+Player->SessionPlayerId;
    TestEqual(TEXT("Joined peer contributes one map target"),Map->GetZones().Num(),1);
    Replacement->SetActorLocation(At+FVector(1300,900,0));
    const auto* Target = Map->FindZone(Key);
    TestTrue(TEXT("Moving peer updates its target"),Target && Target->Location.Equals(Replacement->GetActorLocation()));
    const auto AtlasTargets = Map->GetAtlasTargets();
    const auto* AtlasPeer = AtlasTargets.FindByPredicate([&](const FJapanAtlasTarget& T){return T.Key==Key;});
    TestTrue(TEXT("Atlas retains the live player category and travel identity"),AtlasPeer && AtlasPeer->Category==TEXT("player") && AtlasPeer->bTravel && AtlasPeer->Location.Equals(Replacement->GetActorLocation()));
    Replacement->SetPlayerState(nullptr); Rider->SetPlayerState(Player); Rider->bReady = true;
    Map->Owner = Replacement;
    Target = Map->FindZone(Key);
    TestTrue(TEXT("Character replacement retains identity and follows current pawn"),Target && Target->Location.Equals(Rider->GetActorLocation()));
    Player->bWorldReady = false;
    TestEqual(TEXT("A departed or unready peer is removed"),Map->GetZones().Num(),0);
    Player->bWorldReady = true;
    Map->Owner = Rider;
    TestEqual(TEXT("The local player never becomes a teleport target"),Map->GetZones().Num(),0);
    return true;
}
#endif
