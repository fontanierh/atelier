#include "WandererCharacter.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Tests/AutomationCommon.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"

// V2 scenery streams in by cell: a travel can arrive before its destination has collision. The player must be held
// where they arrived (the defect: they fell, and water recovery took them away) and land once the ground blocks.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanTravelGroundTest, "Yorimichi.Map.StreamedGroundWait",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanTravelGroundTest::RunTest(const FString&)
{
    AWandererCharacter* Player = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (UWorld* World = Context.World(); World && World->IsGameWorld())
            if (auto* Controller = World->GetFirstPlayerController()) Player = Cast<AWandererCharacter>(Controller->GetPawn());
    if (!TestNotNull(TEXT("Run after the guarded game is ready"), Player)) return false;
    const float Half = Player->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const FVector Home = Player->GetActorLocation() - FVector(0,0,Half);
    const float HomeYaw = Player->GetActorRotation().Yaw;
    // Far over the open sea and high: nothing within the travel trace (25 m above to 25 m below) blocks.
    const FVector Target(2500000.f, 2500000.f, 50000.f);
    if (!TestTrue(TEXT("Travel to a destination without ground is accepted"), Player->TravelTo(Target,0.f,TEXT("streamed ground regression"))))
        return false;
    TestTrue(TEXT("The player is held for the destination's ground"), Player->IsWaitingForTravelGround());
    TestTrue(TEXT("Held players do not move"), Player->GetCharacterMovement()->MovementMode == MOVE_None);
    const FVector Held = Player->GetActorLocation();
    TWeakObjectPtr<AWandererCharacter> Weak(Player);
    TSharedRef<TWeakObjectPtr<AActor>> Ground = MakeShared<TWeakObjectPtr<AActor>>();
    const float Top = Target.Z - 1000.f;
    ADD_LATENT_AUTOMATION_COMMAND(FDelayedFunctionLatentCommand([this, Weak, Held, Ground, Target, Top]
    {
        AWandererCharacter* P = Weak.Get();
        if (!P) return;
        TestTrue(TEXT("Still held a second later"), P->IsWaitingForTravelGround());
        TestTrue(TEXT("The held player has not fallen"), P->GetActorLocation().Equals(Held, 1.f));
        // The destination's collision arrives.
        AActor* Floor = P->GetWorld()->SpawnActor<AActor>();
        auto* Box = NewObject<UBoxComponent>(Floor);
        Box->SetBoxExtent(FVector(500.f,500.f,50.f));
        Box->SetCollisionProfileName(TEXT("BlockAll"));
        Floor->SetRootComponent(Box);
        Box->RegisterComponent();
        Box->SetWorldLocation(FVector(Target.X,Target.Y,Top-50.f));
        *Ground = Floor;
    }, 1.f));
    ADD_LATENT_AUTOMATION_COMMAND(FDelayedFunctionLatentCommand([this, Weak, Ground, Top, Half, Home, HomeYaw]
    {
        AWandererCharacter* P = Weak.Get();
        if (P)
        {
            TestFalse(TEXT("The wait ends once the ground blocks"), P->IsWaitingForTravelGround());
            TestTrue(TEXT("The player lands on the arrived ground"),
                FMath::Abs(P->GetActorLocation().Z - Half - Top) < 20.f);
            TestTrue(TEXT("Movement resumes"), P->GetCharacterMovement()->MovementMode != MOVE_None);
        }
        if (AActor* Floor = Ground->Get()) Floor->Destroy();
        if (P) P->TravelTo(Home,HomeYaw,TEXT("streamed ground regression return"),30.f);
    }, 1.f));
    return true;
}
#endif
