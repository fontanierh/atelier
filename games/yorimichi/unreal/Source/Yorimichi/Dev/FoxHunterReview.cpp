#include "FoxHunter.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Misc/App.h"
#include "Misc/FileHelper.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UnrealClient.h"
#include "Kismet/GameplayStatics.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"

/**
 * -foxqa: a scripted fight on a flat floor, on a fixed clock (-foxqafps=N). The fox is placed 5.2 m from the
 * armed player and the script drives the player's real handlers: it parries the first attack (timed from the
 * fox's own hit window) and checks the stagger and the counter, takes the second attack and checks the flinch
 * and the health loss, rolls through the third, wears the fox down with quick strikes and finishes it with a
 * full charge, waits for the body to fade and the hunter to return, then stands still until it is knocked down
 * and checks that it gets back up while the fox withdraws. Results: fox_qa.json, fox_telemetry.csv, screenshots.
 */
struct FFoxReview
{
    AFoxHunter* Fox = nullptr; AWandererCharacter* Player = nullptr;
    struct FStep { FString Name; TFunction<void()> Enter; TFunction<void()> Each; TFunction<bool()> Done; float Timeout = 10.f; TFunction<void()> Exit; };
    TArray<FStep> Steps; int32 Step = -1; float Time = 0.f, StepTime = 0.f; int32 Fps = 60; bool bStarted = false;
    TArray<FString> Errors; FString Dir; FVector Origin = FVector::ZeroVector;
    FString Telemetry = TEXT("time,step,fox_state,fox_action,fox_time,fox_hp,fox_x,fox_y,fox_yaw,fox_speed,strike_x,strike_y,strike_z,dist,player_state,player_action,player_hp,down,px,py,pyaw,landed,parried,dodged,missed,fox_hits\n");
    bool bPressed = false, bSawFlinch = false, bLoggedRun = false; float MaxSpeed = 0.f, HealthAtStep = 0.f; int32 HitsAtStep = 0, LandedAt = 0, ParriedAt = 0, DodgedAt = 0, MissedAt = 0; float NextTap = -1.f;
    void Check(bool Pass, const FString& Label)
    {
        UE_LOG(LogTemp, Display, TEXT("FOX QA %s: %s"), Pass ? TEXT("PASS") : TEXT("FAIL"), *Label);
        if (!Pass) Errors.Add(Label);
    }
    void Shot(const TCHAR* Name) { FScreenshotRequest::RequestScreenshot(Dir / FString::Printf(TEXT("fox_%s.png"), Name), false, false); }
};

TSharedPtr<FFoxReview> CreateFoxReview(AFoxHunter* Fox) { TSharedPtr<FFoxReview> R = MakeShared<FFoxReview>(); R->Fox = Fox; return R; }

static void BuildSteps(FFoxReview& R)
{
    AFoxHunter* Fox = R.Fox; AWandererCharacter* P = R.Player; UWandererSwordComponent* S = P->GetSword();
    auto Dist = [=]() { return FVector::Dist2D(Fox->GetActorLocation(), P->GetActorLocation()); };
    auto InWindup = [=](float Lead) { const FFoxHunterClip* C = Fox->GetDefinition()->FindClip(Fox->GetAnimationAction()); return Fox->GetState() == EFoxState::Attack && C && C->HitStart > 0.f && Fox->GetActionTime() >= C->HitStart - Lead && Fox->GetActionTime() < C->HitStart; };
    auto Mark = [=, &R]() { R.LandedAt = Fox->StrikesLanded; R.ParriedAt = Fox->StrikesParried; R.DodgedAt = Fox->StrikesDodged; R.HitsAtStep = Fox->HitsTaken; R.HealthAtStep = S->GetHealth(); };
    auto Tap = [=]() { S->AttackPressed(); S->AttackReleased(); };
    R.Steps = {
        { TEXT("draw and notice"), [=]() { S->ToggleWeapon(); }, nullptr,
          [=]() { return S->IsArmed() && S->GetState() == ESwordState::Guard && Fox->GetState() != EFoxState::Idle; }, 2.f, nullptr },
        { TEXT("approach"), nullptr, nullptr, [=]() { return Fox->GetState() == EFoxState::Stalk; }, 6.f,
          [=, &R]() { R.Check(R.MaxSpeed > 300.f, FString::Printf(TEXT("fox ran in (peak %.0f cm/s)"), R.MaxSpeed)); R.Shot(TEXT("approach")); } },
        { TEXT("first claw parried"), [=, &R]() { Mark(); Fox->ForceNextAttack(TEXT("AttackR_A")); R.bPressed = false; R.bLoggedRun = false; },
          [=, &R]() { if (!R.bPressed && InWindup(.20f)) { R.bPressed = true; S->ParryPressed(); } if (R.bPressed && !R.bLoggedRun && S->IsParryActive()) { R.bLoggedRun = true; R.Shot(TEXT("parry")); } },
          [=, &R]() { return Fox->StrikesParried > R.ParriedAt && Fox->GetState() == EFoxState::Hurt; }, 9.f,
          [=, &R]() { R.Check(S->ParriesMade() == 1 && S->GetHealth() == R.HealthAtStep, TEXT("player parried the claw and took no hit")); } },
        { TEXT("counter lands"), [=, &R]() { R.HitsAtStep = Fox->HitsTaken; }, nullptr,
          [=, &R]() { return Fox->HitsTaken > R.HitsAtStep; }, 2.5f, [=, &R]() { R.Check(Fox->GetHealth() == AFoxHunter::MaxHealth - 1, FString::Printf(TEXT("counter took one point (%d/%d)"), Fox->GetHealth(), AFoxHunter::MaxHealth)); R.Shot(TEXT("counter")); } },
        { TEXT("unparried claw hits"), [=, &R]() { Mark(); Fox->ForceNextAttack(TEXT("AttackL_B")); R.bSawFlinch = false; },
          [=, &R]() { if (P->GetAnimationAction() == TEXT("Land")) R.bSawFlinch = true; },
          [=, &R]() { return Fox->StrikesLanded > R.LandedAt; }, 12.f,
          [=, &R]() { R.Check(S->GetHealth() < R.HealthAtStep, FString::Printf(TEXT("claw took health (%.0f -> %.0f)"), R.HealthAtStep, S->GetHealth())); } },
        { TEXT("flinch plays"), nullptr, [=, &R]() { if (P->GetAnimationAction() == TEXT("Land")) R.bSawFlinch = true; }, [=, &R]() { return R.bSawFlinch; }, 1.f,
          [=, &R]() { R.Check(R.bSawFlinch, TEXT("hit plays the flinch")); R.Shot(TEXT("hit")); } },
        { TEXT("roll through the next claw"), [=, &R]() { Mark(); Fox->ForceNextAttack(TEXT("AttackR_B")); R.bPressed = false; R.MissedAt = Fox->StrikesMissed; },
          [=, &R]() { if (!R.bPressed && InWindup(.14f)) { R.bPressed = true; FVector To = Fox->GetActorLocation() - P->GetActorLocation(); To.Z = 0; To.Normalize(); S->ReviewRoll(FVector2D(To.Y, To.X)); }
                      if (R.bPressed && P->GetAnimationAction() != TEXT("Roll")) S->ReviewMove(FVector2D::ZeroVector); },
          [=, &R]() { return Fox->StrikesDodged > R.DodgedAt || (Fox->StrikesMissed > R.MissedAt && S->GetHealth() == R.HealthAtStep); }, 12.f,
          [=, &R]() { S->ReviewMove(FVector2D::ZeroVector); R.Check(S->GetHealth() == R.HealthAtStep, FString::Printf(TEXT("rolling through the claw costs no health (%s)"), Fox->StrikesDodged > R.DodgedAt ? TEXT("dodged in the roll") : TEXT("out of reach"))); R.Shot(TEXT("roll")); } },
        { TEXT("quick strikes wear it down"), [=, &R]() { Mark(); Fox->SetPassive(true); R.NextTap = -1.f; },
          [=, &R]() { const bool bReady = (S->GetState() == ESwordState::Guard || S->GetState() == ESwordState::Stowed) && P->GetAnimationAction() != TEXT("Roll");
                      if (bReady && Dist() <= AFoxHunter::AttackRange + 5.f && R.NextTap < 0.f) R.NextTap = R.Time + .1f; if (R.NextTap > 0.f && R.Time >= R.NextTap) { R.NextTap = -1.f; Tap(); } },
          [=]() { return Fox->GetHealth() <= 3; }, 30.f, [=, &R]() { R.Check(Fox->GetHealth() <= 3 && Fox->IsAlive(), FString::Printf(TEXT("quick strikes bring the fox to %d (%d hits)"), Fox->GetHealth(), Fox->HitsTaken - R.HitsAtStep)); } },
        { TEXT("full charge finishes it"), [=, &R]() { R.bPressed = false; },
          [=, &R]() { if (!R.bPressed && S->GetState() == ESwordState::Guard && Dist() <= AFoxHunter::AttackRange + 5.f && Fox->GetState() == EFoxState::Stalk && Fox->GetVelocity().Size2D() < 5.f) { R.bPressed = true; S->AttackPressed(); }
                      if (R.bPressed && S->GetState() == ESwordState::ChargeHold && S->ChargeFraction() >= 1.f) { S->AttackReleased(); R.Shot(TEXT("charge")); } },
          [=]() { return Fox->Deaths == 1 && !Fox->IsAlive(); }, 20.f, [=, &R]() { R.Check(Fox->GetState() == EFoxState::Dead, TEXT("full charge kills the fox")); R.Shot(TEXT("death")); } },
        { TEXT("body fades"), nullptr, nullptr, [=]() { return Fox->IsHidden(); }, AFoxHunter::DeadBodyTime + 1.f, [=, &R]() { R.Check(Fox->IsHidden() && !Fox->IsAlive(), TEXT("body holds its pose then fades")); } },
        { TEXT("hunter returns"), [=]() { Fox->SetPassive(false); S->AttackReleased(); }, nullptr, [=]() { return Fox->IsAlive() && Fox->GetState() == EFoxState::Idle && Fox->GetHealth() == AFoxHunter::MaxHealth && !Fox->IsHidden(); }, AFoxHunter::RespawnTime + 2.f,
          [=, &R]() { R.Check(FVector::Dist2D(Fox->GetActorLocation(), R.Origin + FVector(520, 0, 0)) < 20.f, TEXT("returns to its home spot at full health")); } },
        { TEXT("knocked down"), [=, &R]() { Mark(); if (Dist() > 600.f) P->TravelTo(R.Origin + FVector(200, 0, -P->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), 0.f, TEXT("Fox QA")); }, nullptr, [=]() { return S->IsDown(); }, 60.f,
          [=, &R]() { R.Check(S->IsDown() && S->GetHealth() <= 0.f, FString::Printf(TEXT("standing still, the fox knocks the player down (%d landed)"), Fox->StrikesLanded - R.LandedAt)); R.Shot(TEXT("down")); } },
        { TEXT("fox withdraws"), nullptr, nullptr, [=]() { return Fox->GetState() == EFoxState::Withdraw || Fox->GetState() == EFoxState::Return || Fox->GetState() == EFoxState::Idle; }, 6.f, [=, &R]() { R.Check(Fox->GetState() != EFoxState::Attack && Fox->GetState() != EFoxState::Stalk, TEXT("fox withdraws after the knock-down")); } },
        { TEXT("back on your feet"), nullptr, nullptr, [=]() { return !S->IsDown() && S->GetHealth() >= 100.f; }, 8.f,
          [=, &R]() { R.Check(!S->IsDown() && !S->LocksMovement() && S->IsArmed(), TEXT("player stands up with full health, still armed")); R.Shot(TEXT("up")); } },
    };
}

void AdvanceFoxReview(FFoxReview& R, float Dt)
{
    AFoxHunter* Fox = R.Fox;
    if (!R.Player) R.Player = Cast<AWandererCharacter>(UGameplayStatics::GetPlayerPawn(Fox, 0));
    if (!R.Player || !R.Player->IsReady() || !R.Player->GetSword()) return;
    AWandererCharacter* P = R.Player; UWandererSwordComponent* S = P->GetSword();
    if (!R.bStarted)
    {
        R.bStarted = true;
        FParse::Value(FCommandLine::Get(), TEXT("foxqafps="), R.Fps); R.Fps = FMath::Clamp(R.Fps, 15, 240);
        FApp::SetFixedDeltaTime(1.0 / R.Fps); FApp::SetUseFixedTimeStep(true);
        FParse::Value(FCommandLine::Get(), TEXT("reviewdir="), R.Dir);
        if (R.Dir.IsEmpty()) R.Dir = FPaths::ProjectSavedDir() / TEXT("Screenshots/Fox") / FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
        IFileManager::Get().MakeDirectory(*R.Dir, true);
        const FVector Base = P->GetActorLocation() + FVector(0, 0, 2000);
        auto* Floor = Fox->GetWorld()->SpawnActor<AActor>();
        auto* Box = NewObject<UBoxComponent>(Floor); Floor->SetRootComponent(Box); Floor->AddInstanceComponent(Box);
        Box->SetBoxExtent(FVector(3000, 3000, 50)); Box->SetCollisionProfileName(TEXT("BlockAll")); Box->RegisterComponent();
        const float PlayerHalf = P->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        Floor->SetActorLocation(Base - FVector(0, 0, PlayerHalf + 52));
        auto* Surface = Fox->GetWorld()->SpawnActor<AStaticMeshActor>();
        Surface->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        Surface->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
        Surface->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision); Surface->GetStaticMeshComponent()->SetCastShadow(false);
        Surface->SetActorLocation(Floor->GetActorLocation()); Surface->SetActorScale3D(FVector(60, 60, 1));
        P->TravelTo(Base - FVector(0, 0, PlayerHalf), 0, TEXT("Fox QA"));
        R.Origin = P->GetActorLocation();
        if (P->Controller) P->Controller->SetControlRotation(FRotator::ZeroRotator);
        if (UCameraComponent* Camera = P->FindComponentByClass<UCameraComponent>())
        {
            Camera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            const FVector Eye = R.Origin + FVector(220, -560, 150), Look = R.Origin + FVector(220, 0, 30);
            Camera->SetWorldLocationAndRotation(Eye, (Look - Eye).Rotation());
        }
        const float FoxHalf = Fox->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        const FVector FoxAt = R.Origin + FVector(520, 0, FoxHalf - PlayerHalf + 2.f);
        Fox->SetActorLocation(FoxAt, false, nullptr, ETeleportType::TeleportPhysics);
        Fox->SetActorRotation(FRotator(0, 180, 0));
        Fox->SetHome(FoxAt, 180.f); Fox->SetSeed(7);
        R.Check(Fox->IsReady(), TEXT("fox definition installed (DA_FoxHunter)"));
        R.Check(Fox->GetState() == EFoxState::Idle, TEXT("fox starts idle at its world spot"));
        R.Check(S->IsInstalled(), TEXT("sword set installed on the player"));
        BuildSteps(R);
        UE_LOG(LogTemp, Display, TEXT("FOX QA START fps=%d dir=%s"), R.Fps, *R.Dir);
        return;
    }
    R.Time += Dt; R.MaxSpeed = FMath::Max(R.MaxSpeed, Fox->GetVelocity().Size2D());
    const FVector FoxRel = Fox->GetActorLocation() - R.Origin, PRel = P->GetActorLocation() - R.Origin, Strike = Fox->StrikePoint() - R.Origin;
    R.Telemetry += FString::Printf(TEXT("%.3f,%d,%s,%s,%.3f,%d,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%s,%s,%.0f,%d,%.1f,%.1f,%.1f,%d,%d,%d,%d,%d\n"), R.Time, R.Step, *Fox->StateName(), *Fox->GetAnimationAction().ToString(), Fox->GetActionTime(), Fox->GetHealth(),
        FoxRel.X, FoxRel.Y, Fox->GetActorRotation().Yaw, Fox->GetVelocity().Size2D(), Strike.X, Strike.Y, Strike.Z, FVector::Dist2D(Fox->GetActorLocation(), P->GetActorLocation()),
        *S->StateName(), *P->GetAnimationAction().ToString(), S->GetHealth(), S->IsDown(), PRel.X, PRel.Y, P->GetActorRotation().Yaw, Fox->StrikesLanded, Fox->StrikesParried, Fox->StrikesDodged, Fox->StrikesMissed, Fox->HitsTaken);
    if (R.Step < 0)
    {
        if (R.Time < .5f) return;
        R.Step = 0; R.StepTime = 0.f; if (R.Steps[0].Enter) R.Steps[0].Enter();
        UE_LOG(LogTemp, Display, TEXT("FOX QA step %d: %s"), R.Step, *R.Steps[0].Name);
        return;
    }
    if (R.Step >= R.Steps.Num())
    {
        FFileHelper::SaveStringToFile(R.Telemetry, *(R.Dir / TEXT("fox_telemetry.csv")));
        FString ErrorList; for (const FString& E : R.Errors) { if (!ErrorList.IsEmpty()) ErrorList += TEXT(","); ErrorList += TEXT("\"") + E + TEXT("\""); }
        const FString Result = FString::Printf(TEXT("{\"passed\":%s,\"errors\":[%s],\"fox_attacks\":%d,\"landed\":%d,\"parried\":%d,\"dodged\":%d,\"missed\":%d,\"fox_hits_taken\":%d,\"fox_deaths\":%d,\"player_hits_taken\":%d,\"player_parries\":%d,\"fixed_fps\":%d,\"seconds\":%.1f}\n"),
            R.Errors.IsEmpty() ? TEXT("true") : TEXT("false"), *ErrorList, Fox->Attacks, Fox->StrikesLanded, Fox->StrikesParried, Fox->StrikesDodged, Fox->StrikesMissed, Fox->HitsTaken, Fox->Deaths, S->HitsTaken(), S->ParriesMade(), R.Fps, R.Time);
        FFileHelper::SaveStringToFile(Result, *(R.Dir / TEXT("fox_qa.json")));
        UE_LOG(LogTemp, Display, TEXT("FOX QA COMPLETE %s"), *Result);
        R.Step = MAX_int32 / 2;   // written once
        FPlatformMisc::RequestExit(false);
        return;
    }
    FFoxReview::FStep& Current = R.Steps[R.Step];
    R.StepTime += Dt;
    if (Current.Each) Current.Each();
    const bool bDone = Current.Done && Current.Done();
    if (bDone || R.StepTime > Current.Timeout)
    {
        if (!bDone) R.Check(false, FString::Printf(TEXT("%s: timed out after %.1f s (fox %s hp %d, player %s hp %.0f, dist %.0f)"), *Current.Name, Current.Timeout, *Fox->StateName(), Fox->GetHealth(), *S->StateName(), S->GetHealth(), FVector::Dist2D(Fox->GetActorLocation(), P->GetActorLocation())));
        else UE_LOG(LogTemp, Display, TEXT("FOX QA step %d done at %.2f s: %s"), R.Step, R.Time, *Current.Name);
        if (Current.Exit) Current.Exit();
        ++R.Step; R.StepTime = 0.f;
        if (R.Step < R.Steps.Num()) { if (R.Steps[R.Step].Enter) R.Steps[R.Step].Enter(); UE_LOG(LogTemp, Display, TEXT("FOX QA step %d: %s"), R.Step, *R.Steps[R.Step].Name); }
    }
}
