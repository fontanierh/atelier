#include "WandererCharacter.h"
#include "WandererDefinition.h"
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

/** -sworddummy: a training post 1.3 m ahead of the player, swinging every 3 s so parries can be tried in play.
 * It is a deterministic test fixture, not an enemy. */
void AWandererCharacter::SpawnSwordDummy()
{
    if (SwordDummy || !GetWorld()) return;
    const FVector Where = GetActorLocation() + GetActorForwardVector() * 130.f - FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()) + FVector(0, 0, 70.f);
    SwordDummy = GetWorld()->SpawnActor<ASwordDummy>(Where, FRotator::ZeroRotator);
    if (SwordDummy) { SwordDummy->SetTarget(this); if (!bSwordReview) SwordDummy->SetAutoStrike(3.f); }
}

/** Opt-in -swordqa: scripted presses through the real input handlers on a fixed clock, checking states,
 * strike counts, buffering, charge/cancel/parry timing and weapon policy. -swordqafps=N changes the frame interval. */
void AWandererCharacter::AdvanceSwordReview(float Dt)
{
    auto Check = [&](bool Pass, const FString& Label)
    {
        UE_LOG(LogTemp, Display, TEXT("SWORD QA %s: %s"), Pass ? TEXT("PASS") : TEXT("FAIL"), *Label);
        if (!Pass) SwordErrors.Add(Label);
    };
    auto Shot = [&](const TCHAR* Name) { FScreenshotRequest::RequestScreenshot(ReviewDirectory / FString::Printf(TEXT("sword_%s.png"), Name), false, false); };
    auto Tap = [&]() { Sword->AttackPressed(); Sword->AttackReleased(); };
    if (SwordReviewStep < 0)
    {
        int32 Fps = 60; FParse::Value(FCommandLine::Get(), TEXT("swordqafps="), Fps); Fps = FMath::Clamp(Fps, 15, 240);
        FApp::SetFixedDeltaTime(1.0 / Fps); FApp::SetUseFixedTimeStep(true);
        const FVector Origin = GetActorLocation() + FVector(0, 0, 2000);
        auto* Floor = GetWorld()->SpawnActor<AActor>();
        auto* Box = NewObject<UBoxComponent>(Floor); Floor->SetRootComponent(Box); Floor->AddInstanceComponent(Box);
        Box->SetBoxExtent(FVector(3000, 3000, 50)); Box->SetCollisionProfileName(TEXT("BlockAll")); Box->RegisterComponent();
        Floor->SetActorLocation(Origin - FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 52));
        auto* Surface = GetWorld()->SpawnActor<AStaticMeshActor>();
        Surface->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        Surface->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
        Surface->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision); Surface->GetStaticMeshComponent()->SetCastShadow(false);
        Surface->SetActorLocation(Floor->GetActorLocation()); Surface->SetActorScale3D(FVector(60, 60, 1));
        TravelTo(Origin - FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), 0, TEXT("Sword QA"));
        CairoOrigin = GetActorLocation();
        ReviewForward = FVector::ForwardVector; Controller->SetControlRotation(FRotator::ZeroRotator);
        FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        const FVector Eye = GetActorLocation() + FVector(70, -320, 60), Look = GetActorLocation() + FVector(70, 0, 10);
        FollowCamera->SetWorldLocationAndRotation(Eye, (Look - Eye).Rotation());
        SpawnSwordDummy();
        // Inside the reach of every strike arc (the first cut lands about 70 cm ahead and to the left); a wider post for the harness.
        if (SwordDummy) { SwordDummy->SetActorLocation(GetActorLocation() + FVector(95, -15, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 70)); SwordDummy->SetActorScale3D(FVector(1.3f, 1.3f, 1.f)); }
        Check(Definition && Definition->HasSwordSet() && Sword && Sword->IsInstalled(), TEXT("sword set installed on DA_Cairo"));
        Check(SwordDummy != nullptr, TEXT("training dummy spawned"));
        Check(!Sword->IsArmed(), TEXT("starts unarmed"));
        SwordReviewStep = 0; SwordReviewTime = 0.f;
        UE_LOG(LogTemp, Display, TEXT("SWORD QA START fps=%d dir=%s"), Fps, *ReviewDirectory);
        return;
    }
    const float Before = SwordReviewTime; SwordReviewTime += Dt;
    int32 Fps = 60; FParse::Value(FCommandLine::Get(), TEXT("swordqafps="), Fps);
    auto At = [&](float T) { return Before < T && SwordReviewTime >= T; };
    const ESwordState S = Sword->GetState();
    const int32 Strikes = Sword->Strikes().Num(); const int32 DummyHits = SwordDummy ? SwordDummy->HitsTaken : -1;
    static int32 MarkStrikes = 0, MarkHits = 0; auto Mark = [&]() { MarkStrikes = Strikes; MarkHits = DummyHits; };
    const int32 DS = Strikes - MarkStrikes, DH = DummyHits - MarkHits;
    const FVector Where = GetActorLocation() - CairoOrigin; const FVector Tip = Sword->BladeTipWorld() - CairoOrigin;
    SwordTelemetry += FString::Printf(TEXT("%.3f,%s,%s,%.3f,%d,%d,%d,%d,%d,%d,%.1f,%.1f,%.1f,%.1f,%d,%.1f,%.1f,%.1f,%.1f\n"), SwordReviewTime, *Sword->StateName(), *AnimationAction.ToString(), GetActionSourceTime(), MovementLocked(), Sword->IsArmed(), Strikes, DummyHits, Sword->HitsTaken(), Sword->ParriesMade(),
        Where.X, Where.Y, Where.Z, GetVelocity().Z, GetCharacterMovement()->IsFalling(), GetActorRotation().Yaw, Tip.X, Tip.Y, Tip.Z);
    // 1. draw
    if (At(.5f)) Sword->ToggleWeapon();
    if (At(.7f)) { Check(S == ESwordState::Guard && Sword->IsArmed() && AnimationAction != TEXT("SwordDraw"), TEXT("weapon toggle draws at once, no draw clip")); Shot(TEXT("draw")); }
    if (At(1.3f)) Check(S == ESwordState::Guard && Sword->IsArmed(), TEXT("draw settles into the armed guard"));
    // 2. a single tap: one prompt strike, one dummy hit, back to guard, no second strike
    if (At(1.45f)) Mark();
    if (At(1.5f)) Tap();
    if (At(1.7f)) Check(S == ESwordState::Attack && AnimationAction == TEXT("SwordAttack1") && MovementLocked(), TEXT("tap starts strike 1 immediately and locks movement"));
    if (At(1.9f)) Shot(TEXT("attack1_contact"));
    if (At(2.7f)) { Check(S == ESwordState::Guard && DS == 1 && DH == 1, FString::Printf(TEXT("single tap = 1 strike, 1 dummy hit, guard again (strikes %d hits %d)"), DS, DH)); Mark(); }
    // 3. chain: taps in the link windows give exactly three strikes; a fourth press after the chain is ignored
    if (At(3.f) || At(3.35f) || At(3.7f) || At(3.9f)) Tap();
    if (At(3.6f)) Check(AnimationAction == TEXT("SwordAttack2"), TEXT("buffered tap links into strike 2"));
    if (At(4.0f)) { Check(AnimationAction == TEXT("SwordAttack3"), TEXT("buffered tap links into strike 3")); Shot(TEXT("attack3")); }
    if (At(5.3f)) { Check(S == ESwordState::Guard && DS == 3 && DH == 3, FString::Printf(TEXT("chain = 3 strikes, one hit each, then guard (strikes %d hits %d)"), DS, DH)); Mark(); }
    // 4. early release: a held press cuts first, then winds up the charge from the follow-through; releasing early still attacks
    if (At(5.5f)) Sword->AttackPressed();
    if (At(5.9f)) Check(S == ESwordState::ChargeUp, TEXT("holding the button past the first cut winds up a charge"));
    if (At(5.95f)) Sword->AttackReleased();
    if (At(6.05f)) Check(S == ESwordState::ChargeRelease && DS == 2 && !Sword->WasFullCharge() && Sword->Strikes().Last().bCharged, TEXT("early release plays the charged cut, not full"));
    if (At(7.f)) { Check(S == ESwordState::Guard && DS == 2 && DH == 2, FString::Printf(TEXT("the cut and the early release land once each (strikes %d hits %d)"), DS, DH)); Mark(); }
    // 5. full charge: hold for over 0.9 s in the hold, release, hit-stop on contact
    if (At(7.2f)) Sword->AttackPressed();
    if (At(8.f)) Check(S == ESwordState::ChargeHold && Sword->ChargeFraction() > 0.f && Sword->ChargeFraction() < 1.f, TEXT("hold pose reached and charging"));
    if (At(8.3f)) Shot(TEXT("charge_hold"));
    if (At(8.85f)) Check(S == ESwordState::ChargeHold && Sword->ChargeFraction() >= 1.f, TEXT("full charge after 0.9 s of hold"));
    if (At(8.9f)) Sword->AttackReleased();
    if (At(9.f)) Check(S == ESwordState::ChargeRelease && Sword->WasFullCharge() && DS == 2 && Sword->Strikes().Last().bFull, TEXT("full charge release"));
    if (At(9.15f)) Shot(TEXT("charge_release"));
    if (At(10.2f)) { Check(S == ESwordState::Guard && DH == 2, FString::Printf(TEXT("the cut and the full release land once each and recover (hits %d)"), DH)); Mark(); }
    // 6. cancel a charge with parry; the later release must not fire
    if (At(10.4f)) Sword->AttackPressed();
    if (At(11.1f)) Sword->ParryPressed();
    if (At(11.2f)) Check(S == ESwordState::Guard && DS == 1, TEXT("parry press cancels a charge safely (the opening cut stands)"));
    if (At(11.25f)) Sword->AttackReleased();
    if (At(11.4f)) { Check(S == ESwordState::Guard && DS == 1, TEXT("release after a cancel does not attack")); Mark(); }
    // 7. parry with nothing incoming
    if (At(11.6f)) Sword->ParryPressed();
    if (At(11.75f)) Check(S == ESwordState::Parry && Sword->IsParryActive(), TEXT("parry active window opens within 0.15 s"));
    if (At(12.4f)) Check(S == ESwordState::Guard && Sword->ParriesMade() == 0 && Sword->HitsTaken() == 0, TEXT("missed parry returns to guard"));
    // 8. parry success: the dummy's swing lands inside the active window, then the counter strike
    if (At(12.6f) && SwordDummy) SwordDummy->StrikeIn(.6f);
    if (At(13.f)) Sword->ParryPressed();
    if (At(13.15f)) Shot(TEXT("parry_active"));
    if (At(13.3f)) Check(Sword->ParriesMade() == 1 && (S == ESwordState::ParryHit || S == ESwordState::Attack), TEXT("swing landing in the parry window is deflected"));
    if (At(13.6f)) { Check(S == ESwordState::Attack && AnimationAction == TEXT("SwordAttack1") && DS == 1, TEXT("deflection chains into the counter strike")); Shot(TEXT("counter")); }
    if (At(14.7f)) { Check(S == ESwordState::Guard && DH == 1, FString::Printf(TEXT("counter lands once (hits %d)"), DH)); Mark(); }
    // 9. late parry: the swing lands while the player is not parrying
    if (At(15.f) && SwordDummy) SwordDummy->StrikeIn(.6f);
    if (At(15.7f)) Check(Sword->HitsTaken() == 1 && Sword->ParriesMade() == 1, TEXT("unparried swing counts as a hit on the player"));
    // 10. movement cancels the recovery after the cancel window; the carry layer runs armed locomotion
    if (At(15.9f)) Mark();
    if (At(16.f)) Tap();
    if (At(16.15f)) Check(MovementLocked(), TEXT("movement is locked before the cancel window"));
    if (At(16.55f)) MoveIntent = FVector2D(0, 1);
    if (At(16.75f)) Check(S == ESwordState::Guard && AnimationAction.IsNone() && !MovementLocked(), TEXT("movement after the cancel window returns control"));
    if (At(17.1f)) Check(Sword->CarryWeight() > .5f && Sword->IsArmed() && GetVelocity().Size2D() > 30.f, TEXT("armed running keeps the sword with the carry layer"));
    if (At(17.3f)) MoveIntent = FVector2D::ZeroVector;
    // 11. rolling keeps the sword (armed roll); the next attack press strikes at once
    if (At(17.8f)) Dodge(FInputActionValue(true));
    if (At(18.f)) Check(Sword->IsArmed() && AnimationAction == TEXT("Roll") && GetAnimationClip() == TEXT("SwordRoll"), TEXT("roll keeps the sword and plays the armed roll"));
    if (At(19.4f)) Tap();
    if (At(19.55f)) Check(S == ESwordState::Attack, TEXT("attack after the roll strikes at once"));
    // 12. the settings menu cancels a held charge
    if (At(21.25f)) Mark();
    if (At(21.3f)) Sword->AttackPressed();
    if (At(22.f)) SetMenuOpen(true);
    if (At(22.1f)) Check(S == ESwordState::Guard && DS == 1, TEXT("opening the menu cancels the charge (the opening cut stands)"));
    if (At(22.3f)) SetMenuOpen(false);
    if (At(22.4f)) Sword->AttackReleased();
    if (At(22.5f)) { Check(DS == 1 && S == ESwordState::Guard, TEXT("release after the menu does not attack")); Mark(); }
    // 13. mashing: six presses in 0.5 s give exactly one three-strike chain
    if (At(22.7f) || At(22.8f) || At(22.9f) || At(23.f) || At(23.1f) || At(23.2f)) Tap();
    if (At(25.f)) Check(S == ESwordState::Guard && DS >= 2 && DS <= 3, FString::Printf(TEXT("mashing six presses yields one chain of at most three strikes (strikes %d)"), DS));
    // 14. sheathe and finish
    if (At(25.3f)) Sword->ToggleWeapon();
    if (At(25.5f)) Check(!Sword->IsArmed(), TEXT("weapon toggle sheathes at once"));
    if (At(26.2f)) Check(!Sword->IsArmed() && !MovementLocked() && AnimationAction.IsNone(), TEXT("ends unarmed, unlocked, in locomotion"));
    if (At(26.5f))
    {
        int32 Landed = 0; for (const FSwordStrikeEvent& E : Sword->Strikes()) Landed += E.Targets.Num();
        Check(Landed == DummyHits, FString::Printf(TEXT("every registered strike target matches a dummy hit (%d/%d)"), Landed, DummyHits));
        FFileHelper::SaveStringToFile(SwordTelemetry, *(ReviewDirectory / TEXT("sword_telemetry.csv")));
        FString Errors; for (const auto& E : SwordErrors) { if (!Errors.IsEmpty()) Errors += TEXT(","); Errors += TEXT("\"") + E + TEXT("\""); }
        const FString Result = FString::Printf(TEXT("{\"passed\":%s,\"errors\":[%s],\"strikes\":%d,\"dummy_hits\":%d,\"hits_taken\":%d,\"parries\":%d,\"fixed_fps\":%.0f}\n"),
            SwordErrors.IsEmpty() ? TEXT("true") : TEXT("false"), *Errors, Strikes, DummyHits, Sword->HitsTaken(), Sword->ParriesMade(), double(Fps));
        FFileHelper::SaveStringToFile(Result, *(ReviewDirectory / TEXT("sword_qa.json")));
        UE_LOG(LogTemp, Display, TEXT("SWORD QA COMPLETE %s"), *Result);
        FPlatformMisc::RequestExit(false);
    }
}
