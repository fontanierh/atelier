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
 * The transitions' clip player for the Ride backend (RIDE.md, "Rider"). The mount, dismount, carry, run-out, kick-out,
 * recover and get-up clips play through Unreal's animation system on a hidden mesh of the native rig (SK_SkateRider
 * with USkateRideAnimInstance), which this class ticks once per drawn frame: the caller (RideTransition.cpp) picks the
 * clips and their times as override layers, and the graph blends, mirrors and cross-fades them. The evaluated
 * component-space pose (the clips' root space: TRAJECTORY at the origin, the board's bones where the clip has them)
 * is published as root-space bones on the native rig's names (the same contract as FSkateRuntime's native output).
 * The riding pose is never this class's: Native's session poses the rider on the board.
 *
 * Without the rig (no clips in the build) it publishes no bones.
 */
class FRideAnimator
{
public:
    FRideAnimator();
    ~FRideAnimator();
    /** Load the rig and its mirror table if they are in the build (blocking; called before the first transition). The
     *  clips load on first use (Clip). */
    void Preload();
    /** Put the hidden pose mesh on the rider (kept across rides and on foot). Without an owner the body is not
     *  animated. */
    void Attach(AActor* Owner);
    void Detach();
    /** The rig is loaded and the pose mesh exists: the clips play on the body. */
    bool HasRig() const { return bRig && Mesh.IsValid() && Instance.IsValid(); }
    /** The rig is loaded (its clips can be looked up even before the mesh exists). */
    bool HasClips() const { return bRig; }
    /** The published bones' names and their reference pose in root space; none without the rig. */
    const TArray<FName>& GetNames() const { return HasRig() ? Names : NoNames; }
    const TArray<FTransform>& GetReference() const { return HasRig() ? Reference : NoBones; }
    /** Root-space bones for this frame (Dt: the drawn frame's time): the override layers, published as evaluated (the
     *  clips' root space, TRAJECTORY at the origin; the board bones are the clip's). Without an override the last
     *  layers are held. */
    void EvaluateFree(float Dt, TArray<FTransform>& Bones);

    // The clips the caller plays (mount, dismount, carry, run-out, kick-out, recover, get-up).
    /** A clip of the native library by name (loaded on first use, then kept). */
    UAnimSequence* Clip(FName Name);
    /** Play these layers, cross-fading in over BlendIn (call every frame with the layers' new times; BlendIn only
     *  counts on the first call, and a change of the main clip cross-fades over BlendIn again). Layers.bMirror applies
     *  as given. */
    void SetOverride(const FRideAnimLayers& Layers, float BlendIn);
    /** End the override: the last layers are held until the next one, which the next frame takes at once (the caller
     *  blends the switch itself). */
    void ClearOverride();
    /** A bone's local transform in a clip at Time (key data, unmirrored; SKATEBOARD_ROOT's is its pose under
     *  TRAJECTORY). */
    static FTransform Track(const UAnimSequence* Sequence, FName Bone, float Time);
    /** The clip's root motion (TRAJECTORY) between two times. */
    static FTransform RootMotion(const UAnimSequence* Sequence, float From, float To);

private:
    // The rig.
    bool bRig = false, bTried = false;
    TArray<FName> Names;
    TArray<FTransform> Reference;
    TStrongObjectPtr<USkeletalMesh> RigMesh;
    TStrongObjectPtr<UObject> MirrorTable;
    TMap<FName, TStrongObjectPtr<UAnimSequence>> Library;
    TWeakObjectPtr<USkeletalMeshComponent> Mesh;
    TWeakObjectPtr<USkateRideAnimInstance> Instance;
    // What is published without the rig.
    TArray<FName> NoNames;
    TArray<FTransform> NoBones;

    // Per-frame state: the override and the cross-fade (or cut) asked for the next frame, the last frame's layers
    // and their main clip.
    bool bOverride = false;
    FRideAnimLayers Override;
    float OverrideBlend = 0, PendingBlend = 0;
    bool bCutNext = false;
    bool bFirst = true;
    const UAnimSequence* LastKey = nullptr;
    FRideAnimLayers Last;

    UAnimSequence* Load(const TCHAR* Name);
    /** Run the graph on these layers (cross-fading first when Inertialize > 0). */
    void Run(const FRideAnimLayers& Layers, float Inertialize, float Dt);
};
