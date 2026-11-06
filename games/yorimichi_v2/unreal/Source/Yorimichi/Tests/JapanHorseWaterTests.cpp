#include "HorseComponent.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "AdventureMoveSet.h"
#include "WandererCharacter.h"
#include "JapanWorld.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/ScopeExit.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanHorseWaterTest, "Yorimichi.Network.HorseWater",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanHorseWaterTest::RunTest(const FString&)
{
    UWorld* TestWorld = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { TestWorld = Context.World(); break; }
    if (!TestNotNull(TEXT("Water regression uses a native game world"), TestWorld)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = TestWorld->SpawnActor<AWandererCharacter>(FVector(0, 0, 100000), FRotator::ZeroRotator, Spawn);
    auto* Landscape = TestWorld->SpawnActor<AJapanWorld>(Spawn);
    ON_SCOPE_EXIT { if (Rider) Rider->Destroy(); if (Landscape) Landscape->Destroy(); };
    if (!TestNotNull(TEXT("Deferred rider exists"), Rider) || !TestNotNull(TEXT("Authored water fixture exists"), Landscape)) return false;
    // Deferred actors avoid loading art. Use the real game water query and movement component without any physics volume.
    Rider->EnterWorld(Landscape);
    Rider->Moves = NewObject<UAdventureMoveSet>(Rider);
    Rider->Moves->Character = Rider;
    auto* Horse = Rider->GetHorse(); Horse->Rider = Rider;
    auto* Movement = Rider->GetCharacterMovement();
    Movement->SetUpdatedComponent(Rider->GetCapsuleComponent()); Movement->Activate(true);
    Landscape->bForestLakeLoaded = true;
    Landscape->ForestLakeCenter = FVector(50000, -10000, 300);
    Landscape->ForestLakeRadii = FVector2D(1000, 800);
    const float Friction = Movement->GroundFriction, Braking = Movement->BrakingDecelerationWalking;
    auto Check = [&](const TCHAR* Label, FVector Feet, EMovementMode Mode, bool Ends)
    {
        const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        Rider->SetActorLocation(Feet + FVector(0, 0, Half), false, nullptr, ETeleportType::TeleportPhysics);
        Movement->SetMovementMode(Mode);
        Horse->Phase = UHorseComponent::EPhase::Mounting; Horse->Role = EHorseRole::Mount;
        Horse->PhaseTime = 0.f; Horse->bTerminal = false; Horse->Speed = 600.f;
        Horse->HoldFriction();
        TestFalse(TEXT("Authored water has no Unreal swimming mode"), Movement->IsSwimming());
        TestEqual(Label, Horse->AdvanceSimulation(1.f / 60.f, FHorseInput()), !Ends);
        Horse->StowImmediately();
        TestEqual(TEXT("Water exit restores walking friction"), Movement->GroundFriction, Friction);
        TestEqual(TEXT("Water exit restores walking braking"), Movement->BrakingDecelerationWalking, Braking);
        TestFalse(TEXT("Stow ends the ride"), Horse->IsEquipped());
    };
    for (const float Scale : {1.f, 1.4f})
    {
        Rider->GetCapsuleComponent()->SetWorldScale3D(FVector(Scale));
        const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        Check(TEXT("Dry land below sea level keeps the horse"), FVector(50000, 10000, -200), MOVE_Walking, false);
        Check(TEXT("Sea shallows keep the horse"), FVector(0, 10000, -Half * 1.1f + .5f), MOVE_Walking, false);
        Check(TEXT("Deep sea ends the ride before custom swimming starts"), FVector(0, 10000, -Half * 1.1f - .5f), MOVE_Walking, true);
        Check(TEXT("Falling just above swim depth keeps the horse"), FVector(0, 10000, -9), MOVE_Falling, false);
        Check(TEXT("Falling into the sea ends the ride"), FVector(0, 10000, -11), MOVE_Falling, true);
        Check(TEXT("Lake shallows use the raised surface"), FVector(50000, -10000, 300 - Half * 1.1f + .5f), MOVE_Walking, false);
        Check(TEXT("Deep lake ends the ride"), FVector(50000, -10000, 300 - Half * 1.1f - .5f), MOVE_Walking, true);
        Check(TEXT("Outside the lake shoreline keeps the horse"), FVector(52000, -10000, 0), MOVE_Walking, false);
    }
    return true;
}
#endif
