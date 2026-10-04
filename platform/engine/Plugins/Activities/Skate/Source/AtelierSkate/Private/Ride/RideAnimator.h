#pragma once
#include "CoreMinimal.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/WeakObjectPtrTemplates.h"
#include "RideTypes.h"
#include "RideAnimInstance.h"

class AActor;
class UAnimSequence;
class USkeletalMesh;
class USkeletalMeshComponent;
class USkateRideAnimInstance;

/**
 * The rider's pose for the Ride backend (RIDE.md, "Rider"). The native clips play through Unreal's animation system
 * on a hidden mesh of the native rig (SK_SkateRider with USkateRideAnimInstance), which this class ticks once per
 * drawn frame after the session's step: the session's state machine says what the body is doing, this class picks
 * the clips and their times, and the graph blends, mirrors and cross-fades them. The evaluated component-space pose
 * (the clips' root space: the deck's pivot at the origin for the riding clips) is placed on the session's deck and
 * published as root-space bones on the native rig's names (the same contract as FSkateRuntime's native output), with
 * the trucks and wheels placed from the session.
 *
 * Without the rig (no clips in the build) it publishes the board's seven bones alone and the character keeps its own
 * locomotion pose.
 */
class FRideAnimator
{
public:
    FRideAnimator();
    ~FRideAnimator();
    /** Load the rig and the clips if they are in the build (blocking; called before the first ride). */
    void Preload();
    /** Put the hidden pose mesh on the rider (kept across rides and on foot). Without an owner the body is not
     *  animated. */
    void Attach(AActor* Owner);
    void Detach();
    /** The clips are loaded and the pose mesh exists: the body is animated and the clips drive the board's flips. */
    bool HasRig() const { return bRig && Mesh.IsValid() && Instance.IsValid(); }
    /** The clips are loaded (their timing drives the session even before the mesh exists). */
    bool HasClips() const { return bRig; }
    const TArray<FName>& GetNames() const { return HasRig() ? Names : BoardNames; }
    const TArray<FTransform>& GetReference() const { return HasRig() ? Reference : BoardReference; }
    /** Root-space bones for this frame (Dt: the drawn frame's time). The root is the deck's pivot at rest. */
    void Evaluate(const FRideBodyPose& Body, const FRideBoardPose& Board, float Dt, TArray<FTransform>& Bones);
    /** Off the board: the override layers alone, published as evaluated (the clips' root space, TRAJECTORY at the
     *  origin; the board bones are the clip's). Without an override the last layers are held. */
    void EvaluateFree(float Dt, TArray<FTransform>& Bones);

    // Timing the session takes from the clips.
    /** The pop clip's ground part: from the flick to the wheels leaving. */
    float PopDelay(atelier::ride::Flick Trick, float Default) const;
    /** From the take-off to the board caught under the feet (the flip clips' board track), or Default. */
    float CatchTime(atelier::ride::Flick Trick, float Default) const;
    /** The DANGERZONE value (native's DangerZone attribute) of the grab clip the air plays at these times: the grab's
     *  into or cycle while it is held (once a flip is caught), its out after it is let go; 0 past the out, with no
     *  grab, or without the clips. */
    float GrabDanger(atelier::ride::Flick Trick, float TrickTime, ERideGrab Grab, float GrabTime, ERideGrab LastGrab, float SinceGrab) const;
    /** One push cycle: the lead before the foot touches (the first push of a run only), the contact and the
     *  recovery, for a push at Strong (0 slow .. 1 fast). False without the clips. */
    bool PushTiming(bool bFirst, float Strong, float& Lead, float& Contact, float& Recover) const;
    /** The switch clip's length (turning round on the board), 0 without the animated body (the board alone does not
     *  turn round). */
    float SwitchLength() const;

    // For transitions (mount, dismount, carry): clips the caller plays instead of the session's choice.
    /** A clip of the native library by name (loaded on first use, then kept). */
    UAnimSequence* Clip(FName Name);
    /** Play these layers instead of the session's choice, cross-fading in over BlendIn (call every frame with the
     *  layers' new times; BlendIn only counts on the first call, and a change of the main clip cross-fades over
     *  BlendIn again). Layers.bMirror and Layers.Lock apply as given. */
    void SetOverride(const FRideAnimLayers& Layers, float BlendIn);
    /** Back to the session's choice, cross-fading over BlendOut; 0 cuts (the next frame takes the choice and its board
     *  hold at once, for a caller that blends the switch itself). */
    void ClearOverride(float BlendOut);
    bool HasOverride() const { return bOverride; }
    /** A bone's local transform in a clip at Time (key data, unmirrored; SKATEBOARD_ROOT's is its pose under
     *  TRAJECTORY). */
    static FTransform Track(const UAnimSequence* Sequence, FName Bone, float Time);
    /** The clip's root motion (TRAJECTORY) between two times. */
    static FTransform RootMotion(const UAnimSequence* Sequence, float From, float To);

    // What was evaluated last (for the physical rider and QA).
    /** A clip curve's blended value (PUSH_CONTACT, DANGERZONE, ...). */
    float GetCurve(FName Curve) const;
    /** The pose mesh's component-space transforms (SK_SkateRider order, the same as GetNames()). */
    const TArray<FTransform>& GetComponentPose() const;
    /** The board's hold on the body (FRideAnimLayers::Lock), smoothed. */
    float GetLock() const { return Lock; }
    /** The clip with the most weight, by its native name. */
    FName GetMainClip() const;
    /** The main clip's time (s). */
    float GetMainTime() const;
    /** Root-space lift of the whole pose that keeps a tilted board's wheels and tips above the ground (cm). */
    float GetLift() const { return Lift; }
    /** The fakie channel's weight and the torso value it blends its clips by. */
    float GetFakieWeight() const { return FakieWeight; }
    /** The stance mirror the clips played with (a regular rider's, or a goofy one's riding switch). */
    bool GetMirror() const { return Last.bMirror; }
    float GetTorso() const { return Torso; }
    /** The board end for end under the rider: a trick that catches it backwards (a shove-it, a varial, a hardflip or
     *  an inward heelflip) leaves it so, nose trailing, until another one turns it back. The shown deck is then the
     *  clips' turned half a turn about its normal, as riding switch turns it. A new ride starts the right way round. */
    bool IsBoardReversed() const { return bBoardReversed; }
    void ResetBoardTurn() { bBoardReversed = false; }
    USkeletalMeshComponent* GetMesh() const { return Mesh.Get(); }

private:
    // The board-only fallback.
    TArray<FName> BoardNames;
    TArray<FTransform> BoardReference;
    // The rig.
    bool bRig = false, bTried = false;
    TArray<FName> Names;
    TArray<FTransform> Reference;
    TStrongObjectPtr<USkeletalMesh> RigMesh;
    TStrongObjectPtr<UObject> MirrorTable;
    TMap<FName, TStrongObjectPtr<UAnimSequence>> Library;
    TWeakObjectPtr<USkeletalMeshComponent> Mesh;
    TWeakObjectPtr<USkateRideAnimInstance> Instance;
    // Bone indices (in the published order) and the board's bind relative to the deck.
    int32 DeckIndex = 0;
    int32 TruckIndex[2] = {1, 2};
    int32 WheelIndex[4] = {3, 4, 5, 6};
    FTransform TruckFromDeck[2], WheelFromTruck[4];
    FVector TruckAxis[2], WheelAxis[4];     // the deck's length and width in each bone's own frame
    FVector DeckUp = FVector::UpVector;     // the deck's normal in its own frame
    FVector DeckNose = FVector::ForwardVector;      // its length, toward the nose
    float WheelRadius = 3.1f;

    // The clips by role.
    struct FTrickClips
    {
        UAnimSequence* Ground = nullptr; UAnimSequence* Air = nullptr; UAnimSequence* Follow = nullptr; float Catch = -1;
        // The trick's own low air cycle (Follow being the high one), and the two cycles' hips-to-board distances.
        UAnimSequence* Low = nullptr; float High = 0, Reach = 0;
    };
    struct FGrabClips { UAnimSequence* Into = nullptr; UAnimSequence* Cycle = nullptr; UAnimSequence* Out = nullptr; };
    struct FClips
    {
        UAnimSequence* Roll[4] = {};                        // centre, toes, heels, crouched
        UAnimSequence* PushInto = nullptr, *PushOut = nullptr;
        UAnimSequence* PushContact[2] = {}, *PushRecover[2] = {};   // slow, fast
        UAnimSequence* BrakeInto = nullptr, *BrakeCycle = nullptr, *BrakeOut = nullptr;
        UAnimSequence* StandFromBrake = nullptr, *Stand = nullptr, *StandOut = nullptr;
        UAnimSequence* SlideInto[2] = {}, *SlideCycle[2] = {}, *SlideOut[2] = {};   // frontside, backside
        UAnimSequence* Manual = nullptr, *NoseInto = nullptr, *NoseCycle = nullptr, *NoseOut = nullptr;
        UAnimSequence* Load = nullptr, *NoseLoad = nullptr;
        UAnimSequence* AirIdle = nullptr, *AirLow = nullptr, *AirExtend = nullptr;
        UAnimSequence* LandLow = nullptr, *LandHigh = nullptr, *LandGrab = nullptr, *LandSketchy = nullptr;
        FTrickClips Tricks[uint8(atelier::ride::Flick::Num)];
        FGrabClips Grabs[6];
        UAnimSequence* Grinds[6][2] = {};                   // kind, frontside/backside
        UAnimSequence* Fakie[3] = {};                       // the fakie channel by torso: head, head and chest, manual
        UAnimSequence* Switch[3][2] = {};                   // turning round: centre, heels, toes; standing, crouched
    } C;

    // Per-frame state.
    bool bOverride = false;
    FRideAnimLayers Override;
    float OverrideBlend = 0, PendingBlend = 0;
    bool bCutNext = false;
    const UAnimSequence* LastKey = nullptr;
    float LastKeyTime = 0;
    ERideMotion LastMotion = ERideMotion::Roll;
    float LastMotionTime = 0;
    bool bFirst = true;
    bool bBoardReversed = false;
    float Lock = 0, Lift = 0;
    float TruckRoll[2] = {0, 0};            // each truck's roll against the deck (degrees, about the deck's length)
    // The fakie channel: its weight, the torso value its clips blend by, its clock, and whether the rider rode fakie.
    float FakieWeight = 0, Torso = .5f, FakieTime = 0;
    bool bWasFakie = false;
    // The session's turns round (riding switch and back) seen so far, where the last frame put the clips' root and
    // the clips' deck it placed.
    uint32 LastTurns = 0;
    FTransform LastPlace, LastPoseDeck;
    FRideAnimLayers Last;
    TArray<FTransform> Empty;

    void SetBoardOnly();
    bool SetBoardIndices(const TArray<FName>& InNames, const TArray<FTransform>& InReference);
    UAnimSequence* Load(const TCHAR* Name);
    void Resolve();
    float FindCatch(const FTrickClips& Trick) const;
    const FTrickClips* TrickFor(atelier::ride::Flick Trick) const;
    bool IsTrickClip(const UAnimSequence* Sequence) const;
    static float SampleTime(const UAnimSequence* Sequence, float Time, bool bLoop);
    /** The session's choice: the layers and the clip whose change starts a cross-fade (over Blend; 0 cuts, as the
     *  chained clips of one move do). */
    const UAnimSequence* Choose(const FRideBodyPose& Body, FRideAnimLayers& Layers, float& Blend) const;
    /** The fakie channel's weight, torso and clock (no body: off the board, the channel fades out). */
    void UpdateFakie(const FRideBodyPose* Body, float Dt);
    /** Run the graph on these layers (cross-fading first when Inertialize > 0). */
    void Run(const FRideAnimLayers& Layers, float Inertialize, float Dt, bool bCutBoard = false, const FTransform* Turn = nullptr);
    /** Where the clips' deck goes: the session's deck, turned half a turn about its normal riding switch (the
     *  rider's frame on the board). */
    static FTransform RiderDeck(const FRideBodyPose& Body, const FRideBoardPose& Board);
    /** The clips' root space placed on Deck at the current Lock, ClipDeck being the clips' deck in it. */
    FTransform Placement(const FTransform& Deck, const FTransform& ClipDeck) const;
    /** Roll each truck against the deck so that its axle lies level with the ground (the root's XY plane) while the
     *  board is on its wheels; off them the trucks come back straight under the deck. */
    void LevelTrucks(const FRideBoardPose& Board, const FTransform& Deck, float Dt);
    void PlaceBoard(const FRideBoardPose& Board, TArray<FTransform>& Bones) const;
    /** The lowest point of a placed wheel's rim, in the root's space. */
    float WheelBottom(const TArray<FTransform>& Bones, int32 Wheel) const;
};
