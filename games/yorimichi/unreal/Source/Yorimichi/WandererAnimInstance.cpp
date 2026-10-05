#include "WandererAnimInstance.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "SailboatComponent.h"
#include "BikeComponent.h"
#include "BikeGripNode.h"
#include "Components/SkeletalMeshComponent.h"
#include "Animation/AnimNodeSpaceConversions.h"
#include "SkateComponent.h"
#include "AnimNode_SkateRider.h"
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
#include "BoneControllers/AnimNode_TwoBoneIK.h"
#include "BoneControllers/AnimNode_ModifyBone.h"
#include "WandererSword.h"
#include "BotwMoveSet.h"
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
    // A move set's raised shield: the guard's left arm over locomotion and the lock-on strafe. Without the shield the
    // sword is raised instead, both arms from its guard pose (one player per arm layer, each evaluated once).
    FAnimNode_SequencePlayer_Standalone GuardPose, SwordGuardRight, SwordGuardLeft;
    FAnimNode_TwoWayBlend RightArm, LeftArm;
    // Without the shield the off hand is free: during sword work its arm swings with the locomotion (its own player, in
    // step with the stride) instead of holding the shield pose the BOTW clips give it.
    FAnimNode_BlendSpacePlayer_Standalone FreeArm;
    FAnimNode_TwoWayBlend LeftHand;
    FAnimNode_LayeredBoneBlend CarryLayer;
    // Gliding on a fitted body, the hands' fingers closed into the sword guard's fists round the paraglider's handles.
    FAnimNode_SequencePlayer_Standalone Fist;
    FAnimNode_LayeredBoneBlend FistLayer;
    FAnimNode_ConvertLocalToComponentSpace ToComponent;
    // A two-handed hold on a sword shorter than the clip's own (Cairo's bokken clips on Link's sword): the off hand is put
    // on the handle beside the sword hand, its elbow bending as the clip has it.
    FAnimNode_TwoBoneIK GripIK;
    // Gliding, each wrist on its grip on the paraglider's handle (UBotwMoveSet::GlideHandLocation), each elbow toward its
    // place on the neutral glide; then each fist turned round its handle (UBotwMoveSet::GlideHandRotation).
    FAnimNode_TwoBoneIK GlideIK[2];
    FAnimNode_ModifyBone GlideTurn[2];
    // A hit's recoil (UBotwMoveSet::FlinchRotation): the spine, chest, neck and head each turned a little further,
    // added in component space, the bones above following.
    FAnimNode_ModifyBone Flinch[4];
    FGroundContactNode Feet;
    FSailboatStanceNode Stance;
    // On the bike: the gripping hands follow bars the player steers past the clip's own steering.
    FBikeGripNode Grip;
    FAnimNode_ConvertComponentToLocalSpace ToLocal;
    float Speed = 0.f, CrouchTarget = 0.f, CrouchWeight = 0.f, StanceWeight = 0.f, ArmedTarget = 0.f, ArmedWeight = 0.f;
    float AuthoredTopSpeed = 300.f, AuthoredCrouchSpeed = 50.f;
    uint32 AppliedSerial = MAX_uint32;
    FName AppliedClip;
    // The skate pose over everything above, with the switches between them inertialized.
    FAnimNode_SkateRider Skate;
    bool bArmedCrouch = false;

    explicit FWandererAnimProxy(UAnimInstance* Owner) : FAnimInstanceProxy(Owner)
    {
        Ground.A.SetLinkNode(&Moving); Ground.B.SetLinkNode(&Crouching);
        State.Ground.SetLinkNode(&Ground); State.Action.SetLinkNode(&Action);
        CarryLayer.BasePose.SetLinkNode(&State);
        ArmedGround.A.SetLinkNode(&ArmedMoving); ArmedGround.B.SetLinkNode(&ArmedCrouching); ArmedGround.Alpha = 0.f;
        CarryPose.A.SetLinkNode(&Carry); CarryPose.B.SetLinkNode(&ArmedGround); CarryPose.Alpha = 0.f;
        RightArm.A.SetLinkNode(&CarryPose); RightArm.B.SetLinkNode(&SwordGuardRight); RightArm.Alpha = 0.f;
        LeftHand.A.SetLinkNode(&FreeArm); LeftHand.B.SetLinkNode(&GuardPose); LeftHand.Alpha = 1.f;
        LeftArm.A.SetLinkNode(&LeftHand); LeftArm.B.SetLinkNode(&SwordGuardLeft); LeftArm.Alpha = 0.f;
        CarryLayer.BlendPoses.SetNum(2); CarryLayer.BlendPoses[0].SetLinkNode(&RightArm); CarryLayer.BlendPoses[1].SetLinkNode(&LeftArm);
        CarryLayer.LayerSetup.SetNum(2);
        CarryLayer.LayerSetup[0].BranchFilters.Add(FBranchFilter{TEXT("clavicle_R"), 0});
        CarryLayer.LayerSetup[1].BranchFilters.Add(FBranchFilter{TEXT("clavicle_L"), 0});
        CarryLayer.BlendWeights.SetNum(2); CarryLayer.BlendWeights[0] = CarryLayer.BlendWeights[1] = 0.f;
        CarryLayer.bMeshSpaceRotationBlend = false; CarryLayer.bBlendRootMotionBasedOnRootBone = false;
        FistLayer.BasePose.SetLinkNode(&CarryLayer);
        FistLayer.BlendPoses.SetNum(1); FistLayer.BlendPoses[0].SetLinkNode(&Fist);
        FistLayer.LayerSetup.SetNum(1);
        for (const TCHAR* Side : { TEXT("_R"), TEXT("_L") })
            for (const TCHAR* Digit : { TEXT("thumb"), TEXT("finger_0"), TEXT("finger_1"), TEXT("finger_2"), TEXT("finger_3") })
                FistLayer.LayerSetup[0].BranchFilters.Add(FBranchFilter{FName(*(FString(Digit) + Side)), 0});
        FistLayer.BlendWeights.SetNum(1); FistLayer.BlendWeights[0] = 0.f;
        FistLayer.bMeshSpaceRotationBlend = false; FistLayer.bBlendRootMotionBasedOnRootBone = false;
        ToComponent.LocalPose.SetLinkNode(&FistLayer);
        GripIK.ComponentPose.SetLinkNode(&ToComponent);
        GripIK.EffectorLocationSpace = BCS_BoneSpace; GripIK.JointTargetLocationSpace = BCS_BoneSpace;
        GripIK.EffectorLocation = GripIK.JointTargetLocation = FVector::ZeroVector;
        GripIK.bAllowStretching = false; GripIK.bTakeRotationFromEffectorSpace = false; GripIK.bMaintainEffectorRelRot = false;
        GripIK.Alpha = 0.f;
        GlideIK[0].ComponentPose.SetLinkNode(&GripIK);
        GlideIK[1].ComponentPose.SetLinkNode(&GlideIK[0]);
        for (FAnimNode_TwoBoneIK& IK : GlideIK)
        {
            IK.EffectorLocationSpace = BCS_ComponentSpace; IK.JointTargetLocationSpace = BCS_ComponentSpace;
            IK.EffectorLocation = IK.JointTargetLocation = FVector::ZeroVector;
            IK.bAllowStretching = false; IK.bTakeRotationFromEffectorSpace = false; IK.bMaintainEffectorRelRot = false;
            IK.Alpha = 0.f;
        }
        GlideTurn[0].ComponentPose.SetLinkNode(&GlideIK[1]);
        GlideTurn[1].ComponentPose.SetLinkNode(&GlideTurn[0]);
        for (FAnimNode_ModifyBone& Turn : GlideTurn)
        {
            Turn.RotationMode = BMM_Replace; Turn.RotationSpace = BCS_ComponentSpace;
            Turn.TranslationMode = BMM_Ignore; Turn.ScaleMode = BMM_Ignore;
            Turn.Alpha = 0.f;
        }
        for (int32 I = 0; I < 4; ++I)
        {
            Flinch[I].ComponentPose.SetLinkNode(I ? static_cast<FAnimNode_Base*>(&Flinch[I - 1]) : &GlideTurn[1]);
            Flinch[I].RotationMode = BMM_Additive; Flinch[I].RotationSpace = BCS_ComponentSpace;
            Flinch[I].TranslationMode = BMM_Ignore; Flinch[I].ScaleMode = BMM_Ignore;
            Flinch[I].Alpha = 0.f;
        }
        Feet.ComponentPose.SetLinkNode(&Flinch[3]);
        Feet.Alpha=0.f;
        Stance.ComponentPose.SetLinkNode(&Feet);
        Stance.Alpha = 0.f;
        Grip.ComponentPose.SetLinkNode(&Stance);
        Grip.Alpha = 0.f;
        ToLocal.ComponentPose.SetLinkNode(&Grip);
        Skate.OnFoot.SetLinkNode(&ToLocal);
        Moving.SetGroupName(TEXT("Stride")); Crouching.SetGroupName(TEXT("Stride"));
        Moving.SetGroupMethod(EAnimSyncMethod::SyncGroup); Crouching.SetGroupMethod(EAnimSyncMethod::SyncGroup);
        // Same samples and lengths as Moving, so the sword arm swings on the body's stride phase.
        ArmedMoving.SetGroupName(TEXT("Stride")); ArmedMoving.SetGroupMethod(EAnimSyncMethod::SyncGroup);
        ArmedCrouching.SetGroupName(TEXT("Stride")); ArmedCrouching.SetGroupMethod(EAnimSyncMethod::SyncGroup);
        FreeArm.SetGroupName(TEXT("Stride")); FreeArm.SetGroupMethod(EAnimSyncMethod::SyncGroup);
    }
    virtual FAnimNode_Base* GetCustomRootNode() override { return Skate.GetRoot(); }
    virtual void GetCustomNodes(TArray<FAnimNode_Base*>& Nodes) override
    { Nodes = { &Moving, &Crouching, &Ground, &Action, &State, &Carry, &ArmedMoving, &ArmedCrouching, &ArmedGround, &CarryPose, &GuardPose, &SwordGuardRight, &SwordGuardLeft, &RightArm, &LeftArm, &FreeArm, &LeftHand, &CarryLayer, &Fist, &FistLayer, &ToComponent, &GripIK, &GlideIK[0], &GlideIK[1], &GlideTurn[0], &GlideTurn[1], &Flinch[0], &Flinch[1], &Flinch[2], &Flinch[3], &Feet, &Stance, &Grip, &ToLocal }; Skate.GetNodes(Nodes); }
    virtual void Initialize(UAnimInstance* Instance) override
    {
        if (const AWandererCharacter* Pawn = Cast<AWandererCharacter>(Instance->TryGetPawnOwner()))
            if (UWandererDefinition* D = Pawn->GetDefinition())
            {
                Moving.SetBlendSpace(D->Locomotion); Crouching.SetBlendSpace(D->Crouching); FreeArm.SetBlendSpace(D->Locomotion);
                Action.SetSequence(D->FindAction(TEXT("Idle")));
                // The one-handed hold in front of the belly (game-r16); older content holds the guard's arm.
                UAnimSequence* Hold = D->FindAction(TEXT("SwordCarry")); if (!Hold) Hold = D->FindAction(TEXT("SwordIdle"));
                if (Hold) { Carry.SetSequence(Hold); Carry.SetLoopAnimation(true); Carry.SetPlayRate(1.f); }
                ArmedMoving.SetBlendSpace(D->ArmedLocomotion); ArmedCrouching.SetBlendSpace(D->ArmedCrouching); bArmedCrouch = D->ArmedCrouching != nullptr;
                if (UAnimSequence* Guard = D->FindAction(TEXT("GuardCarry"))) { GuardPose.SetSequence(Guard); GuardPose.SetLoopAnimation(true); GuardPose.SetPlayRate(1.f); }
                if (UAnimSequence* Guard = D->FindAction(TEXT("SwordGuardCarry")))
                    for (FAnimNode_SequencePlayer_Standalone* Arm : { &SwordGuardRight, &SwordGuardLeft, &Fist }) { Arm->SetSequence(Guard); Arm->SetLoopAnimation(true); Arm->SetPlayRate(1.f); }
                // The layers' branch bones by the skate contract's names (a character's own clavicles).
                CarryLayer.LayerSetup[0].BranchFilters[0].BoneName = Pawn->GetSkateBone(TEXT("clavicle_R"));
                CarryLayer.LayerSetup[1].BranchFilters[0].BoneName = Pawn->GetSkateBone(TEXT("clavicle_L"));
                // The off hand's IK: the left wrist onto the sword's handle (UBotwMoveSet::TwoHandGripOffset), its elbow
                // as the clip bends it.
                GripIK.IKBone.BoneName = Pawn->GetSkateBone(TEXT("hand_L"));
                GripIK.EffectorTarget = FBoneSocketTarget(Pawn->GetSkateBone(TEXT("hand_R")));
                GripIK.JointTarget = FBoneSocketTarget(Pawn->GetSkateBone(TEXT("forearm_L")));
                for (int32 I = 0; I < 2; ++I)
                {
                    const TCHAR* Side = I ? TEXT("L") : TEXT("R");
                    GlideIK[I].IKBone.BoneName = Pawn->GetSkateBone(FName(*FString::Printf(TEXT("hand_%s"), Side)));
                    GlideTurn[I].BoneToModify.BoneName = GlideIK[I].IKBone.BoneName;
                }
                const TCHAR* const Chain[4] = { TEXT("spine"), TEXT("chest"), TEXT("neck"), TEXT("head") };
                for (int32 I = 0; I < 4; ++I) Flinch[I].BoneToModify.BoneName = Pawn->GetSkateBone(Chain[I]);
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
        const UBikeComponent* BikeC = Pawn->GetBike();
        const bool bBiking = BikeC && BikeC->IsEquipped() && BikeC->GetSequence();
        State.bAction = bSailing || bBiking || !Pawn->GetAnimationAction().IsNone();
        State.Serial = Pawn->GetActionSerial()+(SailboatC ? SailboatC->GetSerial()*7919 : 0)+(Ride ? Ride->GetSerial()*104729 : 0)+(BikeC ? BikeC->GetSerial()*15485863 : 0);
        State.BlendDuration = bSailing || bBiking ? .2f : Pawn->GetActionBlendTime();
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
        const bool Grounded=Pawn->IsA<ACairoCharacter>() && !bSailing && !bBiking &&
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
        // The bike's clips play on the bike's clock, which also poses the bike from the same frame of the clip.
        Grip.Alpha = bBiking ? 1.f : 0.f;
        for (int32 Side = 0; Side < 2; ++Side)
        {
            if (bBiking) BikeC->GetGrip(Side, Grip.Weight[Side], Grip.Offset[Side], Grip.Turn[Side]);
            else Grip.Weight[Side] = 0.f;
        }
        if (State.bAction && AppliedSerial != State.Serial)
        {
            if (UAnimSequence* Clip = bBiking ? BikeC->GetSequence() : bSailing ? SailboatC->GetSequence() : Pawn->GetDefinition()->FindAction(Pawn->GetAnimationClip()))
            {
                Action.SetSequence(Clip); Action.SetAccumulatedTime(bSailing||bBiking?0.f:Pawn->GetActionSourceStartTime());
                Action.SetLoopAnimation(bSailing || bBiking || Pawn->DoesActionLoop());
            }
            AppliedClip = bSailing || bRiding || bBiking ? NAME_None : Pawn->GetAnimationClip();
        }
        // The sword drawn or put away in the middle of an action swaps its armed copy in place, at the same time.
        else if (State.bAction && !bSailing && !bRiding && !bBiking && Pawn->GetAnimationClip() != AppliedClip)
        {
            AppliedClip = Pawn->GetAnimationClip();
            if (UAnimSequence* Clip = Pawn->GetDefinition()->FindAction(AppliedClip))
            { const float Time = Action.GetAccumulatedTime(); Action.SetSequence(Clip); Action.SetAccumulatedTime(Time); }
        }
        Action.SetPlayRate(bRiding || bBiking ? 0.f : bSailing ? 1.f : Pawn->GetActionPlayRate());
        if (bBiking) Action.SetAccumulatedTime(BikeC->GetPoseTime());
        const bool bCarrying = !bSailing && !bRiding && !bBiking && !Pawn->IsZeppelinPassenger();
        const UBotwMoveSet* Moves = Pawn->GetMoves();
        const float SwordGuardWeight = bCarrying && Moves && Pawn->GetDefinition()->FindAction(TEXT("SwordGuardCarry")) ? Moves->SwordGuardWeight() : 0.f;
        const float ShieldWeight = bCarrying && Moves ? Moves->GuardWeight() : 0.f;
        const float FreeWeight = bCarrying && Moves ? Moves->FreeArmWeight() : 0.f;
        const float OffHandGuard = bCarrying && Moves && SwordGuardWeight > 0.f ? Moves->SwordGuardOffHandWeight() : 0.f;
        const float CarryWeight = !bCarrying ? 0.f : Moves ? Moves->SwordCarryWeight() : Pawn->GetSword() ? Pawn->GetSword()->CarryWeight() : 0.f;
        RightArm.Alpha = SwordGuardWeight / FMath::Max(CarryWeight + SwordGuardWeight, KINDA_SMALL_NUMBER);
        LeftHand.Alpha = ShieldWeight / FMath::Max(ShieldWeight + FreeWeight, KINDA_SMALL_NUMBER);
        LeftArm.Alpha = OffHandGuard / FMath::Max(ShieldWeight + FreeWeight + OffHandGuard, KINDA_SMALL_NUMBER);
        CarryLayer.BlendWeights[0] = FMath::Min(1.f, CarryWeight + SwordGuardWeight);
        CarryLayer.BlendWeights[1] = FMath::Min(1.f, ShieldWeight + FreeWeight + OffHandGuard);
        GripIK.Alpha = bCarrying && Moves ? Moves->TwoHandGripWeight() : 0.f;
        if (Moves) GripIK.EffectorLocation = Moves->TwoHandGripOffset();
        for (int32 I = 0; I < 2; ++I)
        {
            GlideIK[I].Alpha = Moves && !bRiding && !bSailing ? Moves->GlideHandWeight() : 0.f;
            if (Moves) { GlideIK[I].EffectorLocation = Moves->GlideHandLocation(I); GlideIK[I].JointTargetLocation = Moves->GlideElbowLocation(I); }
            GlideTurn[I].Alpha = Moves && !bRiding && !bSailing ? Moves->GlideFistWeight() : 0.f;
            if (Moves) GlideTurn[I].Rotation = Moves->GlideHandRotation(I).Rotator();
        }
        FistLayer.BlendWeights[0] = Moves && !bRiding && !bSailing ? Moves->GlideFistWeight() : 0.f;
        const bool bFlinch = Moves && Moves->IsFlinching() && !bRiding && !bSailing && !bBiking;
        for (int32 I = 0; I < 4; ++I)
        {
            Flinch[I].Alpha = bFlinch && !Flinch[I].BoneToModify.BoneName.IsNone() ? 1.f : 0.f;
            Flinch[I].Rotation = bFlinch ? Moves->FlinchRotation(I).Rotator() : FRotator::ZeroRotator;
        }
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
        FreeArm.SetPosition(FVector(FMath::Min(Speed,AuthoredTopSpeed), 0, 0));
        FreeArm.SetPlayRate(FMath::Max(1.f, Speed / AuthoredTopSpeed));
        ArmedMoving.SetPosition(FVector(FMath::Min(Speed,AuthoredTopSpeed), 0, 0));
        ArmedMoving.SetPlayRate(FMath::Max(1.f, Speed / AuthoredTopSpeed));
        ArmedCrouching.SetPosition(FVector(Speed, 0, 0));
        ArmedCrouching.SetPlayRate(FMath::Max(1.f, Speed / AuthoredCrouchSpeed));
        Crouching.SetPlayRate(FMath::Max(1.f, Speed / AuthoredCrouchSpeed));
    }
};

// Sword clips carry their captured travel and turning on the root bone; library clips keep an identity root.
UWandererAnimInstance::UWandererAnimInstance() { RootMotionMode = ERootMotionMode::RootMotionFromEverything; }
FAnimInstanceProxy* UWandererAnimInstance::CreateAnimInstanceProxy() { return new FWandererAnimProxy(this); }
void UWandererAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete static_cast<FWandererAnimProxy*>(Proxy); }
