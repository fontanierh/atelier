#pragma once

#include "CoreMinimal.h"
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"

/** The rider in the saddle (UHorseComponent::PopulateRiderNode fills it on the game thread). The torso takes the horse's
 *  accelerations, turns and gait as a spring-damped pelvis lift and spine-to-head rotations in component space, then the
 *  arms and legs are re-solved so the hands stay on the reins and the feet in the stirrups. spine_mid, neck, head and each
 *  limb are optional; pelvis, spine and chest are required. */
struct FHorseRiderNode final : public FAnimNode_SkeletalControlBase
{
    enum { Pelvis, Spine, SpineMid, Chest, Neck, Head, ClavL, UpperL, ForeL, HandL, ClavR, UpperR, ForeR, HandR,
           ThighL, ShinL, FootL, ThighR, ShinR, FootR, Count };
    FBoneReference Bones[Count];

    /** Torso spring and limb IK weights: 0 on the ground, 1 in the saddle, eased through mounting and dismounting. */
    float TorsoWeight = 0.f;
    float IKWeight = 0.f;
    /** Pelvis lift and the breed's seat offset; the spring's turn of each axial bone (component space). */
    FVector PelvisOffsetCS = FVector::ZeroVector;
    FQuat PelvisDeltaCS = FQuat::Identity;
    FQuat SpineDeltaCS = FQuat::Identity;
    FQuat SpineMidDeltaCS = FQuat::Identity;
    FQuat ChestDeltaCS = FQuat::Identity;
    FQuat NeckDeltaCS = FQuat::Identity;
    FQuat HeadDeltaCS = FQuat::Identity;
    /** Hand and foot targets from the authored pose: the breed's grip and stirrup offsets and the rein pull. */
    FVector LeftHandOffsetCS = FVector::ZeroVector;
    FVector RightHandOffsetCS = FVector::ZeroVector;
    FVector LeftFootOffsetCS = FVector::ZeroVector;
    FVector RightFootOffsetCS = FVector::ZeroVector;

    FHorseRiderNode()
    {
        const TCHAR* Names[] = {TEXT("pelvis"), TEXT("spine"), TEXT("spine_mid"), TEXT("chest"), TEXT("neck"), TEXT("head"),
            TEXT("clavicle_L"), TEXT("upperarm_L"), TEXT("forearm_L"), TEXT("hand_L"),
            TEXT("clavicle_R"), TEXT("upperarm_R"), TEXT("forearm_R"), TEXT("hand_R"),
            TEXT("thigh_L"), TEXT("shin_L"), TEXT("foot_L"), TEXT("thigh_R"), TEXT("shin_R"), TEXT("foot_R")};
        for (int32 I = 0; I < Count; ++I) Bones[I].BoneName = Names[I];
    }

    virtual void InitializeBoneReferences(const FBoneContainer& RequiredBones) override
    {
        for (FBoneReference& Bone : Bones) Bone.Initialize(RequiredBones);
    }

    virtual bool IsValidToEvaluate(const USkeleton*, const FBoneContainer& RequiredBones) override
    {
        return (TorsoWeight > 0.f || IKWeight > 0.f) && Bones[Pelvis].IsValidToEvaluate(RequiredBones) &&
            Bones[Spine].IsValidToEvaluate(RequiredBones) && Bones[Chest].IsValidToEvaluate(RequiredBones);
    }

    virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& Result) override
    {
        const FBoneContainer& Required = Output.Pose.GetPose().GetBoneContainer();
        FCompactPoseBoneIndex Index[Count];
        bool Has[Count];
        FTransform Old[Count];
        for (int32 I = 0; I < Count; ++I)
        {
            Index[I] = Bones[I].GetCompactPoseIndex(Required);
            Has[I] = Index[I].IsValid();
            if (Has[I]) Old[I] = Output.Pose.GetComponentSpaceTransform(Index[I]);
        }
        // Missing optional bones stand in for their parent, so the chain carries on past them.
        if (!Has[SpineMid]) Old[SpineMid] = Old[Spine];
        if (!Has[Neck]) Old[Neck] = Old[Chest];
        if (!Has[Head]) Old[Head] = Old[Neck];

        // A child follows its parent's move and turn, then turns by its own increment.
        auto Follow = [](const FTransform& ParentOld, const FTransform& ParentNew, const FTransform& ChildOld, const FQuat& Turn)
        {
            const FQuat ParentTurn = ParentNew.GetRotation() * ParentOld.GetRotation().Inverse();
            const FVector At = ParentNew.GetLocation() + ParentTurn.RotateVector(ChildOld.GetLocation() - ParentOld.GetLocation());
            return FTransform((Turn * ParentTurn * ChildOld.GetRotation()).GetNormalized(), At, ChildOld.GetScale3D());
        };

        const float Torso = FMath::Clamp(TorsoWeight, 0.f, 1.f);
        auto Weighted = [Torso](const FQuat& Delta) { return FQuat::Slerp(FQuat::Identity, Delta, Torso); };
        FTransform New[Count];
        New[Pelvis] = Old[Pelvis];
        New[Pelvis].SetLocation(Old[Pelvis].GetLocation() + PelvisOffsetCS * Torso);
        New[Pelvis].SetRotation((Weighted(PelvisDeltaCS) * Old[Pelvis].GetRotation()).GetNormalized());
        New[Spine] = Follow(Old[Pelvis], New[Pelvis], Old[Spine], Weighted(SpineDeltaCS));
        New[SpineMid] = Has[SpineMid] ? Follow(Old[Spine], New[Spine], Old[SpineMid], Weighted(SpineMidDeltaCS)) : New[Spine];
        New[Chest] = Follow(Old[SpineMid], New[SpineMid], Old[Chest], Weighted(ChestDeltaCS));
        New[Neck] = Has[Neck] ? Follow(Old[Chest], New[Chest], Old[Neck], Weighted(NeckDeltaCS)) : New[Chest];
        New[Head] = Has[Head] ? Follow(Old[Neck], New[Neck], Old[Head], Weighted(HeadDeltaCS)) : New[Neck];
        for (const int32 I : {Pelvis, Spine, SpineMid, Chest, Neck, Head})
            if (Has[I]) Result.Emplace(Index[I], New[I]);

        // Each limb rides with the torso, then reaches its target in the bend plane it already has; the hand and foot keep
        // their authored turn so the fingers stay round the reins and the soles level in the stirrups.
        const float Reach = FMath::Clamp(IKWeight, 0.f, 1.f);
        auto Limb = [&](int32 Root, int32 Upper, const FTransform& RootNew, const FVector& Offset)
        {
            FTransform Upper0 = Follow(Old[Root], RootNew, Old[Upper], FQuat::Identity);
            FTransform Middle = Follow(Old[Upper], Upper0, Old[Upper + 1], FQuat::Identity);
            FTransform End = Follow(Old[Upper + 1], Middle, Old[Upper + 2], FQuat::Identity);
            if (Reach > 0.f)
            {
                const FVector Bend = Middle.GetLocation() - (Upper0.GetLocation() + End.GetLocation()) * .5f;
                const FVector Out = Bend.SizeSquared() > 1.f ? Bend : Middle.GetUnitAxis(EAxis::Y) * 15.f;
                const FVector Target = Old[Upper + 2].GetLocation() + Offset;
                const FVector Pole = Middle.GetLocation() + Out + .5f * (Target - Old[Upper + 2].GetLocation());
                AnimationCore::SolveTwoBoneIK(Upper0, Middle, End, Pole, FMath::Lerp(End.GetLocation(), Target, Reach), false, 1.f, 1.f);
                End.SetRotation(FQuat::Slerp(End.GetRotation(), Old[Upper + 2].GetRotation(), Reach).GetNormalized());
            }
            Result.Emplace(Index[Upper], Upper0);
            Result.Emplace(Index[Upper + 1], Middle);
            Result.Emplace(Index[Upper + 2], End);
        };
        for (int32 Side = 0; Side < 2; ++Side)
        {
            const int32 Clavicle = Side ? ClavR : ClavL;
            if (Has[Clavicle] && Has[Clavicle + 1] && Has[Clavicle + 2] && Has[Clavicle + 3])
            {
                const FTransform ClavicleNew = Follow(Old[Chest], New[Chest], Old[Clavicle], FQuat::Identity);
                Result.Emplace(Index[Clavicle], ClavicleNew);
                Limb(Clavicle, Clavicle + 1, ClavicleNew, Side ? RightHandOffsetCS : LeftHandOffsetCS);
            }
            const int32 Thigh = Side ? ThighR : ThighL;
            if (Has[Thigh] && Has[Thigh + 1] && Has[Thigh + 2])
                Limb(Pelvis, Thigh, New[Pelvis], Side ? RightFootOffsetCS : LeftFootOffsetCS);
        }
        Result.Sort(FCompareBoneTransformIndex());
    }
};
