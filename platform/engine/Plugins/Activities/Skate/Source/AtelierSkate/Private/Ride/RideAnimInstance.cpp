#include "RideAnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimSequence.h"
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
    // simulation clips' own fastest limbs (1100 to 1300 cm/s, the trick clips').
    constexpr float CrossFadeSpeed = 1000.f;
    const FName BodyRoot(TEXT("HIPS"));
}

struct FRideAnimProxy final : public FAnimInstanceProxy
{
    FAnimNode_SequenceEvaluator_Standalone Clips[FRideAnimLayers::Max];
    FAnimNode_MultiWayBlend Blend;
    FAnimNode_Mirror_Standalone Mirror;
    FAnimNode_RideInertialization Inertia;
    FRideAnimFrame Frame;
    UMirrorDataTable* Table = nullptr;

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
        Inertia.MaxSpeed = CrossFadeSpeed; Inertia.SpeedRoot = BodyRoot;
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
        if (Frame.Inertialize > 0) Inertia.RequestInertialization(Frame.Inertialize);
    }
};

USkateRideAnimInstance::USkateRideAnimInstance()
{
    // The clips' TRAJECTORY is zeroed at import; the caller moves the rider.
    RootMotionMode = ERootMotionMode::IgnoreRootMotion;
    // FRideAnimator ticks and evaluates the mesh itself, once per drawn frame.
    bUseMultiThreadedAnimationUpdate = false;
}

void USkateRideAnimInstance::Hold(const TArray<UAnimSequence*>& Sequences)
{
    for (UAnimSequence* Sequence : Sequences) if (Sequence) Held.AddUnique(Sequence);
}

FAnimInstanceProxy* USkateRideAnimInstance::CreateAnimInstanceProxy() { return new FRideAnimProxy(this); }
void USkateRideAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete static_cast<FRideAnimProxy*>(Proxy); }
