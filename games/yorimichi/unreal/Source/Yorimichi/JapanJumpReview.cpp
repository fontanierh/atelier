#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/World.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/GameViewportClient.h"
#include "Misc/FileHelper.h"
#include "Misc/App.h"

// Explicit -jumpqa only: real CharacterMovement on an isolated temporary floor.
// No map assets or saved user preferences are changed.
void AWandererCharacter::AdvanceJumpReview(float Dt)
{
    auto* M=GetCharacterMovement();
    auto Check=[&](bool Pass,const FString& Name)
    {
        UE_LOG(LogTemp,Display,TEXT("JUMP QA %s: %s"),Pass?TEXT("PASS"):TEXT("FAIL"),*Name);
        if(!Pass)JumpReviewErrors.Add(Name);
    };
    if(JumpReviewTime==0.f)
    {
        FApp::SetFixedDeltaTime(1./60.);FApp::SetUseFixedTimeStep(true);
        JumpReviewOrigin=GetActorLocation()+FVector(0,0,1500);
        auto* Floor=GetWorld()->SpawnActor<AActor>();
        auto* Box=NewObject<UBoxComponent>(Floor);Floor->SetRootComponent(Box);Floor->AddInstanceComponent(Box);
        Box->SetBoxExtent(FVector(10000,2000,50));Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
        Floor->SetActorLocation(JumpReviewOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+52));
        Check(TravelTo(JumpReviewOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("jump QA floor")),TEXT("floor setup"));
        JumpReviewOrigin=GetActorLocation();
        ReviewForward=FVector::ForwardVector;
        FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        Check(Definition->FindAction(TEXT("DoubleJump"))!=nullptr,TEXT("front flip asset available"));
    }
    const float Previous=JumpReviewTime;
    JumpReviewTime+=Dt;const float T=JumpReviewTime;
    auto At=[&](float Time){return Previous<Time && T>=Time;};
    auto Reset=[&]()
    {
        Check(TravelTo(JumpReviewOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("jump QA reset")),TEXT("teleport reset"));
        Check(!bAirJumpUsed&&!bGroundJumped&&!bPendingTakeoff,TEXT("teleport clears jump state"));
    };
    MoveIntent=FVector2D(0,T<9.f?1.f:0.f);
    if(At(1.f)||At(4.f)||At(7.f)||At(10.f))RequestJump(FInputActionValue(true));
    if(At(1.03f)||At(4.03f)||At(7.03f)||At(10.03f))ReleaseJump(FInputActionValue(false));
    if(At(4.30f)||At(7.30f)||At(10.30f))
    {
        Check(M->IsFalling(),TEXT("second press is airborne"));
        const FVector Before=M->Velocity;
        RequestJump(FInputActionValue(true));
        Check(bAirJumpUsed && AnimationAction==TEXT("DoubleJump"),TEXT("second press starts front flip"));
        Check(FVector::DistSquared2D(Before,M->Velocity)<.01,TEXT("air jump preserves horizontal velocity"));
    }
    if(At(4.33f)||At(7.33f)||At(10.33f))ReleaseJump(FInputActionValue(false));
    if(At(4.50f)||At(4.65f)||At(7.50f))
    {
        const uint32 Before=ActionSerial;const FVector Velocity=M->Velocity;
        RequestJump(FInputActionValue(true));
        Check(ActionSerial==Before && M->Velocity.Equals(Velocity,.001f),TEXT("third jump rejected"));
    }
    if(T>1.f&&T<2.5f)JumpReviewSinglePeak=FMath::Max(JumpReviewSinglePeak,float(GetActorLocation().Z-JumpReviewOrigin.Z));
    if(T>4.f&&T<6.5f)JumpReviewDoublePeak=FMath::Max(JumpReviewDoublePeak,float(GetActorLocation().Z-JumpReviewOrigin.Z));
    if((T>1.f&&T<2.2f)||(T>4.f&&T<5.8f))JumpReviewMinSpeed=FMath::Min(JumpReviewMinSpeed,float(M->Velocity.Size2D()));
    const FTransform Root=GetMesh()->GetSocketTransform(TEXT("root"),RTS_Component);
    const FQuat Bind=GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton().GetRefBonePose()[GetMesh()->GetBoneIndex(TEXT("root"))].GetRotation();
    const float Up=(Root.GetRotation()*Bind.Inverse()).GetUpVector().Z;
    if(AnimationAction==TEXT("DoubleJump")&&Up<-.8f)bJumpReviewInverted=true;
    if(At(2.7f)||At(6.7f)||At(8.9f)||At(12.1f))
    {
        Check(M->IsMovingOnGround(),TEXT("landed upright"));
        Check(Up>.98f,TEXT("visual root upright after landing"));
        Check(!bAirJumpUsed&&!bGroundJumped,TEXT("landing replenishes jumps"));
    }
    if(At(3.f)||At(9.f))Reset();
    if(T>10.f&&T<11.8f)Check(M->Velocity.Size2D()<1.f,TEXT("standing jump adds no horizontal impulse"));
    if(At(12.3f))
    {
        RequestJump(FInputActionValue(true));SetMenuOpen(true);
        Check(JumpBuffer==0.f&&!bPendingTakeoff,TEXT("menu cancels buffered takeoff"));SetMenuOpen(false);
    }
    const FVector Target=GetActorLocation()+FVector(0,0,15);
    FollowCamera->SetWorldLocation(Target+FVector(60,420,65));
    FollowCamera->SetWorldRotation((Target-FollowCamera->GetComponentLocation()).Rotation());
    JumpReviewTelemetry+=FString::Printf(TEXT("%.5f,%.4f,%.4f,%.4f,%d,%d,%s,%.5f\n"),T,M->Velocity.Size2D(),GetActorLocation().Z-JumpReviewOrigin.Z,M->Velocity.Z,M->IsFalling(),bAirJumpUsed,*AnimationAction.ToString(),Up);
    if(FParse::Param(FCommandLine::Get(),TEXT("jumpqashots"))) for(float Shot:{4.38f,4.48f,4.60f,4.75f,4.90f,5.08f,5.45f})if(At(Shot))
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("jump_%03d.png"),FMath::RoundToInt(Shot*100)),false,false);
    if(At(13.f))
    {
        Reset();
        auto* Ceiling=GetWorld()->SpawnActor<AActor>();
        auto* Box=NewObject<UBoxComponent>(Ceiling);Ceiling->SetRootComponent(Box);Ceiling->AddInstanceComponent(Box);
        Box->SetBoxExtent(FVector(500,500,20));Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
        Ceiling->SetActorLocation(JumpReviewOrigin+FVector(0,0,125));
    }
    if(At(13.20f))RequestJump(FInputActionValue(true));
    if(At(13.23f))ReleaseJump(FInputActionValue(false));
    if(At(13.35f))
    {
        Check(M->IsFalling(),TEXT("low ceiling second press is airborne"));
        RequestJump(FInputActionValue(true));
        Check(bAirJumpUsed,TEXT("low ceiling consumes only one air jump"));
    }
    if(At(14.7f))
    {
        Check(M->IsMovingOnGround() && !bAirJumpUsed,TEXT("low ceiling landing recovers jump state"));
        Check(Up>.98f,TEXT("interrupted flip recovers upright"));
    }
    if(T>=15.f)
    {
        Check(JumpReviewMinSpeed>Definition->RunSpeed*2.f*.95f,TEXT("running speed survives takeoff, air and landing"));
        Check(JumpReviewDoublePeak>JumpReviewSinglePeak+70.f,TEXT("double jump is substantially higher"));
        Check(bJumpReviewInverted,TEXT("front flip passes through inverted pose"));
        FFileHelper::SaveStringToFile(JumpReviewTelemetry,*(ReviewDirectory/TEXT("jump.csv")));
        const FString Result=FString::Printf(TEXT("{\"passed\":%s,\"errors\":%d,\"single_height_cm\":%.3f,\"double_height_cm\":%.3f,\"min_running_speed\":%.3f}\n"),JumpReviewErrors.IsEmpty()?TEXT("true"):TEXT("false"),JumpReviewErrors.Num(),JumpReviewSinglePeak,JumpReviewDoublePeak,JumpReviewMinSpeed);
        FFileHelper::SaveStringToFile(Result,*(ReviewDirectory/TEXT("result.json")));
        UE_LOG(LogTemp,Display,TEXT("JUMP QA COMPLETE %s"),*Result);
        FPlatformMisc::RequestExit(false);
    }
}
