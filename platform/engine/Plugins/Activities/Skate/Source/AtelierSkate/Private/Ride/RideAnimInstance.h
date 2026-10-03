#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "RideAnimInstance.generated.h"

class UAnimSequence;
class UBlendProfile;
class UMirrorDataTable;

/** One clip in the rider's blend: a sequence sampled at an explicit time, with its weight. */
struct FRideClipLayer
{
    UAnimSequence* Clip = nullptr;
    float Time = 0;
    float Weight = 0;
};

/** Up to four weighted clips, sampled at explicit times (the Ride session's clock drives every clip). */
struct FRideAnimLayers
{
    static constexpr int32 Max = 4;
    FRideClipLayer Layer[Max];
    int32 Num = 0;
    /** The board's hold on the rider: 1 puts the clip's board exactly on the session's deck and the body follows it
     *  (a clip whose board is elsewhere, such as in a hand, is moved onto the deck); 0 keeps the clip's own board
     *  under the rider's root, as the riding clips do (they tilt, pop and flip the board themselves). */
    float Lock = 1;
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

/** A bone's share in a channel clip (the clip's channel weight for that bone; bones not listed have none). */
struct FRideChannelBone
{
    const TCHAR* Bone;
    float Weight;
};

/**
 * A channel over the layers, as native's animation channels (AnimationChannels.cpp, ChannelBlendPoseSample): up to
 * three clips phase-blended by Weight, each with its per-bone weights, replace the layers' pose bone by bone in local
 * space by Alpha times the blended per-bone weight. It plays before the stance mirror, so it mirrors with the body.
 */
struct FRideAnimChannel
{
    static constexpr int32 Max = 3;
    UAnimSequence* Clip[Max] = {};
    TConstArrayView<FRideChannelBone> Bones[Max];
    float Weight[Max] = {};
    float Time = 0;
    float Alpha = 0;
};

/** What the rider's graph plays on its next update: the layers (with the stance mirror) and a cross-fade request. */
struct FRideAnimFrame
{
    FRideAnimLayers Layers;
    /** Over the layers: native's fakie channel (the head and chest toward the travel). */
    FRideAnimChannel Channel;
    /** Above zero: inertialize from the pose before this frame over this many seconds. */
    float Inertialize = 0;
    /** With Inertialize: the board (SKATEBOARD_ROOT and the bones under it) takes the new clip at once while the body
     *  blends, for a board that ends turned end for end and looks the same either way round. */
    bool bCutBoard = false;
};

/**
 * The Ride rider's animation graph, built in C++ like the game's own anim instances: four explicit-time sequence
 * evaluators blended by weight (FAnimNode_MultiWayBlend), a channel over them (FRideAnimChannel), the stance mirror
 * (FAnimNode_Mirror with the rig's mirror table: a regular rider plays the clips mirrored) and inertialization for the
 * cross-fades between clips. It runs on a hidden mesh of the native rig that FRideAnimator ticks after each session step; the session's state machine
 * chooses the clips and their times, and the curves the clips carry (PUSH_CONTACT and the rest) are read back from
 * the instance after evaluation.
 */
UCLASS(Transient)
class USkateRideAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
public:
    USkateRideAnimInstance();
    void SetMirrorTable(UMirrorDataTable* Table) { MirrorTable = Table; }
    UMirrorDataTable* GetMirrorTable() const { return MirrorTable; }
    /** Builds the blend profile that cuts this bone and its children (time factor 0) in an inertialization. */
    void SetBoardBone(FName Bone);
    const UBlendProfile* GetBoardCut() const { return BoardCut; }
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
    UPROPERTY(Transient) TObjectPtr<UBlendProfile> BoardCut;
    UPROPERTY(Transient) TArray<TObjectPtr<UAnimSequence>> Held;
    FRideAnimFrame Frame;
};
