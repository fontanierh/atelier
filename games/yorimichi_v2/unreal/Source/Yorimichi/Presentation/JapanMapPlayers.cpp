#include "JapanMap.h"
#include "JapanSession.h"
#include "JapanNetwork.h"
#include "JapanGameplayCollision.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/World.h"

namespace
{
AWandererCharacter* FindPlayer(UWorld* World, const FString& Id)
{
    const auto* State = World ? World->GetGameState<AJapanGameState>() : nullptr;
    if (!State || Id.IsEmpty()) return nullptr;
    for (const auto& Entry : State->PlayerArray)
        if (const auto* Player = Cast<AJapanPlayerState>(Entry); Player && Player->bWorldReady && Player->SessionPlayerId == Id)
            return Cast<AWandererCharacter>(Player->GetPawn());
    return nullptr;
}

bool HasPlayerClearance(const AWandererCharacter* Traveller, const AWandererCharacter* Peer, const FVector& Ground)
{
    const auto* Capsule = Traveller->GetCapsuleComponent();
    const auto* Standing = Traveller->GetClass()->GetDefaultObject<AWandererCharacter>()->GetCapsuleComponent();
    const float Half = FMath::Max(Capsule->GetUnscaledCapsuleHalfHeight(),Standing->GetUnscaledCapsuleHalfHeight())*Capsule->GetShapeScale();
    const float Radius = FMath::Max(Capsule->GetUnscaledCapsuleRadius(),Standing->GetUnscaledCapsuleRadius())*Capsule->GetShapeScale();
    // Ground selection ignores moving actors. Clearance must retain them: a
    // train body or another moving obstruction can occupy otherwise safe ground.
    FCollisionQueryParams Clearance(SCENE_QUERY_STAT(PlayerMapClearance),false,Traveller);
    Clearance.AddIgnoredActor(Peer);
    // Online Pawn overlap customizes the profile; a named-profile lookup would
    // fall back to WorldStatic/default responses. Use the live collision mask.
    return !Traveller->GetWorld()->OverlapBlockingTestByChannel(Ground+FVector(0,0,Half+3), FQuat::Identity,
        Capsule->GetCollisionObjectType(), FCollisionShape::MakeCapsule(Radius,Half), Clearance,
        FCollisionResponseParams(Capsule->GetCollisionResponseToChannels()));
}

}

void UJapanMap::RefreshPlayerZones() const
{
    TSet<FString> Present;
    const auto* State = Owner ? Owner->GetWorld()->GetGameState<AJapanGameState>() : nullptr;
    if (State) for (const auto& Entry : State->PlayerArray)
    {
        const auto* Player = Cast<AJapanPlayerState>(Entry);
        auto* Pawn = Player && Player->bWorldReady && !Player->SessionPlayerId.IsEmpty() ? Cast<AWandererCharacter>(Player->GetPawn()) : nullptr;
        if (!IsValid(Pawn) || Pawn == Owner || !Pawn->IsReady() || Pawn->IsNpc()) continue;
        const FString Key = TEXT("player_") + Player->SessionPlayerId;
        Present.Add(Key);
        auto* Zone = Zones.FindByPredicate([&](const FJapanMapZone& Z) { return Z.Key == Key; });
        if (!Zone) Zone = &Zones.AddDefaulted_GetRef();
        Zone->Key = Key;
        Zone->Name = Player->RiderName.IsEmpty() ? TEXT("Player") : Player->RiderName;
        Zone->Hint = TEXT("Online player · teleport nearby");
        Zone->Location = Pawn->GetActorLocation();
        Zone->Yaw = Pawn->GetActorRotation().Yaw;
    }
    Zones.RemoveAll([&](const FJapanMapZone& Z) { return Z.Key.StartsWith(TEXT("player_")) && !Present.Contains(Z.Key); });
}

void AWandererCharacter::ServerTravelToPlayer_Implementation(const FString& Id, uint32 Epoch)
{
    if (Epoch != NetworkActivity.Epoch || !bReady || Id.Len() > 128) return;
    auto* Peer = FindPlayer(GetWorld(), Id);
    if (!IsValid(Peer) || Peer == this || !Peer->IsReady())
    { ClientActivityRejected(TEXT("That player is no longer available.")); return; }
    // Choose actual walkable ground near the current authoritative position,
    // including below an airborne rider. Never copy a stale client map position.
    auto Params = JapanGameplayCollision::Query(GetWorld(), SCENE_QUERY_STAT(PlayerMapTravel), false);
    Params.AddIgnoredActor(this); Params.AddIgnoredActor(Peer);
    for (int32 I = 0; I < 8; ++I)
    {
        const float Angle = Peer->GetActorRotation().Yaw + 45.f * I;
        const FVector Near = Peer->GetActorLocation() + FRotator(0,Angle,0).Vector()*180.f;
        FHitResult Hit;
        if (!GetWorld()->LineTraceSingleByChannel(Hit, Near+FVector(0,0,100), Near-FVector(0,0,100000), JapanGameplayCollision::Channel, Params) ||
            !GetCharacterMovement()->IsWalkable(Hit) || !HasPlayerClearance(this,Peer,Hit.ImpactPoint)) continue;
        // Reuse encounter, pending-hit, epoch and travel-rate admission. The
        // short trace retains the selected floor beneath bridges and roofs.
        if (PerformNetworkTravel(Hit.ImpactPoint, Peer->GetActorRotation().Yaw, Epoch, 30.f)) ClientPlayerTravelled();
        return;
    }
    ClientActivityRejected(TEXT("There is no safe ground near that player just now."));
}

void AWandererCharacter::ClientPlayerTravelled_Implementation()
{
    if (GetMap()) GetMap()->Close();
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Components/BoxComponent.h"
#include "Engine/Engine.h"
#include "Misc/ScopeExit.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayerMapClearanceTest, "Yorimichi.Network.PlayerTravelClearance",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FPlayerMapClearanceTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World=Context.World(); break; }
    if (!TestNotNull(TEXT("Native world"),World)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Traveller = World->SpawnActor<AWandererCharacter>(Spawn);
    auto* Peer = World->SpawnActor<AWandererCharacter>(Spawn);
    auto* Obstruction = World->SpawnActor<AActor>(Spawn);
    ON_SCOPE_EXIT
    {
        if (Traveller) Traveller->Destroy();
        if (Peer) Peer->Destroy();
        if (Obstruction) Obstruction->Destroy();
    };
    if (!Traveller || !Peer || !Obstruction) return false;
    JapanNetwork::ConfigurePlayerCollision(Traveller->GetCapsuleComponent());
    const FVector Ground(300000,200000,10000);
    auto* Box = NewObject<UBoxComponent>(Obstruction);
    Obstruction->SetRootComponent(Box);
    Box->SetMobility(EComponentMobility::Movable);
    Box->SetBoxExtent(FVector(45,45,100));
    Box->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    Box->SetCollisionObjectType(ECC_WorldDynamic);
    Box->SetCollisionResponseToAllChannels(ECR_Block);
    Box->SetCollisionResponseToChannel(JapanGameplayCollision::Channel,ECR_Ignore);
    Box->SetCollisionResponseToChannel(ECC_WorldStatic,ECR_Ignore);
    Box->SetWorldLocation(Ground+FVector(0,0,75)); Box->RegisterComponent();
    TestFalse(TEXT("An online custom capsule detects Pawn blockers that ignore WorldStatic and fixed geometry"),HasPlayerClearance(Traveller,Peer,Ground));
    TestTrue(TEXT("A clear nearby candidate is still available"),HasPlayerClearance(Traveller,Peer,Ground+FVector(180,0,0)));
    Traveller->GetCapsuleComponent()->SetCapsuleHalfHeight(45);
    Box->SetBoxExtent(FVector(45,45,10)); Box->SetWorldLocation(Ground+FVector(0,0,130));
    TestFalse(TEXT("Crouching does not bypass standing headroom"),HasPlayerClearance(Traveller,Peer,Ground));
    Box->SetWorldLocation(Ground+FVector(1000,0,0));
    TestTrue(TEXT("Moving obstruction away restores the candidate"),HasPlayerClearance(Traveller,Peer,Ground));
    return true;
}
#endif
