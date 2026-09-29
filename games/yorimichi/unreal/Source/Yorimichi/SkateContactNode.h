#pragma once

#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"

// Adapt a planted push to uneven ground. Lower the hips only when needed,
// keeping the front foot on its authored deck contact and both legs unstretched.
struct FSkateContactNode final : public FAnimNode_SkeletalControlBase
{
    FBoneReference Bones[7];
    FVector EffectorLocation = FVector::ZeroVector;
    FVector JointTargetLocation = FVector::ZeroVector;
    bool bContact = false;
    int32 PushHipIndex = 4;
    float DeltaSeconds = 0.f, PelvisDrop = 0.f;

    FSkateContactNode()
    {
        const TCHAR* Names[] = {TEXT("pelvis"),TEXT("thigh_L"),TEXT("shin_L"),TEXT("foot_L"),
                              TEXT("thigh_R"),TEXT("shin_R"),TEXT("foot_R")};
        for (int32 I=0; I<7; ++I) Bones[I].BoneName = Names[I];
    }
    virtual void InitializeBoneReferences(const FBoneContainer& RequiredBones) override
    {
        for (auto& Bone : Bones) Bone.Initialize(RequiredBones);
        PelvisDrop = 0.f;
    }
    virtual bool IsValidToEvaluate(const USkeleton*,const FBoneContainer& RequiredBones) override
    {
        for (const auto& Bone : Bones) if (!Bone.IsValidToEvaluate(RequiredBones)) return false;
        return true;
    }
    virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output,TArray<FBoneTransform>& Result) override
    {
        if (!bContact && PelvisDrop <= KINDA_SMALL_NUMBER) return;
        const auto& RequiredBones = Output.Pose.GetPose().GetBoneContainer();
        FCompactPoseBoneIndex Indices[7];
        FTransform Pose[7];
        for (int32 I=0; I<7; ++I)
        {
            Indices[I] = Bones[I].GetCompactPoseIndex(RequiredBones);
            Pose[I] = Output.Pose.GetComponentSpaceTransform(Indices[I]);
        }
        double RequiredDrop = 0.;
        if (bContact)
        {
            const FVector Hip = Pose[PushHipIndex].GetLocation();
            const double Reach = FVector::Distance(Hip,Pose[PushHipIndex+1].GetLocation())+
                FVector::Distance(Pose[PushHipIndex+1].GetLocation(),Pose[PushHipIndex+2].GetLocation())-.1;
            const double Horizontal = FVector::DistSquared2D(Hip,EffectorLocation);
            const double Height = FMath::Sqrt(FMath::Max(0.,Reach*Reach-Horizontal));
            RequiredDrop = FMath::Clamp(Hip.Z-EffectorLocation.Z-Height,0.,18.);
        }
        // Meet the ground immediately; rise smoothly after the foot lifts.
        PelvisDrop = FMath::Max(float(RequiredDrop),FMath::FInterpConstantTo(PelvisDrop,0.f,DeltaSeconds,120.f));
        const FVector Offset(0,0,-PelvisDrop);
        Pose[0].AddToTranslation(Offset);
        Result.Emplace(Indices[0],Pose[0]);
        for (int32 HipIndex : {1,4})
        {
            FTransform& Hip = Pose[HipIndex];
            FTransform& Knee = Pose[HipIndex+1];
            FTransform& Foot = Pose[HipIndex+2];
            const FVector Target = HipIndex==PushHipIndex && bContact ? EffectorLocation : Foot.GetLocation();
            const FVector Pole = HipIndex==PushHipIndex && bContact ? JointTargetLocation : Knee.GetLocation();
            Hip.AddToTranslation(Offset); Knee.AddToTranslation(Offset); Foot.AddToTranslation(Offset);
            AnimationCore::SolveTwoBoneIK(Hip,Knee,Foot,Pole,Target,false,1.,1.);
            for (int32 I=HipIndex; I<HipIndex+3; ++I) Result.Emplace(Indices[I],Pose[I]);
        }
        Result.Sort(FCompareBoneTransformIndex());
    }
};
