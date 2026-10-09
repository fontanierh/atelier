#include "AnimNode_SkiRider.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "BoneContainer.h"
#include "BonePose.h"
#include "GameFramework/Actor.h"
#include "TwoBoneIK.h"

void FAnimNode_SkiRider::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
    FAnimNode_Base::Initialize_AnyThread(Context);
    OnFoot.Initialize(Context);
}

void FAnimNode_SkiRider::CacheBones_AnyThread(const FAnimationCacheBonesContext& Context)
{
    OnFoot.CacheBones(Context);
}

void FAnimNode_SkiRider::PreUpdate(const UAnimInstance* InAnimInstance)
{
    if (!Ski.IsValid())
        if (const AActor* Owner = InAnimInstance ? InAnimInstance->GetOwningActor() : nullptr) Ski = Owner->FindComponentByClass<USkiComponent>();
    bActive = Ski.IsValid() && Ski->GetPose(Pose);
}

void FAnimNode_SkiRider::Update_AnyThread(const FAnimationUpdateContext& Context)
{
    OnFoot.Update(Context);
}

void FAnimNode_SkiRider::Evaluate_AnyThread(FPoseContext& Output)
{
    OnFoot.Evaluate(Output);
    if (!bActive) return;
    const FBoneContainer& Required = Output.Pose.GetBoneContainer();
    auto Index = [&Required](FName Name)
    {
        const int32 Mesh = Name.IsNone() ? INDEX_NONE : Required.GetPoseBoneIndexForBoneName(Name);
        return Mesh == INDEX_NONE ? FCompactPoseBoneIndex(INDEX_NONE) : Required.MakeCompactPoseIndex(FMeshPoseBoneIndex(Mesh));
    };
    const FCompactPoseBoneIndex Pelvis = Index(Pose.Pelvis);
    if (Pelvis == INDEX_NONE) return;

    const float Weight = FMath::Clamp(Pose.Weight, 0.f, 1.f);
    TArray<FTransform> Own;
    if (Weight < 1.f)
    {
        Own.Reserve(Output.Pose.GetNumBones());
        for (const FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex()) Own.Add(Output.Pose[Bone]);
    }

    FCSPose<FCompactPose> CS;
    CS.InitPose(Output.Pose);
    auto Set = [&CS](FCompactPoseBoneIndex Bone, const FTransform& T)
    {
        if (Bone == INDEX_NONE) return;
        const TArray<FBoneTransform> One = {FBoneTransform(Bone, T)};
        CS.SafeSetCSBoneTransforms(One);
    };
    // Turns a bone about its own joint by a component-space rotation; its children follow.
    auto Turn = [&CS, &Set](FCompactPoseBoneIndex Bone, const FQuat& By)
    {
        if (Bone == INDEX_NONE) return;
        FTransform T = CS.GetComponentSpaceTransform(Bone);
        T.SetRotation((By * T.GetRotation()).GetNormalized());
        Set(Bone, T);
    };

    // The pelvis where the simulation has it; the whole body follows.
    Set(Pelvis, FTransform(Pose.PelvisTarget.GetRotation(), Pose.PelvisTarget.GetLocation(), CS.GetComponentSpaceTransform(Pelvis).GetScale3D()));
    // The trunk bends forward over the spine; the head looks back up the run.
    for (const FName& Spine : Pose.Spine) Turn(Index(Spine), FQuat(Pose.BendAxis, Pose.Bend / 3.f));
    Turn(Index(Pose.Neck), FQuat(Pose.BendAxis, -Pose.Look * .5f));
    Turn(Index(Pose.Head), FQuat(Pose.BendAxis, -Pose.Look * .5f));

    auto Reach = [&](FName UpperName, FName MiddleName, FName EndName, const FVector& Target, const FVector& Pole, const FQuat* EndRotation)
    {
        const FCompactPoseBoneIndex Upper = Index(UpperName), Middle = Index(MiddleName), End = Index(EndName);
        if (Upper == INDEX_NONE || Middle == INDEX_NONE || End == INDEX_NONE) return;
        FTransform A = CS.GetComponentSpaceTransform(Upper), B = CS.GetComponentSpaceTransform(Middle), C = CS.GetComponentSpaceTransform(End);
        AnimationCore::SolveTwoBoneIK(A, B, C, Pole, Target, false, 1.0, 1.0);
        if (EndRotation) C.SetRotation(*EndRotation);
        TArray<FBoneTransform> Bones = {FBoneTransform(Upper, A), FBoneTransform(Middle, B), FBoneTransform(End, C)};
        Bones.Sort(FCompareBoneTransformIndex());
        CS.SafeSetCSBoneTransforms(Bones);
    };
    for (int32 Side = 0; Side < 2; ++Side)
    {
        Reach(Pose.Thigh[Side], Pose.Shin[Side], Pose.Foot[Side], Pose.Ankle[Side], Pose.Knee[Side], &Pose.FootRotation[Side]);
        Reach(Pose.UpperArm[Side], Pose.Forearm[Side], Pose.Hand[Side], Pose.HandTarget[Side], Pose.Elbow[Side], nullptr);
    }

    FCSPose<FCompactPose>::ConvertComponentPosesToLocalPoses(MoveTemp(CS), Output.Pose);
    if (Weight < 1.f)
    {
        int32 I = 0;
        for (const FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex())
        {
            FTransform Blended;
            Blended.Blend(Own[I++], Output.Pose[Bone], Weight);
            Output.Pose[Bone] = Blended;
        }
    }
}
