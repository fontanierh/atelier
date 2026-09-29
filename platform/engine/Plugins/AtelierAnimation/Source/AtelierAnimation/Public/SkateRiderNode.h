#pragma once
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"

/** Keeps the rider on the moving board: every limb the clip has on the board (feet on the deck, hands on a grab) is carried
 *  by the board's motion away from where the clip assumes it (the pop pitch, a manual, a tilted landing). The clip's own
 *  limb position relative to the deck is kept; only the deck's delta is applied, through a two-bone solve. */
struct FSkateRiderNode final : public FAnimNode_SkeletalControlBase
{
    enum { ThighL, ShinL, FootL, ThighR, ShinR, FootR, UpperL, ForeL, HandL, UpperR, ForeR, HandR, Count };
    FBoneReference Bones[Count];
    /** Component space: the deck now and where the clips put it. */
    FTransform DeckNow = FTransform::Identity, DeckRest = FTransform::Identity;
    /** 0 foot_L, 1 foot_R, 2 hand_L, 3 hand_R. */
    float Weight[4] = {0.f, 0.f, 0.f, 0.f};

    FSkateRiderNode()
    {
        const TCHAR* Names[] = {TEXT("thigh_L"), TEXT("shin_L"), TEXT("foot_L"), TEXT("thigh_R"), TEXT("shin_R"), TEXT("foot_R"),
                                TEXT("upperarm_L"), TEXT("forearm_L"), TEXT("hand_L"), TEXT("upperarm_R"), TEXT("forearm_R"), TEXT("hand_R")};
        for (int32 I = 0; I < Count; ++I) Bones[I].BoneName = Names[I];
    }
    virtual void InitializeBoneReferences(const FBoneContainer& Required) override { for (auto& B : Bones) B.Initialize(Required); }
    virtual bool IsValidToEvaluate(const USkeleton*, const FBoneContainer& Required) override
    {
        for (const auto& B : Bones) if (!B.IsValidToEvaluate(Required)) return false;
        return true;
    }
    virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& Result) override
    {
        const FBoneContainer& Required = Output.Pose.GetPose().GetBoneContainer();
        FCompactPoseBoneIndex Index[Count] = {FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE),
            FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE),
            FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE)};
        FTransform Pose[Count];
        for (int32 I = 0; I < Count; ++I) { Index[I] = Bones[I].GetCompactPoseIndex(Required); Pose[I] = Output.Pose.GetComponentSpaceTransform(Index[I]); }
        const FTransform Delta = DeckRest.Inverse() * DeckNow;   // rest deck -> deck now, in component space
        const int32 Roots[4] = {ThighL, ThighR, UpperL, UpperR};
        for (int32 L = 0; L < 4; ++L)
        {
            const float W = FMath::Clamp(Weight[L], 0.f, 1.f);
            if (W <= KINDA_SMALL_NUMBER) continue;
            const int32 R = Roots[L];
            FTransform& Root = Pose[R]; FTransform& Joint = Pose[R + 1]; FTransform& End = Pose[R + 2];
            const FTransform Carried = End * Delta;
            const FVector Target = FMath::Lerp(End.GetLocation(), Carried.GetLocation(), W);
            const FQuat Turn = FQuat::Slerp(End.GetRotation(), Carried.GetRotation(), W);
            // The knee (elbow) keeps its side: carry its pole the same way.
            const FVector Pole = FMath::Lerp(Joint.GetLocation(), Delta.TransformPosition(Joint.GetLocation()), W) + (Joint.GetLocation() - (Root.GetLocation() + End.GetLocation()) * .5f) * .5f;
            AnimationCore::SolveTwoBoneIK(Root, Joint, End, Pole, Target, false, 1.f, 1.f);
            End.SetRotation(Turn);
            for (int32 I = R; I < R + 3; ++I) Result.Emplace(Index[I], Pose[I]);
        }
        Result.Sort(FCompareBoneTransformIndex());
    }
};
