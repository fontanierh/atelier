#include "WandererCharacter.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "InputKeyEventArgs.h"
#include "Engine/GameViewportClient.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

// Opt-in input/pose capture. A road-following direction lets the camera show the
// side and rear while the real movement inputs drive the gait and acceleration.
void AWandererCharacter::AdvanceLocomotionReview(float Dt)
{
    const float Previous = ReviewTime;
    ReviewTime += Dt;
    APlayerController* PC = CastChecked<APlayerController>(Controller);
    if (bRecordReview && PC->GetHUD()) PC->GetHUD()->bShowHUD = false;
    if (Previous == 0.f) SetMouseReleased(false);
    auto Key = [&](float At,FKey K,bool Down)
    {
        if (Previous < At && ReviewTime >= At)
            PC->InputKey(FInputKeyEventArgs::CreateSimulated(K,Down ? IE_Pressed : IE_Released,Down ? 1.f : 0.f,1));
    };
    if (bRecordReview)
    {
        // Offline frames take longer than game time. Desktop focus changes or
        // remote device reconnects must not release the recorded held actions.
        // The real-time QA below still exercises the physical key bindings.
        const bool Moving = (ReviewTime >= 1.f && ReviewTime < 16.f) || (ReviewTime >= 18.f && ReviewTime < 21.f);
        Move(FInputActionValue(FVector2D(0.f,Moving ? 1.f : 0.f)));
        Jog(FInputActionValue(ReviewTime >= 4.f && ReviewTime < 13.f));
        Walk(FInputActionValue(ReviewTime >= 7.f && ReviewTime < 10.f));
    }
    else
    {
        Key(1.f,EKeys::W,true);                  // No modifier: run.
        Key(4.f,EKeys::LeftShift,true);          // Hold Shift: jog.
        Key(7.f,EKeys::LeftAlt,true);            // Alt takes priority: walk.
        Key(10.f,EKeys::LeftAlt,false);          // Return to held jog.
        Key(13.f,EKeys::LeftShift,false);        // Return to default run.
        Key(16.f,EKeys::W,false);                // Stop and restart from idle.
        Key(18.f,EKeys::W,true);
        Key(21.f,EKeys::W,false);
    }
    // The longer run leaves the original straight QA segment. Follow the road
    // centre instead of eventually testing a collision with its curved guardrail.
    ReviewForward = FRotator(0,GetActorRotation().Yaw+GetRoadSteering()*120.f*Dt,0).Vector();
    const float Orbit = ReviewTime < 12.5f ? 85.f : 0.f;
    const FRotator Target(-8.f,ReviewForward.Rotation().Yaw+Orbit,0.f);
    PC->SetControlRotation(FMath::RInterpTo(PC->GetControlRotation(),Target,Dt,5.f));
    if (ReviewTime >= 22.f)
    {
        FFileHelper::SaveStringToFile(LocomotionTelemetry,*(ReviewDirectory/TEXT("locomotion.csv")));
        UE_LOG(LogTemp,Display,TEXT("LOCOMOTION QA COMPLETE"));
        FPlatformMisc::RequestExit(false);
        return;
    }
    if (bRecordReview)
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("frame_%05d.png"),ReviewFrame++),false,false);
    else
        for (float At : {2.f,3.f,5.f,8.f,11.f,14.f,15.f,17.f,19.f,20.f})
            if (Previous < At && ReviewTime >= At)
                FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("pose_%02d.png"),FMath::RoundToInt(At)),false,false);
}

void AWandererCharacter::RecordLocomotionPose()
{
    if (!bReady || ReviewTime <= 0.f || ReviewTime >= 22.f) return;
    const USkeletalMeshComponent* Mesh = GetMesh();
    const FVector Left = Mesh->GetBoneLocation(TEXT("foot_L"),EBoneSpaces::ComponentSpace);
    const FVector Right = Mesh->GetBoneLocation(TEXT("foot_R"),EBoneSpaces::ComponentSpace);
    const float Head = Mesh->GetBoneLocation(TEXT("head"),EBoneSpaces::ComponentSpace).Z;
    const float Pelvis = Mesh->GetBoneLocation(TEXT("pelvis"),EBoneSpaces::ComponentSpace).Z;
    LocomotionTelemetry += FString::Printf(TEXT("%.6f,%.4f,%d,%d,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f\n"),
        ReviewTime,GetVelocity().Size2D(),bWalk,bJog,Head,Pelvis,Left.X,Left.Y,Left.Z,Right.X,Right.Y,Right.Z);
}
