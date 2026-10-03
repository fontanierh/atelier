#include "AnimNode_SkateRider.h"
#include "SkateComponent.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeMessages.h"
#include "Animation/AnimNode_Inertialization.h"
#include "GameFramework/Actor.h"

FAnimNode_Base* FAnimNode_SkateRider::GetRoot()
{
    Blend.Source.SetLinkNode(this);
    return &Blend;
}

void FAnimNode_SkateRider::GetNodes(TArray<FAnimNode_Base*>& Nodes)
{
    Blend.Source.SetLinkNode(this);
    Nodes.Add(&Blend);
    Nodes.Add(this);
}

void FAnimNode_SkateRider::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
    FAnimNode_Base::Initialize_AnyThread(Context);
    OnFoot.Initialize(Context);
    bShowedSkate = bSkate = false;
}

void FAnimNode_SkateRider::CacheBones_AnyThread(const FAnimationCacheBonesContext& Context)
{
    OnFoot.CacheBones(Context);
}

void FAnimNode_SkateRider::PreUpdate(const UAnimInstance* InAnimInstance)
{
    if (!Skate.IsValid())
        if (const AActor* Owner = InAnimInstance ? InAnimInstance->GetOwningActor() : nullptr) Skate = Owner->FindComponentByClass<USkateComponent>();
    const USkateComponent* Component = Skate.Get();
    if (Component && !Component->GetRetailPose().IsEmpty()) Pose = Component->GetRetailPose();
    else Pose.Reset();
    if (Component) { BlendSerial = Component->GetPoseBlendSerial(); BlendTime = Component->GetPoseBlendTime(); }
}

void FAnimNode_SkateRider::Update_AnyThread(const FAnimationUpdateContext& Context)
{
    bSkate = !Pose.IsEmpty();
    // The component counts the switches it wants concealed (the first update only learns the count), and a switch
    // between the poses a frame after the count changed is blended too. Native rides never ask for a blend.
    const bool bSwitch = bSkate != bShowedSkate;
    if (((bSerialKnown && BlendSerial != AppliedSerial) || bSwitch) && BlendTime > 0.f)
    {
        if (UE::Anim::IInertializationRequester* Requester = Context.GetMessage<UE::Anim::IInertializationRequester>())
            Requester->RequestInertialization(BlendTime);
    }
    AppliedSerial = BlendSerial; bSerialKnown = true;
    if (!bSkate)
    {
        // The character's graph did not run while the skate pose showed: start it fresh rather than resume stale
        // transitions and clocks (the blend list's "reset child on activation").
        if (bShowedSkate)
        {
            FAnimationInitializeContext Reinitialize(Context.AnimInstanceProxy, Context.SharedContext);
            OnFoot.Initialize(Reinitialize);
        }
        OnFoot.Update(Context);
    }
    bShowedSkate = bSkate;
}

void FAnimNode_SkateRider::Evaluate_AnyThread(FPoseContext& Output)
{
    if (!bSkate) { OnFoot.Evaluate(Output); return; }
    Output.ResetToRefPose();
    const FBoneContainer& Required = Output.Pose.GetBoneContainer();
    for (const FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex())
    {
        const int32 Index = Required.MakeMeshPoseIndex(Bone).GetInt();
        if (Pose.IsValidIndex(Index)) Output.Pose[Bone] = Pose[Index];
    }
}
