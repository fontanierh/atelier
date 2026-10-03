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
}

struct FRideAnimProxy final : public FAnimInstanceProxy
{
    FAnimNode_SequenceEvaluator_Standalone Clips[FRideAnimLayers::Max];
    FAnimNode_MultiWayBlend Blend;
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
        Mirror.SetSourceLinkNode(&Blend);
        Mirror.SetBlendTimeOnMirrorStateChange(MirrorBlend);
        Inertia.Source.SetLinkNode(&Mirror);
    }
    virtual FAnimNode_Base* GetCustomRootNode() override { return &Inertia; }
    virtual void GetCustomNodes(TArray<FAnimNode_Base*>& Nodes) override
    {
        Nodes.Reset();
        for (FAnimNode_SequenceEvaluator_Standalone& Clip : Clips) Nodes.Add(&Clip);
        Nodes.Append({&Blend, &Mirror, &Inertia});
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
