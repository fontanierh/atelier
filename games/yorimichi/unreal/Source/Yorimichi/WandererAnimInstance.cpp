#include "WandererAnimInstance.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "SailboatComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Animation/AnimNodeSpaceConversions.h"
#include "SkateComponent.h"
#include "AnimNodes/AnimNode_SkatePose.h"
#include "GroundContactNode.h"
#include "ZeppelinService.h"
#include "CairoCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "SailboatStanceNode.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNode_SequencePlayer.h"
#include "Animation/AnimSequence.h"
#include "AnimNodes/AnimNode_BlendSpacePlayer.h"
#include "AnimNodes/AnimNode_TwoWayBlend.h"
#include "AnimNodes/AnimNode_LayeredBoneBlend.h"
#include "WandererSword.h"
#include "GameFramework/CharacterMovementComponent.h"

void FWandererStateNode::Initialize_AnyThread(const FAnimationInitializeContext& C)
{
    FAnimNode_Base::Initialize_AnyThread(C); Ground.Initialize(C); Action.Initialize(C);
    PreviousSerial = Serial;
    LastPose.Reset(); PreviousPose.Reset(); TransitionPose.Reset(); LastCurve.Empty(); TransitionCurve.Empty();
}
void FWandererStateNode::CacheBones_AnyThread(const FAnimationCacheBonesContext& C)
{
    Ground.CacheBones(C); Action.CacheBones(C);
    LastPose.Reset(); PreviousPose.Reset(); TransitionPose.Reset(); LastCurve.Empty(); TransitionCurve.Empty();
}
void FWandererStateNode::Update_AnyThread(const FAnimationUpdateContext& C)
{
    DeltaSeconds = C.GetDeltaTime();
    if (PreviousSerial != Serial) { bCaptureTransition = true; PreviousSerial = Serial; }
    (bAction ? Action : Ground).Update(C);
    if(bAction && bAdvanceGround)Ground.Update(C);
}
void FWandererStateNode::Evaluate_AnyThread(FPoseContext& Output)
{
    (bAction ? Action : Ground).Evaluate(Output);
    const int32 Count = Output.Pose.GetNumBones();
    if(bAction && RecoveryAlpha>0.f)
    {
        FPoseContext MovingPose(Output);Ground.Evaluate(MovingPose);
        for(int32 I=0;I<Count;++I)
        {
            const FCompactPoseBoneIndex Bone(I);
            Output.Pose[Bone].BlendWith(MovingPose.Pose[Bone],RecoveryAlpha);
        }
        Output.Curve.LerpTo(MovingPose.Curve,RecoveryAlpha);
    }
    if (bCaptureTransition)
    {
        bCaptureTransition = false; BlendTime = 0.f;
        TransitionPose = LastPose;
        TransitionCurve.CopyFrom(LastCurve);
        TranslationVelocity.SetNumZeroed(Count); RotationVelocity.SetNumZeroed(Count);
        if (LastPose.Num() == Count && PreviousPose.Num() == Count && PreviousDelta > SMALL_NUMBER)
            for (int32 I = 0; I < Count; ++I)
            {
                TranslationVelocity[I] = ((LastPose[I].GetTranslation()-PreviousPose[I].GetTranslation())/PreviousDelta).GetClampedToMaxSize(1200.f);
                FQuat Delta = LastPose[I].GetRotation()*PreviousPose[I].GetRotation().Inverse();
                if (Delta.W < 0) Delta = Delta*(-1.f);
                FVector Axis; double Angle; Delta.ToAxisAndAngle(Axis,Angle);
                RotationVelocity[I] = (Axis*(Angle/PreviousDelta)).GetClampedToMaxSize(14.f);
            }
    }
    if (TransitionPose.Num() == Count && BlendTime < BlendDuration)
    {
        const float U = FMath::Clamp(BlendTime/FMath::Max(BlendDuration,.001f),0.f,1.f);
        // Smoothstep has zero first/second derivatives at both endpoints. The
        // outgoing pose extrapolates its measured velocity while its weight fades.
        const float Alpha = U*U*U*(10.f+U*(-15.f+6.f*U));
        for (int32 I = 0; I < Count; ++I)
        {
            const FTransform& From = TransitionPose[I];
            FTransform& To = Output.Pose[FCompactPoseBoneIndex(I)];
            const FVector Spin = RotationVelocity[I]*BlendTime;
            const double Angle = Spin.Length();
            const FQuat Predicted = (Angle > SMALL_NUMBER ? FQuat(Spin/Angle,Angle) : FQuat::Identity)*From.GetRotation();
            To.SetTranslation(FMath::Lerp(From.GetTranslation()+TranslationVelocity[I]*BlendTime,To.GetTranslation(),Alpha));
            To.SetRotation(FQuat::Slerp(Predicted,To.GetRotation(),Alpha).GetNormalized());
            To.SetScale3D(FMath::Lerp(From.GetScale3D(),To.GetScale3D(),Alpha));
        }
        Output.Curve.LerpTo(TransitionCurve,1.f-Alpha);
        BlendTime += DeltaSeconds;
    }
    else TransitionPose.Reset();
    Swap(PreviousPose,LastPose); LastPose.SetNumUninitialized(Count);
    for (int32 I = 0; I < Count; ++I) LastPose[I] = Output.Pose[FCompactPoseBoneIndex(I)];
    LastCurve.CopyFrom(Output.Curve);
    PreviousDelta = DeltaSeconds;
}

struct FWandererAnimProxy final : public FAnimInstanceProxy
{
    FAnimNode_BlendSpacePlayer_Standalone Moving, Crouching;
    FAnimNode_TwoWayBlend Ground;
    FAnimNode_SequencePlayer_Standalone Action;
    FWandererStateNode State;
    // Armed: the right arm comes from the armed locomotion (the sword swinging in step with the stride) on the ground,
    // and holds the guard's carry pose over anything else that is not a sword clip (jumps, falls, dashes, crouching).
    FAnimNode_SequencePlayer_Standalone Carry;
    FAnimNode_BlendSpacePlayer_Standalone ArmedMoving, ArmedCrouching;
    FAnimNode_TwoWayBlend ArmedGround, CarryPose;
    FAnimNode_LayeredBoneBlend CarryLayer;
    FAnimNode_ConvertLocalToComponentSpace ToComponent;
    FGroundContactNode Feet;
    FSailboatStanceNode Stance;
    FAnimNode_ConvertComponentToLocalSpace ToLocal;
    FAnimNode_SkatePose SkatePose;
    float Speed = 0.f, CrouchTarget = 0.f, CrouchWeight = 0.f, StanceWeight = 0.f, ArmedTarget = 0.f, ArmedWeight = 0.f;
    float AuthoredTopSpeed = 300.f, AuthoredCrouchSpeed = 50.f;
    uint32 AppliedSerial = MAX_uint32;
    FName AppliedClip;
    bool bArmedCrouch = false;

    explicit FWandererAnimProxy(UAnimInstance* Owner) : FAnimInstanceProxy(Owner)
    {
        Ground.A.SetLinkNode(&Moving); Ground.B.SetLinkNode(&Crouching);
        State.Ground.SetLinkNode(&Ground); State.Action.SetLinkNode(&Action);
        CarryLayer.BasePose.SetLinkNode(&State);
        ArmedGround.A.SetLinkNode(&ArmedMoving); ArmedGround.B.SetLinkNode(&ArmedCrouching); ArmedGround.Alpha = 0.f;
        CarryPose.A.SetLinkNode(&Carry); CarryPose.B.SetLinkNode(&ArmedGround); CarryPose.Alpha = 0.f;
        CarryLayer.BlendPoses.SetNum(1); CarryLayer.BlendPoses[0].SetLinkNode(&CarryPose);
        CarryLayer.LayerSetup.SetNum(1); CarryLayer.LayerSetup[0].BranchFilters.Add(FBranchFilter{TEXT("clavicle_R"), 0});
        CarryLayer.BlendWeights.SetNum(1); CarryLayer.BlendWeights[0] = 0.f;
        CarryLayer.bMeshSpaceRotationBlend = false; CarryLayer.bBlendRootMotionBasedOnRootBone = false;
        ToComponent.LocalPose.SetLinkNode(&CarryLayer);
        Feet.ComponentPose.SetLinkNode(&ToComponent);
        Feet.Alpha=0.f;
        Stance.ComponentPose.SetLinkNode(&Feet);
        Stance.Alpha = 0.f;
        ToLocal.ComponentPose.SetLinkNode(&Stance);
        SkatePose.BasePose.SetLinkNode(&ToLocal);
        Moving.SetGroupName(TEXT("Stride")); Crouching.SetGroupName(TEXT("Stride"));
        Moving.SetGroupMethod(EAnimSyncMethod::SyncGroup); Crouching.SetGroupMethod(EAnimSyncMethod::SyncGroup);
        // Same samples and lengths as Moving, so the sword arm swings on the body's stride phase.
        ArmedMoving.SetGroupName(TEXT("Stride")); ArmedMoving.SetGroupMethod(EAnimSyncMethod::SyncGroup);
        ArmedCrouching.SetGroupName(TEXT("Stride")); ArmedCrouching.SetGroupMethod(EAnimSyncMethod::SyncGroup);
    }
    virtual FAnimNode_Base* GetCustomRootNode() override { return &SkatePose; }
    virtual void GetCustomNodes(TArray<FAnimNode_Base*>& Nodes) override
    { Nodes = { &Moving, &Crouching, &Ground, &Action, &State, &Carry, &ArmedMoving, &ArmedCrouching, &ArmedGround, &CarryPose, &CarryLayer, &ToComponent, &Feet, &Stance, &ToLocal, &SkatePose }; }
    virtual void Initialize(UAnimInstance* Instance) override
    {
        if (const AWandererCharacter* Pawn = Cast<AWandererCharacter>(Instance->TryGetPawnOwner()))
            if (UWandererDefinition* D = Pawn->GetDefinition())
            {
                Moving.SetBlendSpace(D->Locomotion); Crouching.SetBlendSpace(D->Crouching);
                Action.SetSequence(D->FindAction(TEXT("Idle")));
                // The one-handed hold in front of the belly (game-r16); older content holds the guard's arm.
                UAnimSequence* Hold = D->FindAction(TEXT("SwordCarry")); if (!Hold) Hold = D->FindAction(TEXT("SwordIdle"));
                if (Hold) { Carry.SetSequence(Hold); Carry.SetLoopAnimation(true); Carry.SetPlayRate(1.f); }
                ArmedMoving.SetBlendSpace(D->ArmedLocomotion); ArmedCrouching.SetBlendSpace(D->ArmedCrouching); bArmedCrouch = D->ArmedCrouching != nullptr;
            }
        FAnimInstanceProxy::Initialize(Instance);
    }
    virtual void PreUpdate(UAnimInstance* Instance, float Dt) override
    {
        FAnimInstanceProxy::PreUpdate(Instance, Dt);
        const AWandererCharacter* Pawn = Cast<AWandererCharacter>(Instance->TryGetPawnOwner());
        if (!Pawn || !Pawn->GetDefinition()) return;
        Speed = Pawn->IsZeppelinPassenger()?Pawn->GetZeppelin()->GetWalkSpeed():Pawn->GetVelocity().Size2D();
        // Beyond the fastest authored sample the stride cannot grow any more, so only then does the cycle speed up.
        AuthoredTopSpeed = FMath::Max(1.f,FMath::Max(Pawn->GetDefinition()->RunSpeed,Pawn->GetDefinition()->SprintSpeed));
        AuthoredCrouchSpeed = FMath::Max(1.f,Pawn->GetDefinition()->CrouchSpeed);
        CrouchTarget = Pawn->bIsCrouched ? 1.f : 0.f;
        const USailboatComponent* SailboatC = Pawn->GetSailboat();
        const bool bSailing = SailboatC && SailboatC->IsEquipped();
        const USkateComponent* Ride = Pawn->GetSkate();
        const bool bRiding = Ride && Ride->IsRiding();
        State.bAction = bSailing || !Pawn->GetAnimationAction().IsNone();
        State.Serial = Pawn->GetActionSerial()+(SailboatC ? SailboatC->GetSerial()*7919 : 0)+(Ride ? Ride->GetSerial()*104729 : 0);
        State.BlendDuration = bSailing ? .2f : Pawn->GetActionBlendTime();
        // Continue the gait clock during a moving roll. Once the feet recover,
        // blend into that live stride instead of translating a planted idle pose.
        const bool MovingRoll=Pawn->GetAnimationAction()==TEXT("Roll") && Pawn->HasMovementIntent() && Speed>80.f;
        // Also update after input is released, so speed smoothing settles to
        // Idle before Roll ends instead of briefly resurrecting the entry gait.
        State.bAdvanceGround=Pawn->GetAnimationAction()==TEXT("Roll");
        // Source-time markers keep gait recovery aligned when the roll speeds
        // up. Finish blending shortly after steering returns at source .94.
        const float Recovery=MovingRoll?FMath::Clamp((Pawn->GetActionSourceTime()-.85f)/.15f,0.f,1.f):0.f;
        State.RecoveryAlpha=Recovery*Recovery*(3.f-2.f*Recovery);
        const bool Grounded=Pawn->IsA<ACairoCharacter>() && !bSailing &&
            Pawn->GetCharacterMovement()->IsMovingOnGround() && Pawn->GetAnimationAction()!=TEXT("Roll");
        Feet.Alpha=Grounded?1.f:0.f;
        Feet.DeltaSeconds=Dt;
        Feet.RestAnkle=Pawn->GetDefinition()->RestAnkleHeights;
        Feet.Sole=Pawn->GetDefinition()->SoleHeight;
        if(!Grounded)Feet.Reset();
        else
        {
            const FTransform& MeshTransform=Pawn->GetMesh()->GetComponentTransform();
            Feet.Forward=MeshTransform.InverseTransformVectorNoScale(Pawn->GetActorForwardVector());
            FCollisionQueryParams Query(SCENE_QUERY_STAT(CharacterGroundContact),false,Pawn);
            const double Base=Pawn->GetActorLocation().Z-Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
            for(int32 Side=0;Side<2;++Side)
            {
                FVector P=Pawn->GetMesh()->GetBoneLocation(Side?TEXT("foot_R"):TEXT("foot_L"));
                P.Z=Base+45.;FHitResult Hit;
                Feet.Valid[Side]=Pawn->GetWorld()->LineTraceSingleByChannel(Hit,P,P-FVector(0,0,95),ECC_Visibility,Query) &&
                    Pawn->GetCharacterMovement()->IsWalkable(Hit);
                if(Feet.Valid[Side])
                {
                    Feet.Point[Side]=MeshTransform.InverseTransformPosition(Hit.ImpactPoint);
                    Feet.Normal[Side]=MeshTransform.InverseTransformVectorNoScale(Hit.ImpactNormal).GetSafeNormal();
                }
            }
        }
        // Sailboat seating is solved in mesh space from the animated hull and tiller.
        StanceWeight = bSailing ? FMath::FInterpConstantTo(StanceWeight,1.f,Dt,5.f) : 0.f;
        Stance.Alpha = StanceWeight;
        if (bSailing)
        {
            const FTransform& MeshTransform = Pawn->GetMesh()->GetComponentTransform();
            auto Point=[&](FVector P){return MeshTransform.InverseTransformPosition(SailboatC->PosePoint(P));};
            const FVector HullRight=(SailboatC->PosePoint(FVector(0,1,0))-SailboatC->PosePoint(FVector::ZeroVector)).GetSafeNormal();
            const float GripSide=FVector::DotProduct(SailboatC->HandPoint(1)-SailboatC->PosePoint(FVector::ZeroVector),HullRight);
            // Slide naturally along the wide thwart to keep the moving tiller within the child's reach.
            const float SeatShift=FMath::Clamp((GripSide-22.f)*.65f,-18.f,22.f);
            Stance.GripAxis=MeshTransform.InverseTransformVectorNoScale(SailboatC->TillerDirection()).GetSafeNormal();
            Stance.GripUp=MeshTransform.InverseTransformVectorNoScale(SailboatC->TillerUp()).GetSafeNormal();
            Stance.GripForward=FVector::CrossProduct(Stance.GripUp,Stance.GripAxis).GetSafeNormal();
            Stance.PelvisTarget=Point(FVector(-115,SeatShift,53));
            for(int32 Side=0;Side<2;++Side)
            {
                const float S=Side?1.f:-1.f;
                // The free hand rests on the aft thwart, rather than floating in front of the torso.
                Stance.HandTarget[Side]=Side?MeshTransform.InverseTransformPosition(SailboatC->HandPoint(Side)):Point(FVector(-112,-27+SeatShift,53));
                Stance.ElbowPole[Side]=Point(FVector(-120,S*42+SeatShift,70));
                // 29cm thigh + 26cm shin: keep the ankle within reach and above the 10cm cockpit floor.
                Stance.FootTarget[Side]=Point(FVector(-88,S*18+SeatShift,21.5));
                Stance.KneePole[Side]=Point(FVector(-48,S*21+SeatShift,49));
            }
        }
        if (State.bAction && AppliedSerial != State.Serial)
        {
            if (UAnimSequence* Clip = bSailing ? SailboatC->GetSequence() : Pawn->GetDefinition()->FindAction(Pawn->GetAnimationClip()))
            {
                Action.SetSequence(Clip); Action.SetAccumulatedTime(bSailing?0.f:Pawn->GetActionSourceStartTime());
                Action.SetLoopAnimation(bSailing || Pawn->DoesActionLoop());
            }
            AppliedClip = bSailing || bRiding ? NAME_None : Pawn->GetAnimationClip();
        }
        // The sword drawn or put away in the middle of an action swaps its armed copy in place, at the same time.
        else if (State.bAction && !bSailing && !bRiding && Pawn->GetAnimationClip() != AppliedClip)
        {
            AppliedClip = Pawn->GetAnimationClip();
            if (UAnimSequence* Clip = Pawn->GetDefinition()->FindAction(AppliedClip))
            { const float Time = Action.GetAccumulatedTime(); Action.SetSequence(Clip); Action.SetAccumulatedTime(Time); }
        }
        Action.SetPlayRate(bRiding ? 0.f : bSailing ? 1.f : Pawn->GetActionPlayRate());
        CarryLayer.BlendWeights[0] = (!bSailing && !bRiding && Pawn->GetSword() && !Pawn->IsZeppelinPassenger()) ? Pawn->GetSword()->CarryWeight() : 0.f;
        ArmedTarget = (!State.bAction && Pawn->GetDefinition()->ArmedLocomotion) ? 1.f : 0.f;
        AppliedSerial = State.Serial;
    }
    virtual void Update(float Dt) override
    {
        CrouchWeight = FMath::FInterpConstantTo(CrouchWeight, CrouchTarget, Dt, 7.f);
        Ground.Alpha = CrouchWeight;
        // Grounded locomotion and crouching play their armed copies' right arm; anything else holds the carry pose.
        ArmedWeight = FMath::FInterpConstantTo(ArmedWeight, ArmedTarget, Dt, 6.f);
        ArmedGround.Alpha = CrouchWeight;
        CarryPose.Alpha = ArmedWeight * (bArmedCrouch ? 1.f : 1.f - CrouchWeight);
        // ScaleAnimation also accelerates out-of-range blend inputs. Clamp the
        // sample selection so our explicit rate applies extra speed only once.
        Moving.SetPosition(FVector(FMath::Min(Speed,AuthoredTopSpeed), 0, 0));
        Crouching.SetPosition(FVector(Speed, 0, 0));
        Moving.SetPlayRate(FMath::Max(1.f, Speed / AuthoredTopSpeed));
        ArmedMoving.SetPosition(FVector(FMath::Min(Speed,AuthoredTopSpeed), 0, 0));
        ArmedMoving.SetPlayRate(FMath::Max(1.f, Speed / AuthoredTopSpeed));
        ArmedCrouching.SetPosition(FVector(Speed, 0, 0));
        ArmedCrouching.SetPlayRate(FMath::Max(1.f, Speed / AuthoredCrouchSpeed));
        Crouching.SetPlayRate(FMath::Max(1.f, Speed / AuthoredCrouchSpeed));
    }
};

// Sword clips carry their captured travel and turning on the root bone; library clips keep an identity root.
UWandererAnimInstance::UWandererAnimInstance() { RootMotionMode = ERootMotionMode::RootMotionFromEverything; }
FSkatePoseDebugState UWandererAnimInstance::GetSkatePoseDebugState() const
{
    const FWandererAnimProxy& Proxy = GetProxyOnGameThread<FWandererAnimProxy>();
    FSkatePoseDebugState State = Proxy.SkatePose.GetDebugState();
    State.bNativeGraphRoot = const_cast<FWandererAnimProxy&>(Proxy).GetRootNode() == &Proxy.SkatePose;
    State.bBasePoseLinked = const_cast<FAnimNode_SkatePose&>(Proxy.SkatePose).BasePose.GetLinkNode() == &Proxy.ToLocal;
    return State;
}
FAnimInstanceProxy* UWandererAnimInstance::CreateAnimInstanceProxy() { return new FWandererAnimProxy(this); }
void UWandererAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete static_cast<FWandererAnimProxy*>(Proxy); }
