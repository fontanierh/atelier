#include "JapanMap.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanMapSalonTest, "Yorimichi.Map.SalonLanding",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanMapSalonTest::RunTest(const FString&)
{
    AWandererCharacter* Player = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (UWorld* World = Context.World(); World && World->IsGameWorld())
            if (auto* Controller = World->GetFirstPlayerController()) Player = Cast<AWandererCharacter>(Controller->GetPawn());
    if (!TestNotNull(TEXT("Run after the guarded game is ready"), Player)) return false;
    UJapanMap* Map = Player->GetMap();
    if (!TestTrue(TEXT("The production map is loaded"), Map && Map->IsLoaded())) return false;
    const FJapanMapZone* Salon = Map->FindZone(TEXT("belmonte_salon"));
    if (!TestNotNull(TEXT("The generated map includes the salon"), Salon)) return false;
    const FJapanMapZone Zone = *Salon; // GetZones can refresh its array during travel.
    const auto* Capsule = Player->GetCapsuleComponent();
    const float Half = Capsule->GetScaledCapsuleHalfHeight();
    const FVector OriginalGround = Player->GetActorLocation() - FVector(0,0,Half);
    const float OriginalYaw = Player->GetActorRotation().Yaw, Health = Player->GetSword()->GetHealth();
    ON_SCOPE_EXIT { Player->TravelTo(OriginalGround,OriginalYaw,TEXT("map regression return"),30.f); };
    auto Feet = [&] { return Player->GetActorLocation() - FVector(0,0,Half); };
    auto OnFloor = [&]
    {
        FHitResult Hit;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(SalonMapRegression),false,Player);
        const FVector Position = Feet();
        TestTrue(TEXT("The destination is the hall floor"), FMath::Abs(Position.Z-Zone.Location.Z) < 20.f);
        TestTrue(TEXT("Travel retains the stop position"), FVector::Dist2D(Position,Zone.Location) < 1.f);
        TestTrue(TEXT("The player faces the counters"), FMath::Abs(FMath::FindDeltaAngleDegrees(Player->GetActorRotation().Yaw,Zone.Yaw)) < .1f);
        TestTrue(TEXT("The floor is walkable"), Player->GetWorld()->LineTraceSingleByChannel(Hit,Position+FVector(0,0,5),
            Position-FVector(0,0,50),ECC_Visibility,Params) && Player->GetCharacterMovement()->IsWalkable(Hit));
        TestFalse(TEXT("The standing capsule has clear space"), Player->GetWorld()->OverlapBlockingTestByChannel(
            Player->GetActorLocation(),FQuat::Identity,Capsule->GetCollisionObjectType(),
            FCollisionShape::MakeCapsule(Capsule->GetScaledCapsuleRadius(),Half),Params,
            FCollisionResponseParams(Capsule->GetCollisionResponseToChannels())));
        TestEqual(TEXT("Travel preserves health"), Player->GetSword()->GetHealth(), Health);
    };
    TestEqual(TEXT("Indoor clearance is converted from metres"), Zone.Above, 150.f);
    TestEqual(TEXT("Other zones keep the 25 m default"), FJapanMapZone().Above, 2500.f);
    if (!TestTrue(TEXT("Outdoor-height control travels"), Player->TravelTo(Zone.Location,Zone.Yaw,TEXT("salon roof control")))) return false;
    TestTrue(TEXT("The old outdoor trace hits the roof"), Feet().Z > Zone.Location.Z+500.f);
    if (!TestTrue(TEXT("Map travel succeeds"), Map->TeleportToZone(Zone.Key))) return false;
    OnFloor();
    // Exercise the reflected host handler with the same clearance the generated RPC transports.
    Player->SetActorLocation(Player->GetActorLocation()+FVector(1000,0,0),false,nullptr,ETeleportType::TeleportPhysics);
    Player->ServerTravelTo(Zone.Location,Zone.Yaw,Player->GetActivityEpoch(),Zone.Above);
    OnFloor();
    const FVector Before = Player->GetActorLocation();
    TestFalse(TEXT("Negative trace height refuses travel"), Player->TravelTo(Zone.Location,0.f,TEXT("invalid trace"),-1.f));
    TestFalse(TEXT("Excessive trace height refuses travel"), Player->TravelTo(Zone.Location,0.f,TEXT("invalid trace"),6001.f));
    TestFalse(TEXT("NaN trace height refuses travel"), Player->TravelTo(Zone.Location,0.f,TEXT("invalid trace"),std::numeric_limits<float>::quiet_NaN()));
    TestFalse(TEXT("Infinite trace height refuses travel"), Player->TravelTo(Zone.Location,0.f,TEXT("invalid trace"),std::numeric_limits<float>::infinity()));
    TestTrue(TEXT("Invalid heights preserve the player"), Player->GetActorLocation().Equals(Before));
    return true;
}
#endif
