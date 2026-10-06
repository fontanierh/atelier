#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Animation/AnimInstance.h"
#include "Engine/World.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Misc/FileHelper.h"
#include "Misc/App.h"

// Opt-in -cairoqa exercises the actual pawn/controller/animation graph. Temporary
// collision floor and command-line preferences leave the user's world unchanged.
void AWandererCharacter::AdvanceCairoReview(float Dt)
{
    auto* M=GetCharacterMovement();
    auto Check=[&](bool Pass,const FString& Label)
    {
        UE_LOG(LogTemp,Display,TEXT("CAIRO QA %s: %s"),Pass?TEXT("PASS"):TEXT("FAIL"),*Label);
        if(!Pass)CairoErrors.Add(Label);
    };
    if(CairoTime==0.f)
    {
        FApp::SetFixedDeltaTime(1./60.);FApp::SetUseFixedTimeStep(true);
        if(FParse::Param(FCommandLine::Get(),TEXT("caironoshadow")))GetMesh()->SetCastShadow(false);
        CairoOrigin=GetActorLocation()+FVector(0,0,2000);
        auto* Floor=GetWorld()->SpawnActor<AActor>();
        auto* Box=NewObject<UBoxComponent>(Floor);Floor->SetRootComponent(Box);Floor->AddInstanceComponent(Box);
        Box->SetBoxExtent(FVector(15000,3000,50));Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
        Floor->SetActorLocation(CairoOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+52));
        // A visible, non-colliding surface makes support/roll contact reviewable.
        auto* Surface=GetWorld()->SpawnActor<AStaticMeshActor>();
        Surface->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        Surface->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
        Surface->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Surface->GetStaticMeshComponent()->SetCastShadow(false);
        Surface->SetActorLocation(Floor->GetActorLocation());
        Surface->SetActorScale3D(FVector(300,60,1));
        TravelTo(CairoOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("Cairo QA"));
        CairoOrigin=GetActorLocation();ReviewForward=FVector::ForwardVector;
        Controller->SetControlRotation(FRotator::ZeroRotator);
        FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        Check(Definition->Mesh->GetName()==TEXT("SK_Cairo"),TEXT("new default mesh"));
        Check(Definition->Actions.Num()==25 && Definition->FindAction(TEXT("Roll")),TEXT("all 25 animation roles including Roll"));
        Check(GetMesh()->GetNumBones()==53,TEXT("53 bones including fingers"));
        Check(Definition->Mesh->FindMorphTarget(TEXT("head_Hair_fore")) && Definition->Mesh->FindMorphTarget(TEXT("head_Hair_side")),TEXT("both hair tip fields imported"));
        FParse::Value(FCommandLine::Get(),TEXT("cairoqastart="),CairoTime);
    }
    const float Previous=CairoTime;CairoTime+=Dt;const float T=CairoTime;
    const FVector2D Hair(GetMesh()->GetMorphTarget(TEXT("head_Hair_fore")),GetMesh()->GetMorphTarget(TEXT("head_Hair_side")));
    CairoMaxHair=FMath::Max(CairoMaxHair,float(Hair.Size()));
    auto At=[&](float Time){return Previous<Time&&T>=Time;};
    MoveIntent=FVector2D(0,T>=2&&T<8?1:0);
    bWalk=T>=2&&T<4;bJog=false;bSprintHeld=T>=6&&T<8;
    if(At(3.5f))Check(FMath::Abs(M->Velocity.Size2D()-Definition->WalkSpeed)<3,TEXT("walk speed matches stride"));
    if(At(5.5f))Check(FMath::Abs(M->Velocity.Size2D()-Definition->RunSpeed)<3,TEXT("run uses slowed sprint"));
    if(At(7.5f))Check(FMath::Abs(M->Velocity.Size2D()-GetSprintSpeed())<3,TEXT("sprint reaches tuned speed with rate-scaled stride"));
    if(At(7.5f))Check(CairoMaxHair>.001f && CairoMaxHair<=1.001f,TEXT("hair responds to motion with bounded tip flex"));
    if(At(8.5f))Dash(FInputActionValue(true));
    if(At(8.6f))Check(AnimationAction==TEXT("DashGround"),TEXT("ground dash starts"));
    if(At(8.65f))
    {
        Check(M->IsFalling()&&GetActorLocation().Z-CairoOrigin.Z>15.f,TEXT("ground dash is a real forward leap"));
        Check(M->Velocity.Size2D()>1000.f&&ActionDuration<.4f,TEXT("ground dash is short and fast"));
    }
    if(At(9.2f))Check(M->IsMovingOnGround(),TEXT("ground dash lands once and recovers"));
    if(At(10.f))RequestJump(FInputActionValue(true));
    if(At(10.35f))
    {
        Check(M->IsFalling(),TEXT("jump airborne"));RequestJump(FInputActionValue(true));
        Check(AnimationAction==TEXT("DoubleJump")&&bAirJumpUsed,TEXT("double jump starts"));
    }
    if(At(10.55f))
    {
        const uint32 Serial=ActionSerial;RequestJump(FInputActionValue(true));
        Check(Serial==ActionSerial,TEXT("third jump rejected"));
        Dodge(FInputActionValue(true));Check(Serial==ActionSerial,TEXT("ground roll rejected in the air"));
        Dash(FInputActionValue(true));Check(Serial==ActionSerial,TEXT("dash cannot cut flip tuck short"));
    }
    if(At(11.01f))
    {
        Dash(FInputActionValue(true));
        Check(AnimationAction==TEXT("DashAir")&&bAirDashUsed&&bAirJumpUsed,TEXT("air dash preserves spent double jump"));
    }
    if(At(11.1f))Check(AnimationAction==TEXT("DashAir")&&ActionDuration<.25f&&M->Velocity.Size2D()>1000.f,TEXT("air dash is short and fast"));
    if(At(12.8f))Check(M->IsMovingOnGround()&&!bAirDashUsed&&!bAirJumpUsed,TEXT("landing restores air abilities"));
    if(At(13.2f))RequestJump(FInputActionValue(true));
    if(At(13.45f)){Dash(FInputActionValue(true));Check(!bAirJumpUsed&&bAirDashUsed,TEXT("air dash leaves double jump available"));}
    if(At(13.8f)){RequestJump(FInputActionValue(true));Check(bAirJumpUsed,TEXT("double jump after air dash"));}
    if(At(16.f)){ToggleCrouch(FInputActionValue(true));}
    if(T>=16.5f&&T<18.f)MoveIntent=FVector2D(0,1);
    if(At(18.f)){ToggleCrouch(FInputActionValue(true));}
    if(At(18.5f))Wave(FInputActionValue(true));
    if(At(21.1f))Interact(FInputActionValue(true));
    if(At(23.f))Dodge(FInputActionValue(true));
    // Remaining authored roles get a native-graph gallery after controller QA.
    const TCHAR* Gallery[]={TEXT("SitDown"),TEXT("SitIdle"),TEXT("StandUp"),TEXT("Climb"),TEXT("Glide"),TEXT("TurnLeft"),TEXT("TurnRight"),TEXT("HardLand")};
    for(int32 I=0;I<8;++I)if(At(25.f+I*2.f))SetAction(Gallery[I],I==1||I==3||I==4,.12f);
    if(T>=25.f && T<41.f)M->StopMovementImmediately();
    const FVector2D RollDirections[]={FVector2D(0,1),FVector2D(1,0),FVector2D(0,-1),FVector2D(-1,0),
        FVector2D(.707107,.707107),FVector2D(.707107,-.707107),FVector2D(-.707107,-.707107),FVector2D(-.707107,.707107)};
    for(int32 I=0;I<8;++I)
    {
        const float Start=42.f+I*2.f;
        if(At(Start))
        {
            TravelTo(CairoOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll direction QA"));
            M->SetMovementMode(MOVE_Walking);
            Controller->SetControlRotation(FRotator::ZeroRotator);
            CairoRollOrigin=GetActorLocation();CairoRollInverted=false;MoveIntent=RollDirections[I];
            Dodge(FInputActionValue(true));
            Check(AnimationAction==TEXT("Roll"),FString::Printf(TEXT("roll direction %d starts"),I));
            const uint32 Serial=ActionSerial;
            Dodge(FInputActionValue(true));Dash(FInputActionValue(true));RequestJump(FInputActionValue(true));
            Check(Serial==ActionSerial,FString::Printf(TEXT("roll direction %d cannot be interrupted"),I));
        }
        if(At(Start+1.35f))
        {
            const FVector Direction(RollDirections[I].Y,RollDirections[I].X,0);
            const FVector Travel=GetActorLocation()-CairoRollOrigin;
            Check(FVector::DotProduct(Travel,Direction)>100.f && FMath::Abs(FVector::DotProduct(Travel,Direction.RotateAngleAxis(90,FVector::UpVector)))<3.f,
                FString::Printf(TEXT("roll direction %d travels along its input including diagonals"),I));
            Check(CairoRollInverted && AnimationAction!=TEXT("Roll") && M->IsMovingOnGround(),FString::Printf(TEXT("roll direction %d rotates and recovers"),I));
        }
    }
    if(At(58.f))
    {
        TravelTo(CairoOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll wall QA"));
        M->SetMovementMode(MOVE_Walking);CairoRollOrigin=GetActorLocation();
        CairoRollObstacle=GetWorld()->SpawnActor<AActor>();
        auto* Box=NewObject<UBoxComponent>(CairoRollObstacle);CairoRollObstacle->SetRootComponent(Box);
        CairoRollObstacle->AddInstanceComponent(Box);Box->SetBoxExtent(FVector(20,180,180));
        Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
        CairoRollObstacle->SetActorLocation(CairoRollOrigin+FVector(130,0,70));
        MoveIntent=FVector2D(0,1);Dodge(FInputActionValue(true));
    }
    if(At(59.4f))
    {
        const double Travel=GetActorLocation().X-CairoRollOrigin.X;
        Check(Travel>40 && Travel<110 && AnimationAction!=TEXT("Roll"),TEXT("roll capsule stops at wall and action recovers"));
        CairoRollObstacle->Destroy();CairoRollObstacle=nullptr;
    }
    if(At(60.f))
    {
        TravelTo(CairoOrigin+FVector(14890,0,-GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll ledge QA"));
        M->SetMovementMode(MOVE_Walking);MoveIntent=FVector2D(0,1);Dodge(FInputActionValue(true));
    }
    if(At(60.7f))Check(M->IsFalling() && M->Velocity.Z<-50.f,TEXT("roll leaving a ledge falls instead of hovering"));
    if(At(61.2f))
    {
        Check(AnimationAction!=TEXT("Roll"),TEXT("ledge roll opens into falling pose"));
        TravelTo(CairoOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll QA complete"));
    }
    const FVector Target=GetActorLocation()+FVector(0,0,8);
    FVector View=T<1?FVector(-350,0,65):T<2?FVector(350,0,65):FVector(70,350,80);
    float CameraScale=1.f;FParse::Value(FCommandLine::Get(),TEXT("cairocamerascale="),CameraScale);
    FString CameraView;FParse::Value(FCommandLine::Get(),TEXT("cairoview="),CameraView);
    if(CameraView==TEXT("front"))View=FVector(350,0,65);
    else if(CameraView==TEXT("back"))View=FVector(-350,0,65);
    else if(CameraView==TEXT("side"))View=FVector(0,350,65);
    View*=FMath::Clamp(CameraScale,.5f,2.f);
    FollowCamera->SetWorldLocationAndRotation(Target+View,(-View).Rotation());
    const FQuat Pelvis=GetMesh()->GetSocketTransform(TEXT("pelvis"),RTS_Component).GetRotation();
    const FQuat Bind=Definition->Mesh->GetRefSkeleton().GetRefBonePose()[GetMesh()->GetBoneIndex(TEXT("pelvis"))].GetRotation();
    const float Up=(Pelvis*Bind.Inverse()).GetUpVector().Z;
    if(AnimationAction==TEXT("DoubleJump")&&Up<-.65f)CairoInverted=true;
    if(AnimationAction==TEXT("Roll")&&Up<-.65f)CairoRollInverted=true;
    const float Waist=GetMesh()->GetAnimInstance()->GetCurveValue(TEXT("shorts_Waist_shirt_clearance"));
    CairoMaxWaist=FMath::Max(CairoMaxWaist,Waist);
    CairoTelemetry+=FString::Printf(TEXT("%.4f,%s,%.3f,%.3f,%d,%d,%d,%.5f,%.5f\n"),T,*AnimationAction.ToString(),M->Velocity.Size2D(),GetActorLocation().Z-CairoOrigin.Z,M->IsFalling(),bAirJumpUsed,bAirDashUsed,Up,Waist);
    if(FParse::Param(FCommandLine::Get(),TEXT("cairofilm")))RecordFrame();
    else for(float Shot:{1.f,3.f,5.f,6.3f,6.65f,7.f,8.8f,10.65f,11.2f,16.9f,19.2f,21.8f,23.3f,25.7f,27.7f,29.7f,31.7f,33.7f,35.5f,37.5f,39.5f})if(At(Shot))
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("cairo_%04d.png"),FMath::RoundToInt(Shot*100)),false,false);
    float End=63.f;FParse::Value(FCommandLine::Get(),TEXT("cairoqaseconds="),End);
    if(T>=End)
    {
        if(End>=41.f)Check(CairoInverted,TEXT("double jump visibly flips pelvis"));
        if(End>=8.f)Check(CairoMaxWaist>.25f,TEXT("waist corrective survives runtime graph"));
        FFileHelper::SaveStringToFile(CairoTelemetry,*(ReviewDirectory/TEXT("cairo.csv")));
        FString Errors;for(const auto& Error:CairoErrors){if(!Errors.IsEmpty())Errors+=TEXT(",");Errors+=TEXT("\"")+Error+TEXT("\"");}
        const FString Result=FString::Printf(TEXT("{\"passed\":%s,\"errors\":[%s],\"max_waist_curve\":%.6f,\"max_hair_flex\":%.6f}\n"),CairoErrors.IsEmpty()?TEXT("true"):TEXT("false"),*Errors,CairoMaxWaist,CairoMaxHair);
        FFileHelper::SaveStringToFile(Result,*(ReviewDirectory/TEXT("result.json")));
        UE_LOG(LogTemp,Display,TEXT("CAIRO QA COMPLETE %s"),*Result);FPlatformMisc::RequestExit(false);
    }
}
