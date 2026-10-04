#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "RideAnimInstance.generated.h"

class UAnimSequence;
class UMirrorDataTable;

/** One clip in the rider's blend: a sequence sampled at an explicit time, with its weight. */
struct FRideClipLayer
{
    UAnimSequence* Clip = nullptr;
    float Time = 0;
    float Weight = 0;
};

/** Up to four weighted clips, sampled at explicit times (the caller's clock drives every clip). */
struct FRideAnimLayers
{
    static constexpr int32 Max = 4;
    FRideClipLayer Layer[Max];
    int32 Num = 0;
    /** Play the clips mirrored. The clips are authored goofy: a regular rider plays them mirrored (!bGoofy). */
    bool bMirror = false;

    void Reset() { Num = 0; }
    void Add(UAnimSequence* Clip, float Time, float Weight)
    {
        if (!Clip || Weight <= 1e-4f || Num >= Max) return;
        Layer[Num++] = {Clip, Time, Weight};
    }
    /** The clip with the most weight (the one whose change starts a cross-fade). */
    UAnimSequence* Main() const
    {
        int32 Best = -1;
        for (int32 I = 0; I < Num; ++I) if (Best < 0 || Layer[I].Weight > Layer[Best].Weight) Best = I;
        return Best >= 0 ? Layer[Best].Clip : nullptr;
    }
};

/** What the rider's graph plays on its next update: the layers (with the stance mirror) and a cross-fade request. */
struct FRideAnimFrame
{
    FRideAnimLayers Layers;
    /** Above zero: inertialize from the pose before this frame over this many seconds. */
    float Inertialize = 0;
};

/**
 * The Ride transitions' animation graph, built in C++ like the game's own anim instances: four explicit-time sequence
 * evaluators blended by weight (FAnimNode_MultiWayBlend), the stance mirror (FAnimNode_Mirror with the rig's mirror
 * table: a regular rider plays the clips mirrored) and inertialization for the cross-fades between clips. It runs on a
 * hidden mesh of the native rig that FRideAnimator ticks once per drawn frame; the transitions choose the clips and
 * their times.
 */
UCLASS(Transient)
class USkateRideAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
public:
    USkateRideAnimInstance();
    void SetMirrorTable(UMirrorDataTable* Table) { MirrorTable = Table; }
    UMirrorDataTable* GetMirrorTable() const { return MirrorTable; }
    /** Keep these sequences loaded for as long as the graph may play them. */
    void Hold(const TArray<UAnimSequence*>& Sequences);
    /** The next update plays this frame. */
    void SetFrame(const FRideAnimFrame& InFrame) { Frame = InFrame; }
    const FRideAnimFrame& GetFrame() const { return Frame; }

protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;

private:
    UPROPERTY(Transient) TObjectPtr<UMirrorDataTable> MirrorTable;
    UPROPERTY(Transient) TArray<TObjectPtr<UAnimSequence>> Held;
    FRideAnimFrame Frame;
};
