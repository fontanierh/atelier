#include "HorseComponent.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/ScopeExit.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanHorseTurnTest, "Yorimichi.Horse.TurnInPlace",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanHorseTurnTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("A native game world exists"), World)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = World->SpawnActor<AWandererCharacter>(FVector(0, 0, 100000), FRotator::ZeroRotator, Spawn);
    ON_SCOPE_EXIT { if (Rider) Rider->Destroy(); };
    if (!TestNotNull(TEXT("Deferred rider avoids loading assets"), Rider)) return false;
    auto* Horse = Rider->GetHorse(); Horse->Rider = Rider;
    auto* Movement = Rider->GetCharacterMovement();
    Movement->SetUpdatedComponent(Rider->GetCapsuleComponent()); Movement->Activate(true);
    const FVector Start = Rider->GetActorLocation();
    auto Reset = [&]()
    {
        Horse->Phase = UHorseComponent::EPhase::Riding; Horse->Role = EHorseRole::Idle;
        Horse->Speed = Horse->Steering = Horse->GaitPhase = Horse->PhaseTime = 0.f;
        Horse->ForcedIdle = EHorseRole::IdleGraze; Horse->IdleTimer = 2.f;
        Horse->bTerminal = false; Horse->IdleCooldown = 5.f;
        Movement->SetMovementMode(MOVE_Walking); Movement->Velocity = FVector::ZeroVector;
        Rider->SetActorRotation(FRotator::ZeroRotator);
    };
    for (float Steering : {-1.f, -.5f, .5f, 1.f})
    {
        Reset(); FHorseInput Input; Input.Stick.X = Steering;
        TestTrue(TEXT("Stationary steering simulates"), Horse->AdvanceSimulation(.1f, Input));
        TestEqual(TEXT("Pivot steps use the existing walk wire/rider role"), Horse->Role, EHorseRole::Walk);
        TestEqual(TEXT("Pivot cancels grazing"), Horse->ForcedIdle, EHorseRole::Idle);
        TestTrue(TEXT("The cycle follows angular travel even without a rider clip"), FMath::IsNearlyEqual(Horse->GaitPhase, .125f * FMath::Abs(Steering)));
        TestTrue(TEXT("Yaw matches the authored 36-degree / .8-second cycle"), FMath::IsNearlyEqual(float(Rider->GetActorRotation().Yaw), 4.5f * Steering));
        TestEqual(TEXT("Pivot does not translate"), Rider->GetActorLocation(), Start);
        TestEqual(TEXT("Pivot adds no velocity"), Movement->Velocity, FVector::ZeroVector);
        Input.Stick.X = 0.; Horse->AdvanceSimulation(.1f, Input);
        TestEqual(TEXT("Releasing steering returns to standing"), Horse->Role, EHorseRole::Idle);
    }
    Reset(); FHorseInput Input; Input.Stick.X = .09;
    Horse->AdvanceSimulation(.1f, Input);
    TestEqual(TEXT("Stick drift does not rotate"), Rider->GetActorRotation().Yaw, 0.);
    TestFalse(TEXT("Stick drift has no pivot"), Horse->IsTurningInPlace());
    Input.Stick.X = 1.; Input.bMenu = true; Horse->AdvanceSimulation(.1f, Input);
    TestFalse(TEXT("A menu stops pivoting"), Horse->IsTurningInPlace());
    Input.bMenu = false; Movement->SetMovementMode(MOVE_Falling); Horse->AdvanceSimulation(.1f, Input);
    TestFalse(TEXT("Air steering never plants pivot hooves"), Horse->IsTurningInPlace());
    Reset(); Horse->Phase = UHorseComponent::EPhase::Mounting; Horse->Role = EHorseRole::Mount;
    Horse->AdvanceSimulation(.1f, Input);
    TestEqual(TEXT("Mounting keeps its own animation"), Horse->Role, EHorseRole::Mount);

    // Jumping launches from the ground, advances a non-looping jump phase in the air and returns to ground gaits on landing.
    Reset(); Input = FHorseInput();
    TestTrue(TEXT("Grounded horse can jump"), Horse->Jump());
    TestTrue(TEXT("Jump enters falling mode with upward and forward speed"),
        Movement->IsFalling() && Movement->Velocity.Z >= 560.f && Horse->GetSpeed() >= 240.f);
    TestTrue(TEXT("Airborne horse reports jumping state"), Horse->IsJumping());
    TestEqual(TEXT("Jumping uses the gallop rider role"), Horse->Role, EHorseRole::Gallop);
    TestFalse(TEXT("Cannot double-jump in mid-air"), Horse->Jump());
    Horse->AdvanceSimulation(.38f, Input);
    TestTrue(TEXT("Jump phase advances through the flight"), FMath::IsNearlyEqual(Horse->GaitPhase, .5f, .02f));
    Horse->AdvanceSimulation(1.0f, Input);
    TestEqual(TEXT("Jump phase clamps at the end of a long drop"), Horse->GaitPhase, 1.f);
    Movement->SetMovementMode(MOVE_Walking);
    Horse->AdvanceSimulation(.1f, Input);
    TestFalse(TEXT("Landing ends jumping state"), Horse->IsJumping());

    // Summoning from stowed picks a new random look unless one was explicitly chosen while stowed.
    Horse->Breeds.SetNum(3); Horse->TackIds = {TEXT("00"), TEXT("01")};
    Horse->CoatVariants.SetNum(2); Horse->CoatMasks.SetNum(2);
    Horse->HairColors.SetNum(2); Horse->HairPatterns.SetNum(2); Horse->Tints.SetNum(2);
    Horse->bAssetsReady = true;
    for (int32 I = 0; I < 8; ++I)
    {
        const FJapanHorseAppearance Before = Horse->GetAppearance();
        const FJapanHorseAppearance Next = Horse->RandomAppearance();
        TestTrue(TEXT("Randomizing always changes breed, tack and coat"),
            Next.Breed != Before.Breed && Next.Tack != Before.Tack && Next.Coat != Before.Coat);
        Horse->ApplyAppearance(Next);
    }
    return true;
}
#endif
