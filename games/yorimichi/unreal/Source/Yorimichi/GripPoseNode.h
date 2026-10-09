#pragma once
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"

/** The grips posed in the grip poser (assets/characters/grips), held exactly as posed in every clip: the last of the
 *  component-space work, so nothing after it moves a hand on its prop. A pinned hand goes to its place on the prop, given
 *  in Frame's space (the sword hand's, which carries the sword) or the component's (the glider, which the move set places
 *  on the body): its arm reaches it with a two-bone IK in the plane the arm already bends in (its collar bone turned
 *  toward it when the arm alone is too short: Reach), and the hand takes the posed turn. Then each finger bone takes its
 *  posed turn on its parent. A hand that carries its prop (the sword hand) is not moved, only its fingers posed: the prop
 *  is placed on the hand instead (UAdventureMoveSet::ReadGrips). Each hand's Weight blends from the incoming pose. */
struct FGripPoseNode final : public FAnimNode_SkeletalControlBase
{
    struct FHand
    {
        float Weight = 0.f;
        bool bPin = false;       // the hand moved onto Target (else only its fingers posed)
        bool bInFrame = false;   // Target in Frame's space (else the component's)
        FTransform Target = FTransform::Identity;   // the hand bone's place: its location and rotation
        FQuat Local[5][3];       // each finger bone's rotation on its parent (index to little, then the thumb)
        FBoneReference Hand, Bones[5][3];
        float Miss = 0.f;        // the last evaluation's distance between the pinned hand and its Target (component units)
        FHand() { for (auto& Digit : Local) for (FQuat& Q : Digit) Q = FQuat::Identity; }
    };
    FHand Hands[2];
    FBoneReference Frame;

    virtual void InitializeBoneReferences(const FBoneContainer& C) override
    {
        Frame.Initialize(C);
        for (FHand& H : Hands)
        {
            H.Hand.Initialize(C);
            for (auto& Digit : H.Bones) for (FBoneReference& B : Digit) B.Initialize(C);
        }
    }
    virtual bool IsValidToEvaluate(const USkeleton*, const FBoneContainer&) override
    {
        bool bAny = false;
        for (FHand& H : Hands) if (H.Weight > 0.f) bAny = true; else H.Miss = 0.f;
        return bAny;
    }
    virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& Result) override
    {
        const FBoneContainer& C = Output.Pose.GetPose().GetBoneContainer();
        TMap<int32, FTransform> Posed;   // the moved bones' new component transforms, by compact index
        for (FHand& H : Hands)
        {
            H.Miss = 0.f;
            const double Weight = FMath::Clamp(H.Weight, 0.f, 1.f);
            if (Weight <= 0. || !H.Hand.IsValidToEvaluate(C)) continue;
            const FCompactPoseBoneIndex HandBone = H.Hand.GetCompactPoseIndex(C);
            if (H.bPin)
            {
                const FCompactPoseBoneIndex Elbow = Parent(Output, HandBone);
                const FCompactPoseBoneIndex Shoulder = Elbow.IsValid() ? Parent(Output, Elbow) : FCompactPoseBoneIndex(INDEX_NONE);
                if (!Shoulder.IsValid() || (H.bInFrame && !Frame.IsValidToEvaluate(C))) continue;
                const FTransform Space = H.bInFrame ? At(Output, Posed, Frame.GetCompactPoseIndex(C)) : FTransform::Identity;
                const FVector Goal = Space.TransformPosition(H.Target.GetLocation());
                const FQuat Turn = (Space.GetRotation() * H.Target.GetRotation()).GetNormalized();
                Reach(Output, Posed, Parent(Output, Shoulder), Shoulder, Elbow, HandBone, FMath::Lerp(At(Output, Posed, HandBone).GetLocation(), Goal, Weight));
                FTransform T[3] = { At(Output, Posed, Shoulder), At(Output, Posed, Elbow), At(Output, Posed, HandBone) };
                const FQuat Was = T[2].GetRotation();
                AnimationCore::SolveTwoBoneIK(T[0], T[1], T[2], T[1].GetLocation(), FMath::Lerp(T[2].GetLocation(), Goal, Weight), false, 1., 1.);
                T[2].SetRotation(FQuat::Slerp(Was, Turn, Weight).GetNormalized());
                H.Miss = Weight >= 1. ? float((T[2].GetLocation() - Goal).Size()) : 0.f;
                Posed.Add(Shoulder.GetInt(), T[0]); Posed.Add(Elbow.GetInt(), T[1]); Posed.Add(HandBone.GetInt(), T[2]);
            }
            for (int32 F = 0; F < 5; ++F)
                for (int32 K = 0; K < 3; ++K)
                {
                    if (!H.Bones[F][K].IsValidToEvaluate(C)) continue;
                    const FCompactPoseBoneIndex Bone = H.Bones[F][K].GetCompactPoseIndex(C);
                    FTransform Local = Output.Pose.GetLocalSpaceTransform(Bone);
                    Local.SetRotation(FQuat::Slerp(Local.GetRotation(), H.Local[F][K], Weight).GetNormalized());
                    Posed.Add(Bone.GetInt(), Local * At(Output, Posed, Parent(Output, Bone)));
                }
        }
        for (const TPair<int32, FTransform>& Pair : Posed) Result.Emplace(FCompactPoseBoneIndex(Pair.Key), Pair.Value);
        Result.Sort(FCompareBoneTransformIndex());
    }

private:
    /** An arm too short for its goal reaches with its shoulder: the collar bone turned toward the goal, no further than
     *  the arm needs (nor than MaxCollar degrees), the arm carried with it. A grip's hands on the glider's bar, straight
     *  overhead, were up to 3 cm short of it on some of the glide's frames. */
    static void Reach(FComponentSpacePoseContext& Output, TMap<int32, FTransform>& Posed, FCompactPoseBoneIndex Collar,
                      FCompactPoseBoneIndex Shoulder, FCompactPoseBoneIndex Elbow, FCompactPoseBoneIndex HandBone, const FVector& Goal)
    {
        constexpr double MaxCollar = 35.;
        if (!Collar.IsValid()) return;
        const FVector S = At(Output, Posed, Shoulder).GetLocation(), E = At(Output, Posed, Elbow).GetLocation();
        const double Arm = (E - S).Size() + (At(Output, Posed, HandBone).GetLocation() - E).Size() - .01;
        if ((Goal - S).Size() <= Arm) return;
        const FTransform Was = At(Output, Posed, Collar);
        const FVector Pivot = Was.GetLocation();
        FVector Axis; double Angle;
        FQuat::FindBetweenVectors(S - Pivot, Goal - Pivot).ToAxisAndAngle(Axis, Angle);
        double Lo = 0., Hi = FMath::Min(Angle, FMath::DegreesToRadians(MaxCollar));
        if ((Goal - (Pivot + FQuat(Axis, Hi).RotateVector(S - Pivot))).Size() <= Arm)
            for (int32 Step = 0; Step < 16; ++Step)
            {
                const double Mid = (Lo + Hi) * .5;
                if ((Goal - (Pivot + FQuat(Axis, Mid).RotateVector(S - Pivot))).Size() <= Arm) Hi = Mid; else Lo = Mid;
            }
        FTransform Turned = Was;
        Turned.SetRotation((FQuat(Axis, Hi) * Was.GetRotation()).GetNormalized());
        Posed.Add(Collar.GetInt(), Turned);
    }
    static FCompactPoseBoneIndex Parent(FComponentSpacePoseContext& Output, FCompactPoseBoneIndex Bone)
    {
        return Output.Pose.GetPose().GetParentBoneIndex(Bone);
    }
    /** A bone's component transform once the bones above it have moved: its local one, carried by its parent's. */
    static FTransform At(FComponentSpacePoseContext& Output, const TMap<int32, FTransform>& Posed, FCompactPoseBoneIndex Bone)
    {
        if (const FTransform* T = Posed.Find(Bone.GetInt())) return *T;
        for (FCompactPoseBoneIndex Above = Parent(Output, Bone); Above.IsValid(); Above = Parent(Output, Above))
            if (Posed.Contains(Above.GetInt())) return Output.Pose.GetLocalSpaceTransform(Bone) * At(Output, Posed, Parent(Output, Bone));
        return Output.Pose.GetComponentSpaceTransform(Bone);
    }
};
