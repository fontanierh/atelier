#include "RideAnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendProfile.h"
#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "AnimNode_RideInertialization.h"
#include "Animation/MirrorDataTable.h"
#include "AnimNodes/AnimNode_SequenceEvaluator.h"
#include "AnimNodes/AnimNode_MultiWayBlend.h"
#include "AnimNodes/AnimNode_Mirror.h"

namespace
{
    // A stance change (a regular rider switching to goofy) cross-fades over this long.
    constexpr float MirrorBlend = .2f;
    // A cross-fade never sweeps the body (HIPS and the bones under it) faster than this (cm/s), a little under the
    // trick clips' own fastest limbs (1100 to 1300 cm/s). A quick flick pops from the anticipation's first frames,
    // 50 to 65 cm from the pop clip's first pose: the pop's .05 s cross-fade would sweep the head across that at up
    // to 1900 cm/s; it lasts about .1 s instead.
    constexpr float CrossFadeSpeed = 1000.f;
    const FName BodyRoot(TEXT("HIPS"));
}

/**
 * Native's channel blend (AnimationPlayback.cpp, ChannelBlendPoseSample): each bone of the source pose moves toward the
 * channel's pose, in local space, by the channel's Alpha times the bone's weight in the channel clips (phase-blended
 * as the clips are, clamped to 1). Curves and attributes stay the source's.
 */
struct FRideChannelNode final : public FAnimNode_Base
{
    FPoseLink Source, Channel;
    FRideAnimChannel Settings;

    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override
    {
        FAnimNode_Base::Initialize_AnyThread(Context);
        Source.Initialize(Context); Channel.Initialize(Context);
    }
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override
    {
        Source.CacheBones(Context); Channel.CacheBones(Context);
        Serial = 0;
    }
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override
    {
        Source.Update(Context);
        if (FAnimWeight::IsRelevant(Settings.Alpha)) Channel.Update(Context.FractionalWeight(Settings.Alpha));
    }
    virtual void Evaluate_AnyThread(FPoseContext& Output) override
    {
        Source.Evaluate(Output);
        if (!FAnimWeight::IsRelevant(Settings.Alpha)) return;
        FPoseContext Other(Output);
        Channel.Evaluate(Other);
        CacheWeights(Output.Pose.GetBoneContainer());
        for (const FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex())
        {
            float W = 0;
            for (int32 C = 0; C < FRideAnimChannel::Max; ++C) W += Settings.Weight[C] * Weights[C][Bone.GetInt()];
            W = FMath::Clamp(W * Settings.Alpha, 0.f, 1.f);
            if (FAnimWeight::IsRelevant(W)) Output.Pose[Bone].BlendWith(Other.Pose[Bone], W);
        }
    }

private:
    // Each clip's per-bone weights by compact pose index, for the bone container and the bone lists they were made
    // for.
    TArray<float> Weights[FRideAnimChannel::Max];
    const FRideChannelBone* Lists[FRideAnimChannel::Max] = {};
    uint16 Serial = 0;

    void CacheWeights(const FBoneContainer& Container)
    {
        bool bSame = Serial != 0 && Serial == Container.GetSerialNumber();
        for (int32 C = 0; C < FRideAnimChannel::Max; ++C) bSame = bSame && Lists[C] == Settings.Bones[C].GetData();
        if (bSame) return;
        const FReferenceSkeleton& Skeleton = Container.GetReferenceSkeleton();
        const int32 Num = Container.GetCompactPoseNumBones();
        for (int32 C = 0; C < FRideAnimChannel::Max; ++C)
        {
            Weights[C].Init(0.f, Num);
            for (const FRideChannelBone& Entry : Settings.Bones[C])
            {
                const int32 Mesh = Skeleton.FindBoneIndex(FName(Entry.Bone));
                const FCompactPoseBoneIndex Bone = Mesh == INDEX_NONE ? FCompactPoseBoneIndex(INDEX_NONE)
                    : Container.MakeCompactPoseIndex(FMeshPoseBoneIndex(Mesh));
                if (Bone.IsValid()) Weights[C][Bone.GetInt()] = Entry.Weight;
            }
            Lists[C] = Settings.Bones[C].GetData();
        }
        Serial = Container.GetSerialNumber();
    }
};

struct FRideAnimProxy final : public FAnimInstanceProxy
{
    FAnimNode_SequenceEvaluator_Standalone Clips[FRideAnimLayers::Max];
    FAnimNode_MultiWayBlend Blend;
    // The channel: its clips phase-blended, then laid over the layers.
    FAnimNode_SequenceEvaluator_Standalone ChannelClips[FRideAnimChannel::Max];
    FAnimNode_MultiWayBlend ChannelBlend;
    FRideChannelNode Channel;
    FAnimNode_Mirror_Standalone Mirror;
    FAnimNode_RideInertialization Inertia;
    FRideAnimFrame Frame;
    UMirrorDataTable* Table = nullptr;
    const UBlendProfile* BoardCut = nullptr;

    explicit FRideAnimProxy(UAnimInstance* Owner) : FAnimInstanceProxy(Owner)
    {
        for (int32 I = 0; I < FRideAnimLayers::Max; ++I)
        {
            Clips[I].SetTeleportToExplicitTime(true);
            Clips[I].SetShouldLoop(false);
            Blend.AddPose();
            Blend.Poses[I].SetLinkNode(&Clips[I]);
        }
        Blend.bNormalizeAlpha = true;
        for (int32 I = 0; I < FRideAnimChannel::Max; ++I)
        {
            ChannelClips[I].SetTeleportToExplicitTime(true);
            ChannelClips[I].SetShouldLoop(false);
            ChannelBlend.AddPose();
            ChannelBlend.Poses[I].SetLinkNode(&ChannelClips[I]);
        }
        ChannelBlend.bNormalizeAlpha = true;
        Channel.Source.SetLinkNode(&Blend);
        Channel.Channel.SetLinkNode(&ChannelBlend);
        Mirror.SetSourceLinkNode(&Channel);
        Mirror.SetBlendTimeOnMirrorStateChange(MirrorBlend);
        Inertia.Source.SetLinkNode(&Mirror);
        Inertia.MaxSpeed = CrossFadeSpeed; Inertia.SpeedRoot = BodyRoot;
    }
    virtual FAnimNode_Base* GetCustomRootNode() override { return &Inertia; }
    virtual void GetCustomNodes(TArray<FAnimNode_Base*>& Nodes) override
    {
        Nodes.Reset();
        for (FAnimNode_SequenceEvaluator_Standalone& Clip : Clips) Nodes.Add(&Clip);
        Nodes.Add(&Blend);
        for (FAnimNode_SequenceEvaluator_Standalone& Clip : ChannelClips) Nodes.Add(&Clip);
        Nodes.Append({&ChannelBlend, &Channel, &Mirror, &Inertia});
    }
    virtual void PreUpdate(UAnimInstance* Instance, float Dt) override
    {
        FAnimInstanceProxy::PreUpdate(Instance, Dt);
        const USkateRideAnimInstance* Ride = CastChecked<USkateRideAnimInstance>(Instance);
        Frame = Ride->GetFrame();
        Table = Ride->GetMirrorTable();
        BoardCut = Ride->GetBoardCut();
    }
    virtual void Update(float Dt) override
    {
        const FRideAnimLayers& L = Frame.Layers;
        for (int32 I = 0; I < FRideAnimLayers::Max; ++I)
        {
            const bool bUsed = I < L.Num && L.Layer[I].Clip;
            Clips[I].SetSequence(bUsed ? L.Layer[I].Clip : nullptr);
            Clips[I].SetExplicitTime(bUsed ? L.Layer[I].Time : 0.f);
            Blend.DesiredAlphas[I] = bUsed ? L.Layer[I].Weight : 0.f;
        }
        const FRideAnimChannel& C = Frame.Channel;
        float Shares = 0;
        for (int32 I = 0; I < FRideAnimChannel::Max; ++I)
        {
            const bool bUsed = C.Clip[I] && C.Weight[I] > 0;
            ChannelClips[I].SetSequence(bUsed ? C.Clip[I] : nullptr);
            ChannelClips[I].SetExplicitTime(bUsed ? C.Time : 0.f);
            ChannelBlend.DesiredAlphas[I] = bUsed ? C.Weight[I] : 0.f;
            Shares += ChannelBlend.DesiredAlphas[I];
        }
        Channel.Settings = C;
        if (Shares <= 0) Channel.Settings.Alpha = 0;
        // Without a table the clips play as authored (goofy).
        Mirror.SetMirrorDataTable(Table);
        Mirror.SetMirror(Table && L.bMirror);
        if (Frame.Inertialize > 0) Inertia.RequestInertialization(Frame.Inertialize, Frame.bCutBoard ? BoardCut : nullptr);
    }
};

USkateRideAnimInstance::USkateRideAnimInstance()
{
    // The clips' TRAJECTORY is zeroed at import; the session moves the rider.
    RootMotionMode = ERootMotionMode::IgnoreRootMotion;
    // FRideAnimator ticks and evaluates the mesh itself, in step with the session.
    bUseMultiThreadedAnimationUpdate = false;
}

void USkateRideAnimInstance::SetBoardBone(FName Bone)
{
    BoardCut = nullptr;
    const USkeletalMeshComponent* Component = GetSkelMeshComponent();
    USkeleton* Skeleton = Component && Component->GetSkeletalMeshAsset() ? Component->GetSkeletalMeshAsset()->GetSkeleton() : nullptr;
    if (!Skeleton || Skeleton->GetReferenceSkeleton().FindBoneIndex(Bone) == INDEX_NONE) return;
    BoardCut = NewObject<UBlendProfile>(this, TEXT("BoardCut"), RF_Transient);
    BoardCut->SetSkeleton(Skeleton);
    BoardCut->Mode = EBlendProfileMode::TimeFactor;
    BoardCut->SetBoneBlendScale(Bone, 0.f, true, true);
}

void USkateRideAnimInstance::Hold(const TArray<UAnimSequence*>& Sequences)
{
    for (UAnimSequence* Sequence : Sequences) if (Sequence) Held.AddUnique(Sequence);
}

FAnimInstanceProxy* USkateRideAnimInstance::CreateAnimInstanceProxy() { return new FRideAnimProxy(this); }
void USkateRideAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete static_cast<FRideAnimProxy*>(Proxy); }
