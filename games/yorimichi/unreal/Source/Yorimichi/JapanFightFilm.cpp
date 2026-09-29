#include "WandererCharacter.h"
#include "WandererSword.h"
#include "WandererDefinition.h"
#include "FoxHunter.h"
#include "JapanCombatFX.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/HUD.h"
#include "HAL/FileManager.h"
#include "ImageUtils.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"
#include "Kismet/GameplayStatics.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInterface.h"

/**
 * -fightfilm: a filmed fight against the fox hunter at its real spot up the road, played through the real input
 * handlers on a fixed 60 Hz clock (-reviewdir=<folder>). The script walks up, draws when the hunter notices, parries
 * its first claw into a counter, rolls under the kick, takes one claw on purpose, lands a three-strike chain and
 * finishes with a cut held into a full charge; any other attack the hunter starts is parried so the take stays on
 * script. A cinematic follow camera frames both fighters. Output: frame_NNNNN.jpg (game view with the fight HUD),
 * camera.csv (per captured frame), audio.json (every sound started, by captured frame) and film.json.
 */
struct FFightFilm
{
    AWandererCharacter* P = nullptr; AFoxHunter* Fox = nullptr; UWandererSwordComponent* S = nullptr;
    struct FStep { FString Name; TFunction<void()> Enter; TFunction<void()> Each; TFunction<bool()> Done; float Timeout = 12.f; bool bAllowHit = false; };
    TArray<FStep> Steps; int32 Step = -1; float StepTime = 0.f, Clock = 0.f, Warm = 0.f;
    FString Dir; int32 Captured = 0, Pending = -1; FDelegateHandle Capture; bool bStarted = false, bDone = false;
    FString CameraCsv = TEXT("frame,x,y,z,pitch,yaw,roll,fov,step\n");
    FVector Focus = FVector::ZeroVector; float Yaw = 0.f, Pitch = -9.f, Distance = 560.f, Fov = 55.f; bool bCamInit = false;
    int32 ParriedAttack = -1; bool bPressed = false; float NextTap = -1.f, HeldSince = -1.f, EndAt = -1.f;
    int32 Mark = 0; float Push = 0.f, RoadYaw = 0.f, Side = 1.f, Blocked = 0.f; FVector RoadOrigin = FVector::ZeroVector, LastFox = FVector::ZeroVector; TArray<FString> Log;
    void Note(const FString& T) { Log.Add(FString::Printf(TEXT("%.2f %s"), Clock, *T)); UE_LOG(LogTemp, Display, TEXT("FIGHT FILM %.2f %s"), Clock, *T); }
};

TSharedPtr<FFightFilm> CreateFightFilm(AWandererCharacter* P) { TSharedPtr<FFightFilm> F = MakeShared<FFightFilm>(); F->P = P; return F; }

/** True when the ground under XY is the road's tarmac (the painterly material named Road, as the footsteps read it). */
static bool IsRoad(UWorld* World, const FVector& At, const AActor* Ignore, FVector* Ground = nullptr)
{
    FCollisionQueryParams Q(SCENE_QUERY_STAT(FilmRoad), true, Ignore); Q.bReturnFaceIndex = true;
    FHitResult Hit;
    if (!World->LineTraceSingleByChannel(Hit, At + FVector(0, 0, 600), At - FVector(0, 0, 900), ECC_Visibility, Q)) return false;
    if (Ground) *Ground = Hit.ImpactPoint;
    const UStaticMeshComponent* Mesh = Cast<UStaticMeshComponent>(Hit.Component.Get());
    if (!Mesh) return false;
    int32 Section = 0;
    const UMaterialInterface* Material = Hit.FaceIndex != INDEX_NONE ? Mesh->GetMaterialFromCollisionFaceIndex(Hit.FaceIndex, Section) : Mesh->GetMaterial(0);
    return Material && Material->GetName().Contains(TEXT("Road"));
}

/** Centre of the tarmac across the road at Along (a point on the road), scanning +-9 m along Right. */
static bool RoadCentre(UWorld* World, const FVector& Along, const FVector& Right, const AActor* Ignore, FVector& Centre)
{
    float Lo = 1e9f, Hi = -1e9f;
    for (float O = -900.f; O <= 900.f; O += 20.f) if (IsRoad(World, Along + Right * O, Ignore)) { Lo = FMath::Min(Lo, O); Hi = FMath::Max(Hi, O); }
    if (Lo > Hi) return false;
    FVector Ground; IsRoad(World, Along + Right * (.5f * (Lo + Hi)), Ignore, &Ground);
    Centre = Ground; UE_LOG(LogTemp, Display, TEXT("FIGHT FILM road %.0f..%.0f cm across at %s"), Lo, Hi, *Centre.ToString());
    return true;
}

static FVector2D IntentToward(AWandererCharacter* P, const FVector& WorldDir)
{
    // MoveIntent is camera-relative (X right, Y forward).
    const FRotationMatrix Basis(FRotator(0, P->GetControlRotation().Yaw, 0));
    const FVector D = WorldDir.GetSafeNormal2D();
    return FVector2D(FVector::DotProduct(D, Basis.GetUnitAxis(EAxis::Y)), FVector::DotProduct(D, Basis.GetUnitAxis(EAxis::X)));
}

static void BuildSteps(FFightFilm& F)
{
    AWandererCharacter* P = F.P; AFoxHunter* Fox = F.Fox; UWandererSwordComponent* S = F.S;
    auto Dist = [=]() { return FVector::Dist2D(Fox->GetActorLocation(), P->GetActorLocation()); };
    auto ToFox = [=]() { FVector D = Fox->GetActorLocation() - P->GetActorLocation(); D.Z = 0; return D.GetSafeNormal(); };
    auto InWindup = [=](float Lead) { const FFoxHunterClip* C = Fox->GetDefinition()->FindClip(Fox->GetAnimationAction()); return Fox->GetState() == EFoxState::Attack && C && C->HitStart > 0.f && Fox->GetActionTime() >= C->HitStart - Lead && Fox->GetActionTime() < C->HitStart; };
    auto Tap = [=]() { S->AttackPressed(); S->AttackReleased(); };
    auto Guarding = [=]() { return S->GetState() == ESwordState::Guard && !S->IsDown(); };
    F.Steps = {
        { TEXT("settle"), nullptr, nullptr, [&F]() { return F.StepTime > .8f; }, 2.f },
        { TEXT("walk up"), nullptr, [=]() { P->Review_Move(IntentToward(P, ToFox()) * .62f); },
          [=]() { return Fox->GetState() != EFoxState::Idle; }, 8.f },
        { TEXT("draw"), [=]() { P->Review_Move(FVector2D::ZeroVector); S->ToggleWeapon(); }, nullptr,
          [=]() { return Guarding() && (Fox->GetState() == EFoxState::Stalk) && Dist() < 180.f; }, 7.f },
        { TEXT("parry and counter"), [&F, Fox]() { F.Mark = Fox->HitsTaken; Fox->ForceNextAttack(TEXT("AttackR_A")); }, nullptr,
          [&F, Fox, Guarding]() { return Fox->HitsTaken > F.Mark && Guarding(); }, 9.f },
        { TEXT("roll under the kick"), [&F, Fox]() { F.Mark = Fox->StrikesDodged + Fox->StrikesMissed; F.bPressed = false; Fox->ForceNextAttack(TEXT("Kick")); },
          [&F, P, Fox, InWindup, ToFox]() {
              if (!F.bPressed && InWindup(.2f))
              {
                  // Roll back out of the kick along the road (it is under 5 m wide: a sideways roll ends in the verge),
                  // drifting toward the middle of the tarmac.
                  F.bPressed = true;
                  const FVector RoadFwd = FRotator(0, F.RoadYaw, 0).Vector(), RoadRight = FRotationMatrix(FRotator(0, F.RoadYaw, 0)).GetUnitAxis(EAxis::Y);
                  const float Lateral = FVector::DotProduct(P->GetActorLocation() - F.RoadOrigin, RoadRight);
                  const FVector Dir = -RoadFwd * FMath::Sign(FVector::DotProduct(ToFox(), RoadFwd) + 1e-3f) - RoadRight * FMath::Clamp(Lateral / 150.f, -.5f, .5f);
                  P->Review_Move(IntentToward(P, Dir)); P->Review_Dodge();
              }
              if (F.bPressed && P->GetAnimationAction() != TEXT("Roll")) P->Review_Move(FVector2D::ZeroVector); },
          [&F, P, Fox]() { return F.bPressed && Fox->StrikesDodged + Fox->StrikesMissed > F.Mark && P->GetAnimationAction() != TEXT("Roll"); }, 9.f },
        { TEXT("draw again"), [=]() { P->Review_Move(FVector2D::ZeroVector); S->ToggleWeapon(); }, nullptr, [=]() { return Guarding(); }, 3.f },
        { TEXT("take a claw"), [&F, Fox]() { F.Mark = Fox->StrikesLanded; Fox->ForceNextAttack(TEXT("AttackL_B")); }, nullptr,
          [&F, Fox]() { return Fox->StrikesLanded > F.Mark && F.StepTime > .1f; }, 9.f, true },
        { TEXT("recover"), [=]() { Fox->SetPassive(true); }, nullptr, [&F, Guarding]() { return F.StepTime > .7f && Guarding(); }, 3.f },
        { TEXT("three-strike chain"), [&F]() { F.NextTap = -1.f; F.Mark = 0; },
          [&F, P, S, Dist, Tap, Guarding]() {
              if (Guarding() && F.Mark == 0 && Dist() < 200.f) { Tap(); F.Mark = 1; F.NextTap = F.Clock + .2f; return; }
              if (S->GetState() == ESwordState::Attack && F.Mark < 3 && F.NextTap > 0.f && F.Clock >= F.NextTap) { Tap(); ++F.Mark; F.NextTap = F.Clock + .2f; } },
          [&F, Fox, Guarding]() { return F.Mark >= 3 && Guarding() && F.StepTime > 1.f; }, 8.f },
        { TEXT("breathe"), [=]() { Fox->SetPassive(false); }, nullptr, [&F]() { return F.StepTime > .6f; }, 2.f },
        { TEXT("cut into a full charge"), [&F, Fox]() { Fox->SetPassive(true); F.bPressed = false; F.HeldSince = -1.f; },
          [&F, S, Fox, Dist, Guarding]() {
              if (!F.bPressed && Guarding() && Dist() < 190.f && Fox->GetState() != EFoxState::Attack) { F.bPressed = true; S->AttackPressed(); }
              if (F.bPressed && S->GetState() == ESwordState::ChargeHold && S->ChargeFraction() >= 1.f)
              { if (F.HeldSince < 0.f) F.HeldSince = F.Clock; else if (F.Clock - F.HeldSince > .35f) { S->AttackReleased(); } } },
          [=]() { return !Fox->IsAlive(); }, 9.f },
        { TEXT("the hunter falls"), nullptr, nullptr, [&F]() { return F.StepTime > 1.4f; }, 2.f },
        { TEXT("sheathe"), [=]() { if (S->IsArmed() && S->GetState() == ESwordState::Guard) S->ToggleWeapon(); }, nullptr, [=]() { return Fox->IsHidden(); }, 6.f },
        { TEXT("hold"), nullptr, nullptr, [&F]() { return F.StepTime > 1.4f; }, 2.f },
    };
}

/** Frames both fighters from over the road: the view looks along the road from behind the player at a three-quarter
 *  angle (the verges are tall grass and bushes that would fill the lens from the side). */
static void UpdateCamera(FFightFilm& F, float Dt)
{
    AWandererCharacter* P = F.P; AFoxHunter* Fox = F.Fox;
    UCameraComponent* Camera = P->GetFollowCamera();
    if (!Fox->IsHidden()) F.LastFox = Fox->GetActorLocation();
    const FVector PL = P->GetActorLocation(), FL = F.LastFox;
    FVector Line = FL - PL; Line.Z = 0; const float Sep = Line.Size(); Line = Line.GetSafeNormal();
    const bool bEngaged = Fox->GetState() != EFoxState::Idle;
    // The fight line's heading, held within 35 degrees of the road so the lens stays over the tarmac.
    float Delta = FMath::FindDeltaAngleDegrees(F.RoadYaw, Line.Rotation().Yaw);
    if (FMath::Abs(Delta) > 100.f) Delta = 0.f;
    const float Heading = F.RoadYaw + FMath::Clamp(Delta, -35.f, 35.f);
    FVector WantFocus; float WantYaw, WantDist, WantPitch;
    if (!bEngaged && F.Step <= 1)
    {
        WantFocus = PL + Line * 140.f + FVector(0, 0, 55);
        WantYaw = Heading + 14.f * F.Side; WantDist = 560.f; WantPitch = -11.f;
    }
    else if (Fox->IsAlive())
    {
        WantFocus = (PL + FL) * .5f + FVector(0, 0, 40);
        WantYaw = Heading + 30.f * F.Side; WantDist = FMath::Clamp(Sep * 1.05f + 300.f, 430.f, 680.f) * (1.f - .12f * F.Push); WantPitch = -11.f;
    }
    else
    {
        // The body burning away, seen from the side with the player at the edge of the frame.
        WantFocus = FL + FVector(0, 0, -45.f);
        WantYaw = Line.Rotation().Yaw + (75.f + 3.f * F.StepTime) * F.Side; WantDist = 380.f; WantPitch = -17.f;
    }
    // Keep a clear line of sight: if the view from this side is blocked (a pole, a wall) for a moment, film from the other side.
    {
        FCollisionQueryParams Q(SCENE_QUERY_STAT(FilmCameraClear), false, P); Q.AddIgnoredActor(Fox);
        auto Clear = [&](float Yaw) { const FVector E = WantFocus - FRotator(WantPitch, Yaw, 0).Vector() * WantDist; FHitResult H;
            return !P->GetWorld()->SweepSingleByChannel(H, WantFocus, E, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(25.f), Q); };
        if (!Clear(WantYaw)) F.Blocked += Dt; else F.Blocked = 0.f;
        const float Other = WantYaw + (WantYaw - (bEngaged ? (Fox->IsAlive() ? Heading : Line.Rotation().Yaw) : Heading)) * -2.f;
        if (F.Blocked > .2f && Clear(Other)) { F.Side = -F.Side; WantYaw = Other; F.Blocked = 0.f; F.Note(TEXT("camera changes side")); }
    }
    if (!F.bCamInit) { F.Focus = WantFocus; F.Yaw = WantYaw; F.Distance = WantDist; F.Pitch = WantPitch; F.bCamInit = true; }
    F.Focus = FMath::VInterpTo(F.Focus, WantFocus, Dt, 3.f);
    F.Yaw = F.Yaw + FMath::FindDeltaAngleDegrees(F.Yaw, WantYaw) * FMath::Clamp(Dt * 1.6f, 0.f, 1.f);
    F.Distance = FMath::FInterpTo(F.Distance, WantDist, Dt, 1.6f);
    F.Pitch = FMath::FInterpTo(F.Pitch, WantPitch, Dt, 2.f);
    F.Push = FMath::FInterpTo(F.Push, 0.f, Dt, 1.2f);
    const FRotator View(F.Pitch, F.Yaw, 0.f);
    FVector Eye = F.Focus - View.Vector() * F.Distance;
    FHitResult Hit; FCollisionQueryParams Q(SCENE_QUERY_STAT(FilmCamera), false, P); Q.AddIgnoredActor(Fox);
    if (P->GetWorld()->LineTraceSingleByChannel(Hit, F.Focus, Eye, ECC_Camera, Q) && Hit.Distance > 180.f) Eye = Hit.Location + (F.Focus - Eye).GetSafeNormal() * 20.f;
    if (P->GetWorld()->LineTraceSingleByChannel(Hit, Eye + FVector(0, 0, 400), Eye - FVector(0, 0, 400), ECC_Visibility, Q) && Eye.Z < Hit.ImpactPoint.Z + 90.f) Eye.Z = Hit.ImpactPoint.Z + 90.f;
    FVector Shake; FRotator ShakeRot; P->SampleShake(Shake, ShakeRot);
    Camera->SetWorldLocationAndRotation(Eye + View.RotateVector(Shake), (F.Focus - Eye).Rotation() + ShakeRot);
    Camera->SetFieldOfView(F.Fov);
    // The player's controls stay camera-relative to what the viewer sees.
    if (P->Controller) P->Controller->SetControlRotation(FRotator(0, F.Yaw, 0));
}

static void Finish(FFightFilm& F)
{
    FString Audio = TEXT("[\n");
    for (int32 I = 0; I < FJapanAudioLog::Events.Num(); ++I)
    {
        const FJapanAudioEvent& E = FJapanAudioLog::Events[I];
        Audio += FString::Printf(TEXT("  {\"frame\":%d,\"sound\":\"%s\",\"source\":\"%s\",\"x\":%.1f,\"y\":%.1f,\"z\":%.1f,\"volume\":%.3f,\"pitch\":%.3f,\"2d\":%s}%s\n"), E.Frame, *E.Sound, *E.Source.Replace(TEXT("\\"), TEXT("/")),
            E.At.X, E.At.Y, E.At.Z, E.Volume, E.Pitch, E.b2D ? TEXT("true") : TEXT("false"), I + 1 < FJapanAudioLog::Events.Num() ? TEXT(",") : TEXT(""));
    }
    Audio += TEXT("]\n");
    FFileHelper::SaveStringToFile(Audio, *(F.Dir / TEXT("audio.json")));
    FFileHelper::SaveStringToFile(F.CameraCsv, *(F.Dir / TEXT("camera.csv")));
    FString Lines; for (const FString& L : F.Log) { if (!Lines.IsEmpty()) Lines += TEXT(","); Lines += TEXT("\"") + L + TEXT("\""); }
    UWandererSwordComponent* S = F.S; AFoxHunter* Fox = F.Fox;
    const FString Result = FString::Printf(TEXT("{\"frames\":%d,\"fps\":60,\"fox_attacks\":%d,\"landed\":%d,\"parried\":%d,\"dodged\":%d,\"fox_hits_taken\":%d,\"fox_deaths\":%d,\"player_health\":%.0f,\"sounds\":%d,\"log\":[%s]}\n"),
        F.Captured, Fox->Attacks, Fox->StrikesLanded, Fox->StrikesParried, Fox->StrikesDodged, Fox->HitsTaken, Fox->Deaths, S->GetHealth(), FJapanAudioLog::Events.Num(), *Lines);
    FFileHelper::SaveStringToFile(Result, *(F.Dir / TEXT("film.json")));
    UE_LOG(LogTemp, Display, TEXT("FIGHT FILM COMPLETE %s"), *Result);
    FJapanAudioLog::bRecording = false;
    UGameViewportClient::OnScreenshotCaptured().Remove(F.Capture);
    FPlatformMisc::RequestExit(false);
}

void AdvanceFightFilm(FFightFilm& F, float)
{
    const float Dt = FApp::GetDeltaTime();   // real frame step: hit-stop freezes the player's own clock
    AWandererCharacter* P = F.P;
    if (F.bDone) return;
    if (!F.Fox) { if (TActorIterator<AFoxHunter> It(P->GetWorld()); It) F.Fox = *It; if (!F.Fox) return; }
    if (!F.Fox->IsReady() || !P->GetSword() || !P->GetSword()->IsInstalled()) return;
    F.S = P->GetSword();
    if (!F.bStarted)
    {
        // Let streaming, shaders and the lighting settle before the first frame is kept.
        if (P->GetFollowCamera()->GetAttachParent()) P->GetFollowCamera()->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        F.Warm += Dt; if (F.Warm < 4.f) { UpdateCamera(F, Dt); return; }
        F.bStarted = true;
        FParse::Value(FCommandLine::Get(), TEXT("reviewdir="), F.Dir);
        if (F.Dir.IsEmpty()) F.Dir = FPaths::ProjectSavedDir() / TEXT("Screenshots/FightFilm") / FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
        IFileManager::Get().MakeDirectory(*F.Dir, true);
        F.Fox->SetSeed(11);
        F.RoadYaw = P->GetActorRotation().Yaw; F.RoadOrigin = P->GetActorLocation();
        {
            // The fight is staged on the middle of the road (the verges hold poles, the guardrail and tall grass): find the
            // tarmac's centre line near the start and 11 m on, start the player on it and let the hunter wait there.
            UWorld* World = P->GetWorld();
            const FVector Fwd = FRotator(0, F.RoadYaw, 0).Vector(), Right = FRotationMatrix(FRotator(0, F.RoadYaw, 0)).GetUnitAxis(EAxis::Y);
            FVector A, B;
            const bool bA = RoadCentre(World, P->GetActorLocation() - Fwd * 200.f, Right, P, A), bB = bA && RoadCentre(World, P->GetActorLocation() + Fwd * 1000.f, Right, P, B);
            if (bA && bB)
            {
                F.RoadYaw = (B - A).Rotation().Yaw; F.RoadOrigin = A;
                const FVector Start = A + (B - A).GetSafeNormal2D() * 150.f;
                P->TravelTo(Start, F.RoadYaw, TEXT("Fight film"));
                P->GetFollowCamera()->SetWorldRotation(FRotator(-10, F.RoadYaw, 0));
                if (P->Controller) P->Controller->SetControlRotation(FRotator(0, F.RoadYaw, 0));
            }
            else F.Note(TEXT("road centre not found: staging from the spawn"));
            FVector Where = (bA && bB) ? B + (B - A).GetSafeNormal2D() * 50.f : P->GetActorLocation() + Fwd * 1100.f;
            FHitResult Ground; FCollisionQueryParams Q(SCENE_QUERY_STAT(FilmFox), false, P); Q.AddIgnoredActor(F.Fox);
            const float Half = F.Fox->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
            if (World->LineTraceSingleByChannel(Ground, Where + FVector(0, 0, 500), Where - FVector(0, 0, 800), ECC_Visibility, Q)) Where.Z = Ground.ImpactPoint.Z + Half + 2.f;
            F.Fox->SetActorLocation(Where, false, nullptr, ETeleportType::TeleportPhysics);
            F.Fox->SetActorRotation(FRotator(0, F.RoadYaw + 180.f, 0)); F.Fox->SetHome(Where, F.RoadYaw + 180.f);
        }
        F.bCamInit = false;
        FFightFilm* Film = &F;
        F.Capture = UGameViewportClient::OnScreenshotCaptured().AddLambda([Film](int32 W, int32 H, const TArray<FColor>& Pixels)
        {
            if (Film->Pending < 0) return;
            TArray<FColor> Opaque = Pixels; for (FColor& C : Opaque) C.A = 255;
            FImageUtils::SaveImageByExtension(*(Film->Dir / FString::Printf(TEXT("frame_%05d.jpg"), Film->Pending)), FImageView(Opaque.GetData(), W, H), 95);
            Film->Pending = -1;
        });
        BuildSteps(F);
        FJapanAudioLog::Events.Reset(); FJapanAudioLog::bRecording = true;
        F.Step = 0; F.StepTime = 0.f; F.Note(TEXT("step 0: settle"));
    }
    F.Clock += Dt; F.StepTime += Dt;
    FJapanAudioLog::Frame = F.Captured;
    FFightFilm::FStep& Current = F.Steps[F.Step];
    // Keep the take on script: parry any attack this step did not ask to land.
    const FFoxHunterClip* C = F.Fox->GetDefinition()->FindClip(F.Fox->GetAnimationAction());
    if (!Current.bAllowHit && F.Fox->GetState() == EFoxState::Attack && C && F.Fox->Attacks != F.ParriedAttack && F.Fox->GetActionTime() >= C->HitStart - .19f
        && F.S->GetState() == ESwordState::Guard && P->GetAnimationAction() != TEXT("Roll") && Current.Name != TEXT("roll under the kick"))
    { F.ParriedAttack = F.Fox->Attacks; F.S->ParryPressed(); F.Push = 1.f; F.Note(TEXT("parry")); }
    if (F.S->GetState() == ESwordState::ChargeRelease) F.Push = FMath::Max(F.Push, .8f);
    if (Current.Each) Current.Each();
    const bool bStepDone = Current.Done && Current.Done();
    if (bStepDone || F.StepTime > Current.Timeout)
    {
        F.Note(FString::Printf(TEXT("%s %s"), *Current.Name, bStepDone ? TEXT("done") : TEXT("TIMED OUT")));
        ++F.Step; F.StepTime = 0.f;
        if (F.Step >= F.Steps.Num()) { UpdateCamera(F, Dt); F.bDone = true; Finish(F); return; }
        if (F.Steps[F.Step].Enter) F.Steps[F.Step].Enter();
        F.Note(FString::Printf(TEXT("step %d: %s"), F.Step, *F.Steps[F.Step].Name));
    }
    UpdateCamera(F, Dt);
    if (F.Clock > 70.f) { F.Note(TEXT("film time limit")); F.bDone = true; Finish(F); return; }
    // One kept frame per fixed step.
    UCameraComponent* Camera = P->GetFollowCamera();
    const FVector E = Camera->GetComponentLocation(); const FRotator R = Camera->GetComponentRotation();
    F.CameraCsv += FString::Printf(TEXT("%d,%.1f,%.1f,%.1f,%.2f,%.2f,%.2f,%.1f,%d\n"), F.Captured, E.X, E.Y, E.Z, R.Pitch, R.Yaw, R.Roll, Camera->FieldOfView, F.Step);
    F.Pending = F.Captured++;
    FScreenshotRequest::RequestScreenshot(true);
}
