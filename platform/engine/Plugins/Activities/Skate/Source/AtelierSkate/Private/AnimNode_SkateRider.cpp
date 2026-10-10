#include "AnimNode_SkateRider.h"
#include "SkateComponent.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeMessages.h"
#include "Animation/AnimNode_Inertialization.h"
#include "GameFramework/Actor.h"
#include "HAL/IConsoleManager.h"

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
    if (Component && !Component->GetRiderPose().IsEmpty()) Pose = Component->GetRiderPose();
    else Pose.Reset();
    if (Component) { BlendSerial = Component->GetPoseBlendSerial(); BlendTime = Component->GetPoseBlendTime(); }
    static const IConsoleVariable* Trace = IConsoleManager::Get().FindConsoleVariable(TEXT("skate.RideTrace"));
    bTrace = Trace && Trace->GetInt() > 0;
}

void FAnimNode_SkateRider::Update_AnyThread(const FAnimationUpdateContext& Context)
{
    bSkate = !Pose.IsEmpty();
    // The component counts the switches it wants concealed (the first update only learns the count), and a switch
    // between the poses a frame after the count changed is blended too. Simulation rides never ask for a blend.
    const bool bSwitch = bSkate != bShowedSkate;
    const bool bAsked = bSerialKnown && BlendSerial != AppliedSerial;
    UE::Anim::IInertializationRequester* Requester = nullptr;
    if ((bAsked || bSwitch) && BlendTime > 0.f)
    {
        Requester = Context.GetMessage<UE::Anim::IInertializationRequester>();
        if (Requester) Requester->RequestInertialization(BlendTime);
    }
    if (bTrace && (bAsked || bSwitch))
        UE_LOG(LogTemp, Display, TEXT("SKATE trace node f%llu: %s, serial %u -> %u, %s %.2f s"), GFrameCounter,
            bSwitch ? (bSkate ? TEXT("to the skate pose") : TEXT("to the own pose")) : TEXT("same pose"), AppliedSerial, BlendSerial,
            Requester ? TEXT("inertialized") : BlendTime > 0.f ? TEXT("no requester, cut") : TEXT("cut"), BlendTime);
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
