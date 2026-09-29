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

// Opt-in -warmqa exercises the actual pawn/controller/animation graph. Temporary
// collision floor and command-line preferences leave the user's world unchanged.
void AWandererCharacter::AdvanceWarmReview(float Dt)
{
    auto* M=GetCharacterMovement();
    const bool MovingRollReview=FParse::Param(FCommandLine::Get(),TEXT("warmrollqa"));
    const bool RollChainReview=FParse::Param(FCommandLine::Get(),TEXT("warmrollchainqa"));
    const bool AirTurnReview=FParse::Param(FCommandLine::Get(),TEXT("warmairturnqa"));
    auto Check=[&](bool Pass,const FString& Label)
    {
        UE_LOG(LogTemp,Display,TEXT("WARM QA %s: %s"),Pass?TEXT("PASS"):TEXT("FAIL"),*Label);
        if(!Pass)WarmErrors.Add(Label);
    };
    if(WarmTime==0.f)
    {
        FApp::SetFixedDeltaTime(1./60.);FApp::SetUseFixedTimeStep(true);
        if(FParse::Param(FCommandLine::Get(),TEXT("warmnoshadow")))GetMesh()->SetCastShadow(false);
        WarmOrigin=GetActorLocation()+FVector(0,0,2000);
        auto* Floor=GetWorld()->SpawnActor<AActor>();
        auto* Box=NewObject<UBoxComponent>(Floor);Floor->SetRootComponent(Box);Floor->AddInstanceComponent(Box);
        Box->SetBoxExtent(FVector(15000,3000,50));Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
        Floor->SetActorLocation(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+52));
        // A visible, non-colliding surface makes support/roll contact reviewable.
        auto* Surface=GetWorld()->SpawnActor<AStaticMeshActor>();
        Surface->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        Surface->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
        Surface->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Surface->GetStaticMeshComponent()->SetCastShadow(false);
        Surface->SetActorLocation(Floor->GetActorLocation());
        Surface->SetActorScale3D(FVector(300,60,1));
        TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("Warm QA"));
        WarmOrigin=GetActorLocation();ReviewForward=FVector::ForwardVector;
        Controller->SetControlRotation(FRotator::ZeroRotator);
        FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        Check(Definition->Mesh->GetName()==TEXT("SK_WarmOriginal"),TEXT("new default mesh"));
        Check(Definition->Actions.Num()==25 && Definition->FindAction(TEXT("Roll")),TEXT("all 25 animation roles including Roll"));
        Check(GetMesh()->GetNumBones()==53,TEXT("53 bones including fingers"));
        Check(Definition->Mesh->FindMorphTarget(TEXT("head_Hair_fore")) && Definition->Mesh->FindMorphTarget(TEXT("head_Hair_side")),TEXT("both hair tip fields imported"));
        if(MovingRollReview)WarmTime=63.f;
        if(RollChainReview)WarmTime=96.f;
        if(AirTurnReview)WarmTime=128.f;
        if(FParse::Param(FCommandLine::Get(),TEXT("warmflipqa")))WarmTime=9.f;
        FParse::Value(FCommandLine::Get(),TEXT("warmqastart="),WarmTime);
    }
    const float Previous=WarmTime;WarmTime+=Dt;const float T=WarmTime;
    const FVector2D Hair(GetMesh()->GetMorphTarget(TEXT("head_Hair_fore")),GetMesh()->GetMorphTarget(TEXT("head_Hair_side")));
    WarmMaxHair=FMath::Max(WarmMaxHair,float(Hair.Size()));
    auto At=[&](float Time){return Previous<Time&&T>=Time;};
    MoveIntent=FVector2D(0,T>=2&&T<8?1:0);
    bWalk=T>=2&&T<4;bJog=false;bSprintHeld=T>=6&&T<8;
    if(At(3.5f))Check(FMath::Abs(M->Velocity.Size2D()-Definition->WalkSpeed)<3,TEXT("walk speed matches stride"));
    if(At(5.5f))Check(FMath::Abs(M->Velocity.Size2D()-Definition->RunSpeed)<3,TEXT("run uses slowed sprint"));
    if(At(7.5f))Check(FMath::Abs(M->Velocity.Size2D()-GetSprintSpeed())<3,TEXT("sprint reaches tuned speed with rate-scaled stride"));
    if(At(7.5f))Check(WarmMaxHair>.001f && WarmMaxHair<=1.001f,TEXT("hair responds to motion with bounded tip flex"));
    if(At(8.5f))Dash(FInputActionValue(true));
    if(At(8.6f))Check(AnimationAction==TEXT("DashGround"),TEXT("ground dash starts"));
    if(At(8.65f))
    {
        Check(M->IsFalling()&&GetActorLocation().Z-WarmOrigin.Z>15.f,TEXT("ground dash is a real forward leap"));
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
            TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll direction QA"));
            M->SetMovementMode(MOVE_Walking);
            Controller->SetControlRotation(FRotator::ZeroRotator);
            WarmRollOrigin=GetActorLocation();WarmRollInverted=false;MoveIntent=RollDirections[I];
            Dodge(FInputActionValue(true));
            Check(AnimationAction==TEXT("Roll"),FString::Printf(TEXT("roll direction %d starts"),I));
            const uint32 Serial=ActionSerial;
            Dodge(FInputActionValue(true));Dash(FInputActionValue(true));RequestJump(FInputActionValue(true));
            Check(Serial==ActionSerial,FString::Printf(TEXT("roll direction %d cannot be interrupted"),I));
        }
        if(At(Start+1.35f))
        {
            const FVector Direction(RollDirections[I].Y,RollDirections[I].X,0);
            const FVector Travel=GetActorLocation()-WarmRollOrigin;
            Check(FVector::DotProduct(Travel,Direction)>100.f && FMath::Abs(FVector::DotProduct(Travel,Direction.RotateAngleAxis(90,FVector::UpVector)))<3.f,
                FString::Printf(TEXT("roll direction %d travels along its input including diagonals"),I));
            Check(WarmRollInverted && AnimationAction!=TEXT("Roll") && M->IsMovingOnGround(),FString::Printf(TEXT("roll direction %d rotates and recovers"),I));
        }
    }
    if(At(58.f))
    {
        TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll wall QA"));
        M->SetMovementMode(MOVE_Walking);WarmRollOrigin=GetActorLocation();
        WarmRollObstacle=GetWorld()->SpawnActor<AActor>();
        auto* Box=NewObject<UBoxComponent>(WarmRollObstacle);WarmRollObstacle->SetRootComponent(Box);
        WarmRollObstacle->AddInstanceComponent(Box);Box->SetBoxExtent(FVector(20,180,180));
        Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
        WarmRollObstacle->SetActorLocation(WarmRollOrigin+FVector(130,0,70));
        MoveIntent=FVector2D(0,1);Dodge(FInputActionValue(true));
    }
    if(At(59.4f))
    {
        const double Travel=GetActorLocation().X-WarmRollOrigin.X;
        Check(Travel>40 && Travel<110 && AnimationAction!=TEXT("Roll"),TEXT("roll capsule stops at wall and action recovers"));
        WarmRollObstacle->Destroy();WarmRollObstacle=nullptr;
    }
    if(At(60.f))
    {
        TravelTo(WarmOrigin+FVector(14890,0,-GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll ledge QA"));
        M->SetMovementMode(MOVE_Walking);MoveIntent=FVector2D(0,1);Dodge(FInputActionValue(true));
    }
    if(At(60.7f))Check(M->IsFalling() && M->Velocity.Z<-50.f,TEXT("roll leaving a ledge falls instead of hovering"));
    if(At(61.2f))
    {
        Check(AnimationAction!=TEXT("Roll"),TEXT("ledge roll opens into falling pose"));
        TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll QA complete"));
    }
    // Exercise the actual run/sprint transition at different gait phases.
    // The original all-directions tests entered only from rest and missed the stop.
    if(MovingRollReview)
    {
        for(int32 I=0;I<8;++I)
        {
            const float Start=64.f+I*4.f;
            const float Trigger=Start+1.f+(I%4)*.17f;
            const bool Sprinting=I%2==1;
            if(At(Start))
            {
                TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("moving roll QA"));
                M->SetMovementMode(MOVE_Walking);Controller->SetControlRotation(FRotator::ZeroRotator);
                WarmRollInverted=false;WarmRollElapsed=0.f;WarmRollEndSpeed=-1.f;WarmRollEndDistance=0.f;WarmRollWasAirborne=false;WarmRollGroundContacts=0;
                Stamina.SetCapacity(5);
            }
            if(T>=Start && T<Start+3.6f)
            {
                MoveIntent=FVector2D(0,1);bSprintHeld=Sprinting;
                if(I==4 && T>=Trigger+.15f)MoveIntent=FVector2D::ZeroVector;
                // Ask for a new heading before the feet recover. Input should
                // take effect at recovery, without waiting for the clip to end.
                if(I>=6 && T>=Trigger+.70f)MoveIntent=I==6?FVector2D(1,0):FVector2D(0,-1);
            }
            if(I==5 && At(Start+.9f))
            {
                WarmRollObstacle=GetWorld()->SpawnActor<AActor>();
                auto* Box=NewObject<UBoxComponent>(WarmRollObstacle);WarmRollObstacle->SetRootComponent(Box);
                WarmRollObstacle->AddInstanceComponent(Box);Box->SetBoxExtent(FVector(20,180,180));
                Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
                WarmRollObstacle->SetActorLocation(GetActorLocation()+FVector(350,0,70));
            }
            if(At(Trigger))
            {
                WarmRollOrigin=GetActorLocation();WarmRollEntrySpeed=M->Velocity.Size2D();
                WarmRollMinSpeed=WarmRollMinEntrySpeed=WarmRollEntrySpeed;
                Check(FMath::Abs(WarmRollEntrySpeed-(Sprinting?GetSprintSpeed():Definition->RunSpeed))<5.f,
                    FString::Printf(TEXT("moving roll %d enters from full gait speed"),I));
                Dodge(FInputActionValue(true));
                Check(AnimationAction==TEXT("Roll"),FString::Printf(TEXT("moving roll %d starts"),I));
                Check(ActionDuration>1.f && ActionDuration<1.1f && ActionSourceStartTime==0.f,
                    FString::Printf(TEXT("moving roll %d plays the full dive and tuck at a moderately faster rate"),I));
            }
            if(T>Trigger && T<Trigger+1.45f)
            {
                const float Speed=M->Velocity.Size2D();
                if(T<Trigger+.15f)WarmRollMinEntrySpeed=FMath::Min(WarmRollMinEntrySpeed,Speed);
                if(AnimationAction==TEXT("Roll")){WarmRollMinSpeed=FMath::Min(WarmRollMinSpeed,Speed);WarmRollElapsed=T-Trigger;}
                else if(WarmRollEndSpeed<0.f){WarmRollEndSpeed=Speed;WarmRollEndDistance=FVector::Dist2D(GetActorLocation(),WarmRollOrigin);}
                if(WarmRollWasAirborne && M->IsMovingOnGround())++WarmRollGroundContacts;
                WarmRollWasAirborne=M->IsFalling();
            }
            // Inspect the same authored extended-dive pose at the faster rate.
            if(At(Trigger+.22f/ActionPlayRate))
            {
                Check(M->IsFalling() && GetActorLocation().Z-WarmOrigin.Z>10.f,FString::Printf(TEXT("moving roll %d begins with a real airborne dive"),I));
                const FVector Hands=(GetMesh()->GetSocketLocation(TEXT("hand_L"))+GetMesh()->GetSocketLocation(TEXT("hand_R")))*.5;
                const FVector Head=GetMesh()->GetSocketLocation(TEXT("head"));
                const FVector Hips=GetMesh()->GetSocketLocation(TEXT("pelvis"));
                Check(FVector::DotProduct(Hands-Head,GetActorForwardVector())>8.f && FVector::DotProduct(Head-Hips,GetActorForwardVector())>20.f,
                    FString::Printf(TEXT("moving roll %d extends hands and torso before tucking"),I));
            }
            if(At(Trigger+.5f))Check(M->IsMovingOnGround() && AnimationAction==TEXT("Roll"),FString::Printf(TEXT("moving roll %d lands directly into the roll"),I));
            if(I>=6 && At(Trigger+.75f))
                Check(MovementLocked() && M->Velocity.X>100.f && FMath::Abs(M->Velocity.Y)<1.f,
                    FString::Printf(TEXT("steering case %d keeps the tumble heading until feet recover"),I));
            if(I>=6 && At(Trigger+.88f))
            {
                const FVector Heading=I==6?FVector::RightVector:-FVector::ForwardVector;
                Check(AnimationAction==TEXT("Roll") && !MovementLocked() && !M->GetRootMotionSource(TEXT("GroundRoll")).IsValid(),
                    FString::Printf(TEXT("steering case %d releases input and forced travel before the visual recovery ends"),I));
                Check(FVector::DotProduct(M->GetCurrentAcceleration(),Heading)>1000.f,
                    FString::Printf(TEXT("steering case %d immediately accelerates in the requested direction"),I));
                UE_LOG(LogTemp,Display,TEXT("ROLL STEER %d seconds=%.4f velocity=%s acceleration=%s locked=%d"),
                    I,ActionTime,*M->Velocity.ToCompactString(),*M->GetCurrentAcceleration().ToCompactString(),MovementLocked());
            }
            if(I>=6 && At(Trigger+1.05f))
            {
                const FVector Heading=I==6?FVector::RightVector:-FVector::ForwardVector;
                Check(FVector::DotProduct(M->Velocity.GetSafeNormal2D(),Heading)>.8f && FVector::DotProduct(M->Velocity,Heading)>100.f,
                    FString::Printf(TEXT("steering case %d changes actual travel direction during recovery"),I));
                UE_LOG(LogTemp,Display,TEXT("ROLL STEER EXIT %d velocity=%s yaw=%.2f"),I,*M->Velocity.ToCompactString(),GetActorRotation().Yaw);
            }
            if(I==5 && At(Trigger+.35f))WarmRollOrigin=GetActorLocation();
            if(I==5 && At(Trigger+.45f))
            {
                // An active override can report its intended speed against a wall;
                // actual capsule displacement is the collision authority.
                Check(AnimationAction==TEXT("Roll") && FVector::Dist2D(WarmRollOrigin,GetActorLocation())<1.f &&
                    GetActorLocation().X<WarmRollObstacle->GetActorLocation().X-40.f,
                    TEXT("wall blocks the moving roll before recovery"));
            }
            if(At(Trigger+1.45f))
            {
                Check(WarmRollMinEntrySpeed>=WarmRollEntrySpeed*.95f,FString::Printf(TEXT("moving roll %d keeps entry momentum"),I));
                Check(WarmRollInverted && AnimationAction!=TEXT("Roll") && M->IsMovingOnGround(),FString::Printf(TEXT("moving roll %d rotates and recovers"),I));
                Check(WarmRollGroundContacts==1,FString::Printf(TEXT("moving roll %d has one dive touchdown"),I));
                if(I<4)
                {
                    Check(WarmRollEndDistance>480.f && WarmRollEndDistance<(Sprinting?850.f:700.f),FString::Printf(TEXT("moving roll %d travels farther through dive and roll"),I));
                    Check(WarmRollMinSpeed>=WarmRollEntrySpeed*.95f,FString::Printf(TEXT("moving roll %d has no braking inside the roll"),I));
                    Check(WarmRollEndSpeed>=WarmRollEntrySpeed*.9f,FString::Printf(TEXT("moving roll %d carries speed into the next stride"),I));
                }
                if(I==4)Check(M->Velocity.Size2D()<5.f,TEXT("released moving roll comes to a stop"));
                if(I==5)
                {
                    Check(GetActorLocation().X<WarmRollObstacle->GetActorLocation().X-40.f && M->Velocity.Size2D()<5.f,TEXT("sprint roll remains blocked by a wall"));
                    WarmRollObstacle->Destroy();WarmRollObstacle=nullptr;
                }
                UE_LOG(LogTemp,Display,TEXT("ROLL TRANSITION %d entry=%.3f minimum_entry=%.3f minimum_roll=%.3f exit=%.3f seconds=%.4f distance=%.3f"),
                    I,WarmRollEntrySpeed,WarmRollMinEntrySpeed,WarmRollMinSpeed,WarmRollEndSpeed,WarmRollElapsed,WarmRollEndDistance);
            }
        }
    }
    if(RollChainReview)
    {
        for(int32 I=0;I<6;++I)
        {
            const float Start=97.f+I*5.f, Trigger=Start+1.f;
            const bool ExpectChain=I<3;
            const FVector2D Direction=I==1?FVector2D(1,0):I==2?FVector2D(0,-1):FVector2D(0,1);
            if(At(Start))
            {
                TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("roll chain QA"));
                M->SetMovementMode(MOVE_Walking);Controller->SetControlRotation(FRotator::ZeroRotator);
                WarmRollChainSerial=0;WarmRollChainCount=WarmRollChainTucks=WarmRollGroundContacts=0;
                WarmRollChainSecondTime=-1.f;WarmRollInverted=WarmRollWasAirborne=false;Stamina.SetCapacity(5);
            }
            if(T>=Start && T<Start+4.5f)
            {
                MoveIntent=T>=Trigger+.70f?Direction:FVector2D(0,1);bSprintHeld=I==1||I==2;
            }
            if(At(Trigger))Dodge(FInputActionValue(true));
            const float Repeat=I==2?.86f:I==3?.20f:.72f;
            if(At(Trigger+Repeat))
            {
                Dodge(FInputActionValue(true));
                if(I!=2)Check(RollBuffer>0.f,FString::Printf(TEXT("roll chain %d records a brief buffered press"),I));
            }
            if(I==4 && At(Trigger+.76f))SetMenuOpen(true);
            if(I==4 && At(Trigger+.80f))SetMenuOpen(false);
            if(I==5 && At(Trigger+.76f))TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),0,TEXT("cancel buffered roll QA"));
            if(T>=Trigger && T<Start+4.5f)
            {
                if(AnimationAction==TEXT("Roll") && ActionSerial!=WarmRollChainSerial)
                {
                    if(WarmRollInverted)++WarmRollChainTucks;
                    WarmRollInverted=false;WarmRollChainSerial=ActionSerial;++WarmRollChainCount;
                    if(WarmRollChainCount==2)
                    {
                        WarmRollChainSecondTime=T-Trigger;
                        Check(ActionTime<.04f && ActionPlayRate>1.f,FString::Printf(TEXT("roll chain %d restarts the same clip and source clock"),I));
                        UE_LOG(LogTemp,Display,TEXT("ROLL CHAIN %d second_start=%.4f speed=%.3f yaw=%.2f buffer=%.3f"),I,WarmRollChainSecondTime,M->Velocity.Size2D(),GetActorRotation().Yaw,RollBuffer);
                    }
                }
                // TravelTo settles onto its destination separately. Only
                // count support transitions belonging to an actual Roll.
                if(WarmRollWasAirborne && M->IsMovingOnGround() && AnimationAction==TEXT("Roll"))++WarmRollGroundContacts;
                WarmRollWasAirborne=AnimationAction==TEXT("Roll") && M->IsFalling();
            }
            if(ExpectChain && At(Trigger+.92f))
            {
                Check(WarmRollChainCount==2 && WarmRollChainSecondTime>.80f && WarmRollChainSecondTime<.90f,
                    FString::Printf(TEXT("roll chain %d starts again at recovery without the old cooldown"),I));
                const FVector Heading(Direction.Y,Direction.X,0);
                Check(FVector::DotProduct(GetActorForwardVector(),Heading)>.99f && FVector::DotProduct(M->Velocity,Heading)>300.f,
                    FString::Printf(TEXT("roll chain %d uses the latest direction and carries momentum"),I));
            }
            if(ExpectChain && At(Trigger+1.03f))
                Check(WarmRollChainCount==2 && AnimationAction==TEXT("Roll") && M->IsFalling(),
                    FString::Printf(TEXT("roll chain %d performs a fresh second dive"),I));
            if(At(Trigger+3.f))
            {
                Check(WarmRollChainCount==(ExpectChain?2:1),FString::Printf(TEXT("roll chain %d consumes once; early/menu/teleport presses do not leak"),I));
                Check(WarmRollChainTucks+int32(WarmRollInverted)==(ExpectChain?2:1),FString::Printf(TEXT("roll chain %d keeps one full tuck per roll"),I));
                Check(WarmRollGroundContacts==(ExpectChain?2:1),FString::Printf(TEXT("roll chain %d keeps one dive touchdown per roll"),I));
                Check(AnimationAction!=TEXT("Roll") && RollBuffer==0.f,FString::Printf(TEXT("roll chain %d recovers with no automatic extra roll"),I));
            }
        }
    }
    if(AirTurnReview)
    {
        // Real first/second jump inputs, then inspect the next movement tick:
        // LaunchCharacter queues velocity, so an immediate read cannot test it.
        const FVector2D Directions[]={FVector2D(1,0),FVector2D(0,-1),FVector2D(1,0),FVector2D(1,1),
            FVector2D(0,0),FVector2D(0,0),FVector2D(1,0),FVector2D(.4f,0),FVector2D(1,0),FVector2D(-1,0)};
        for(int32 I=0;I<UE_ARRAY_COUNT(Directions);++I)
        {
            const float Start=129.f+I*4.f, Second=Start+1.55f;
            const float CameraYaw=I==2?90.f:0.f;
            const bool Standing=I==5 || I==6, Sprinting=I==1 || I==3;
            const FVector Heading=FRotator(0,CameraYaw,0).RotateVector(FVector(Directions[I].Y,Directions[I].X,0)).GetSafeNormal();
            auto Label=[&](const TCHAR* What){return FString::Printf(TEXT("air turn %d %s"),I,What);};
            if(At(Start))
            {
                TravelTo(WarmOrigin-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),CameraYaw,TEXT("directional double jump QA"));
                M->SetMovementMode(MOVE_Walking);Stamina.SetCapacity(5);WarmInverted=false;
                Controller->SetControlRotation(FRotator(-12,CameraYaw,0));
            }
            if(T>=Start+.2f && T<Second) {MoveIntent=Standing?FVector2D::ZeroVector:FVector2D(0,1);bSprintHeld=Sprinting;}
            if(T>=Second && T<Start+3.f)
            {
                // Briefly release after launch to isolate the impulse from
                // ordinary air acceleration, then restore the player's input.
                MoveIntent=T<Second+.05f?FVector2D::ZeroVector:Directions[I];bSprintHeld=Sprinting;
            }
            if(At(Start+1.f))RequestJump(FInputActionValue(true));
            if(I==9 && At(Start+1.25f))Dash(FInputActionValue(true));
            if(At(Second))
            {
                Check(M->IsFalling()&&!bAirJumpUsed,Label(TEXT("enters from the first jump")));
                WarmAirVelocity=M->Velocity;WarmAirOrigin=GetActorLocation();WarmAirLaunchTime=T;
                MoveIntent=Directions[I];RequestJump(FInputActionValue(true));
                Check(AnimationAction==TEXT("DoubleJump")&&bAirJumpUsed,Label(TEXT("starts exactly one second jump")));
                if(!Heading.IsNearlyZero())Check(FVector::DotProduct(GetActorForwardVector(),Heading)>.999f,Label(TEXT("faces the requested flip heading immediately")));
                MoveIntent=FVector2D::ZeroVector;
                if(I==8)
                {
                    WarmRollObstacle=GetWorld()->SpawnActor<AActor>();
                    auto* Box=NewObject<UBoxComponent>(WarmRollObstacle);WarmRollObstacle->SetRootComponent(Box);WarmRollObstacle->AddInstanceComponent(Box);
                    Box->SetBoxExtent(FVector(300,20,350));Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
                    WarmRollObstacle->SetActorLocation(WarmAirOrigin+FVector(0,130,0));
                }
            }
            if(Previous==WarmAirLaunchTime && T>Second && T<Second+.05f)
            {
                const FVector Expected=Heading.IsNearlyZero()?FVector(WarmAirVelocity.X,WarmAirVelocity.Y,0):Heading*WarmAirVelocity.Size2D();
                Check(FVector::Dist2D(M->Velocity,Expected)<2.f,Label(TEXT("redirects horizontal momentum on the next physics tick without adding speed")));
                Check(M->Velocity.Z>620.f && M->Velocity.Z<=650.f && GetActorLocation().Z>WarmAirOrigin.Z,Label(TEXT("keeps the upward impulse")));
                Check(FMath::Abs(FRotator::NormalizeAxis(GetControlRotation().Yaw-CameraYaw))<.01f && FMath::Abs(GetControlRotation().Pitch+12.f)<.01f,
                    Label(TEXT("leaves camera yaw and pitch unchanged")));
                UE_LOG(LogTemp,Display,TEXT("AIR TURN %d before=%s after=%s expected_xy=%s yaw=%.2f"),I,*WarmAirVelocity.ToCompactString(),*M->Velocity.ToCompactString(),*Expected.ToCompactString(),GetActorRotation().Yaw);
            }
            if(At(Second+.12f))
            {
                const uint32 Serial=ActionSerial;const FRotator Rotation=GetActorRotation();
                MoveIntent=FVector2D(0,-1);RequestJump(FInputActionValue(true));
                Check(Serial==ActionSerial && GetActorRotation().Equals(Rotation,.01f),Label(TEXT("rejects a third jump and its direction change")));
                MoveIntent=Directions[I];
            }
            if(At(Second+.6f))
            {
                Check(WarmInverted,Label(TEXT("retains the full airborne flip")));
                Check(GetActorUpVector().Z>.999f,Label(TEXT("keeps the collision capsule upright")));
                if(I==8)Check(GetActorLocation().Y-WarmAirOrigin.Y>30.f && GetActorLocation().Y-WarmAirOrigin.Y<112.f,
                    Label(TEXT("sweeps into a wall without passing through it")));
                else if(!Heading.IsNearlyZero())Check(FVector::DotProduct(GetActorLocation()-WarmAirOrigin,Heading)>20.f,
                    Label(TEXT("travels in the requested direction")));
            }
            if(At(Start+3.5f))
            {
                Check(M->IsMovingOnGround()&&!bAirJumpUsed&&!bAirDashUsed,Label(TEXT("landing restores both air abilities")));
                if(WarmRollObstacle){WarmRollObstacle->Destroy();WarmRollObstacle=nullptr;}
            }
        }
    }
    const FVector Target=GetActorLocation()+FVector(0,0,8);
    FVector View=T<1?FVector(-350,0,65):T<2?FVector(350,0,65):FVector(70,350,80);
    float CameraScale=1.f;FParse::Value(FCommandLine::Get(),TEXT("warmcamerascale="),CameraScale);
    FString CameraView;FParse::Value(FCommandLine::Get(),TEXT("warmview="),CameraView);
    if(CameraView==TEXT("front"))View=FVector(350,0,65);
    else if(CameraView==TEXT("back"))View=FVector(-350,0,65);
    else if(CameraView==TEXT("side"))View=FVector(0,350,65);
    View*=FMath::Clamp(CameraScale,.5f,2.f);
    FollowCamera->SetWorldLocationAndRotation(Target+View,(-View).Rotation());
    const FQuat Pelvis=GetMesh()->GetSocketTransform(TEXT("pelvis"),RTS_Component).GetRotation();
    const FQuat Bind=Definition->Mesh->GetRefSkeleton().GetRefBonePose()[GetMesh()->GetBoneIndex(TEXT("pelvis"))].GetRotation();
    const float Up=(Pelvis*Bind.Inverse()).GetUpVector().Z;
    if(AnimationAction==TEXT("DoubleJump")&&Up<-.65f)WarmInverted=true;
    if(AnimationAction==TEXT("Roll")&&Up<-.65f)WarmRollInverted=true;
    const float Waist=GetMesh()->GetAnimInstance()->GetCurveValue(TEXT("shorts_Waist_shirt_clearance"));
    WarmMaxWaist=FMath::Max(WarmMaxWaist,Waist);
    WarmTelemetry+=FString::Printf(TEXT("%.4f,%s,%.3f,%.3f,%d,%d,%d,%.5f,%.5f\n"),T,*AnimationAction.ToString(),M->Velocity.Size2D(),GetActorLocation().Z-WarmOrigin.Z,M->IsFalling(),bAirJumpUsed,bAirDashUsed,Up,Waist);
    if(FParse::Param(FCommandLine::Get(),TEXT("warmfilm")))RecordFrame();
    else for(float Shot:{1.f,3.f,5.f,6.3f,6.65f,7.f,8.8f,10.65f,11.2f,16.9f,19.2f,21.8f,23.3f,25.7f,27.7f,29.7f,31.7f,33.7f,35.5f,37.5f,39.5f})if(At(Shot))
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("warm_%04d.png"),FMath::RoundToInt(Shot*100)),false,false);
    float End=AirTurnReview?169.f:RollChainReview?128.f:MovingRollReview?96.f:63.f;FParse::Value(FCommandLine::Get(),TEXT("warmqaseconds="),End);
    if(T>=End)
    {
        if(!MovingRollReview && !RollChainReview && !AirTurnReview && End>=41.f)Check(WarmInverted,TEXT("double jump visibly flips pelvis"));
        if(End>=8.f)Check(WarmMaxWaist>.25f,TEXT("waist corrective survives runtime graph"));
        FFileHelper::SaveStringToFile(WarmTelemetry,*(ReviewDirectory/TEXT("warm.csv")));
        FString Errors;for(const auto& Error:WarmErrors){if(!Errors.IsEmpty())Errors+=TEXT(",");Errors+=TEXT("\"")+Error+TEXT("\"");}
        const FString Result=FString::Printf(TEXT("{\"passed\":%s,\"errors\":[%s],\"max_waist_curve\":%.6f,\"max_hair_flex\":%.6f}\n"),WarmErrors.IsEmpty()?TEXT("true"):TEXT("false"),*Errors,WarmMaxWaist,WarmMaxHair);
        FFileHelper::SaveStringToFile(Result,*(ReviewDirectory/TEXT("result.json")));
        UE_LOG(LogTemp,Display,TEXT("WARM QA COMPLETE %s"),*Result);FPlatformMisc::RequestExit(false);
    }
}
