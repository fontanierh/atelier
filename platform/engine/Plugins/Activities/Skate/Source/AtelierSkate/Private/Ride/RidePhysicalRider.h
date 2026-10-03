// The physical rider (RIDE.md, "Physical rider"): the rider's own bodies simulate in the world's Chaos scene and a
// Physics Control component drives them toward the animated pose, with the feet, pelvis and hands anchored where the
// animation (which stands on the deck) puts them. The same bodies go limp in a bail, and the get-up blends from a
// snapshot of the fallen body into the get-up clip.
#pragma once
#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Tickable.h"
#include "RidePhysicalRider.generated.h"

class ACharacter;
class ISkateRider;
class UBoxComponent;
class UPhysicalMaterial;
class UPhysicsAsset;
class UPhysicsControlAsset;
class UPhysicsControlComponent;
class UPrimitiveComponent;
class USkeletalMesh;
class USkeletalMeshComponent;

/** What the body is doing. Each phase but Off is a named profile in the control asset. */
UENUM()
enum class ERidePhysicalPhase : uint8 { Off, Riding, Air, Landing, Grind, Manual, Bail, GetUp, OnFoot };

/** How a bail starts: a slow, upright rider runs it out on foot; anything else falls. */
enum class ERideBailKind : uint8 { RunOut, Fall };

/** Where a get-up ends: back on the board, or standing on foot with the board left where it lies. */
enum class ERideGetUpExit : uint8 { Board, OnFoot };

/** The body during a ragdoll bail. */
enum class ERideBodyState : uint8 { Tumbling, Settled, Unstable };

/** One phase's control strengths. A strength is a frequency in Hz: an acceleration drive with the animation's
 *  velocity fed forward lags a target that accelerates at a by a/(2 pi f)^2. */
USTRUCT()
struct FRidePhysicalProfile
{
    GENERATED_BODY()

    /** Parent-space: every joint toward the animated local rotation. */
    UPROPERTY(EditAnywhere, Category = Joints, meta = (ClampMin = 0)) float Joints = 10.f;
    UPROPERTY(EditAnywhere, Category = Joints, meta = (ClampMin = 0)) float JointDamping = 1.f;
    /** Scales on Joints for the spine and head, the arms and hands, and the legs and feet. */
    UPROPERTY(EditAnywhere, Category = Joints, meta = (ClampMin = 0)) float Spine = 1.f;
    UPROPERTY(EditAnywhere, Category = Joints, meta = (ClampMin = 0)) float Arms = 1.f;
    UPROPERTY(EditAnywhere, Category = Joints, meta = (ClampMin = 0)) float Legs = 1.f;
    /** World-space: every body toward where the animation puts it, which keeps sag from adding up down the chain. */
    UPROPERTY(EditAnywhere, Category = Anchors, meta = (ClampMin = 0)) float Body = 8.f;
    /** World-space anchors: the pelvis, the feet (the animation stands them on the deck) and the hands. */
    UPROPERTY(EditAnywhere, Category = Anchors, meta = (ClampMin = 0)) float Pelvis = 16.f;
    UPROPERTY(EditAnywhere, Category = Anchors, meta = (ClampMin = 0)) float Feet = 12.f;
    UPROPERTY(EditAnywhere, Category = Anchors, meta = (ClampMin = 0)) float Hands = 2.f;
    /** Below 1 the anchors follow a turning board more closely (a damped drive trails its target). */
    UPROPERTY(EditAnywhere, Category = Anchors, meta = (ClampMin = 0)) float AnchorDamping = .5f;
    /** Physics Control's gravity multiplier on the bodies. 0 is its gravity compensation: the drives hold the pose
     *  rather than a pose sagging under the body's weight (1.9 cm at the pelvis at 1). A bail falls at 1. */
    UPROPERTY(EditAnywhere, Category = Body) float Gravity = 0.f;
    /** Whether the bodies other than the feet collide with the world (knocks, walls, the ground in a bail). */
    UPROPERTY(EditAnywhere, Category = Body) bool bBodyTouchesWorld = true;
    /** Whether the feet collide with the world. On the board the deck carries them, so they pass over its edges. */
    UPROPERTY(EditAnywhere, Category = Body) bool bFeetTouchWorld = false;
};

/** Project Settings > Plugins > Skate Physical Rider. The profiles are compiled into a control asset when a rider
 *  mounts (skate.RidePhysicalReload rebuilds it live); ControlAsset replaces them with an authored asset. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Skate Physical Rider"))
class URidePhysicalSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    URidePhysicalSettings();
    virtual FName GetCategoryName() const override { return TEXT("Plugins"); }

    /** An authored Physics Control asset: limbs naming the rider's bones, the control sets Anchor_Pelvis,
     *  Anchor_Feet and Anchor_Hands, and a profile per phase (Riding, Air, Landing, Grind, Manual, Bail, GetUp,
     *  OnFoot). Empty: the profiles below, on limbs found through the bone contract. */
    UPROPERTY(Config, EditAnywhere, Category = Rider) TSoftObjectPtr<UPhysicsControlAsset> ControlAsset;

    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile Riding;
    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile Air;
    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile Landing;
    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile Grind;
    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile Manual;
    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile Bail;
    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile GetUp;
    UPROPERTY(Config, EditAnywhere, Category = Profiles) FRidePhysicalProfile OnFoot;

    /** The rider's own physics asset: the constraint profile while riding (None: its defaults) and in a bail. */
    UPROPERTY(Config, EditAnywhere, Category = Joints) FName RideConstraintProfile;
    UPROPERTY(Config, EditAnywhere, Category = Joints) FName BailConstraintProfile = TEXT("Ragdoll");
    /** While riding, a joint limit that the animation passes widens to it instead of holding the body back. */
    UPROPERTY(Config, EditAnywhere, Category = Joints) bool bWidenLimitsWhileRiding = true;

    /** How long the Landing profile holds after a touchdown (s). */
    UPROPERTY(Config, EditAnywhere, Category = Timing, meta = (ClampMin = 0)) float LandingTime = .3f;
    /** How long the body takes to become physical when the ride starts, and to let go when it stops (s). */
    UPROPERTY(Config, EditAnywhere, Category = Timing, meta = (ClampMin = 0)) float MountBlend = .25f;
    UPROPERTY(Config, EditAnywhere, Category = Timing, meta = (ClampMin = 0)) float DismountBlend = .2f;
    /** How long the get-up blends from the fallen body's snapshot into the clip (s). */
    UPROPERTY(Config, EditAnywhere, Category = Timing, meta = (ClampMin = .05)) float GetUpBlend = .45f;

    /** A bail runs out on foot when the trunk leans less than this from upright (degrees)... */
    UPROPERTY(Config, EditAnywhere, Category = Bail) float RunOutTilt = 35.f;
    /** ...the board moves slower than this along the ground (cm/s)... */
    UPROPERTY(Config, EditAnywhere, Category = Bail) float RunOutSpeed = 450.f;
    /** ...and slower than this vertically (cm/s), spinning slower than this (degrees/s). */
    UPROPERTY(Config, EditAnywhere, Category = Bail) float RunOutImpact = 300.f;
    UPROPERTY(Config, EditAnywhere, Category = Bail) float RunOutSpin = 200.f;
    /** The bodies' friction in a fall (the lower of it and the ground's). A fall at speed slides and tumbles on for
     *  metres: the reference's body travels about its entry speed times a second. */
    UPROPERTY(Config, EditAnywhere, Category = Bail, meta = (ClampMin = 0)) float BailFriction = .25f;

    /** Query-only surfaces within this distance of the body are made physical so the bodies can touch them (cm). */
    UPROPERTY(Config, EditAnywhere, Category = World) float WorldRadius = 1200.f;

    const FRidePhysicalProfile& Profile(ERidePhysicalPhase Phase) const;
};

/** Asks the transition code whether it takes a bail of this kind (a run-out on foot); false makes it a ragdoll. */
DECLARE_DELEGATE_RetVal_OneParam(bool, FRideBailHandler, ERideBailKind);
/** Asks the transition code where a settled body gets up; unbound means back onto the board. */
DECLARE_DELEGATE_RetVal(ERideGetUpExit, FRideGetUpChooser);

UCLASS(Transient)
class URidePhysicalRider : public UObject, public FTickableGameObject
{
    GENERATED_BODY()
public:
    /** skate.RidePhysical: an active ragdoll while riding (1) or pure animation with a ragdoll for bails only (0). */
    static bool IsWanted();

    /** Set up on Rider's mesh: its own physics asset when it has six or more bodies, otherwise one built from the bone
     *  contract. The bodies follow the animation kinematically, unseen, until BlendIn or StartBail. Calling it again
     *  for the same rider and mesh keeps the current state. */
    bool Begin(ACharacter* Rider, const ISkateRider* Api);
    /** Everything off at once: the mesh shows the animation alone and the surfaces made physical go back to
     *  query-only. A loose board that was not taken is destroyed. A get-up blend that is running keeps running:
     *  its snapshot and alpha stay readable until it ends. */
    void End();
    /** End after the physics weight has faded over Seconds (at once when nothing is simulating). */
    void Release(float Seconds);
    bool IsActive() const { return Control != nullptr; }
    ACharacter* GetRider() const { return Rider; }

    /** Mount: the bodies start simulating where the animation is, moving with it, and their physics weight rises
     *  over Seconds. */
    void BlendIn(float Seconds);
    /** Dismount: the weight falls over Seconds, then the bodies follow the animation kinematically again. */
    void BlendOut(float Seconds);
    bool IsSimulating() const { return bSimulating; }
    float GetWeight() const { return Weight; }

    /** Each frame of the ride, after the step and before the mesh animates. Without it (no ride) the rider ticks
     *  itself in the OnFoot phase, so mount and dismount blends run while the character is on foot. */
    void Update(float Dt, ERidePhysicalPhase Phase);
    ERidePhysicalPhase GetPhase() const { return Phase; }

    // Bails.
    /** From the board's motion at the bail and the body's posture: upright, feet below the hips, slow, no big drop
     *  and no fast spin runs out; anything else falls. */
    ERideBailKind ClassifyBail(const FVector& BoardVelocity, const FVector& BoardSpin) const;
    /** Bound by the transition code: return true to take the bail as a run-out on foot (no ragdoll). */
    FRideBailHandler OnBailStart;
    /** Bound by the transition code: which way a settled body gets up. */
    FRideGetUpChooser ChooseGetUp;
    /** The bail's first frame: classify it and offer it to OnBailStart. True when the transition took it. */
    bool OfferBail(const FVector& BoardVelocity, const FVector& BoardSpin);
    bool IsBailOffered() const { return bBailOffered; }
    void ClearBailOffer() { bBailOffered = false; }
    ERideBailKind GetLastBailKind() const { return LastBailKind; }
    /** Go limp at once with the momentum the bodies have (or Velocity when they were not simulating): the Bail
     *  profile lets go of every anchor, leaves the joints a tone toward the clip and turns gravity on, and the bodies
     *  slide with BailFriction. The board becomes a tumbling box at BoardTransform. */
    bool StartBail(const FVector& Velocity, const FVector& BoardSpin, const FTransform& BoardTransform, float BoardScale);
    ERideBodyState UpdateBail(float Dt, float SettleTime);
    /** A body that met something it could not resolve: back to animation at once, the loose board removed. */
    void Abort();
    bool IsBailing() const { return bBail; }
    float GetBailTime() const { return BailTime; }
    /** The ground under the body, the way it faces (head from hips, degrees) and whether it lies on its back. */
    FVector GetBodyGround() const { return BodyGround; }
    float GetBodyYaw() const;
    bool IsFaceUp() const;
    FVector GetPelvisLocation() const;

    /** Get up where the body lies: snapshot the fallen pose and blend the pose from it (BlendFromSnapshot) over
     *  GetUpBlend. The bodies stay seen until the animation shows the snapshot (a frame or two: the mesh and Physics
     *  Control see the pose late), then follow it kinematically, unseen. For Board the active ragdoll returns at the
     *  end. */
    void StartGetUp(ERideGetUpExit Exit);
    bool IsGettingUp() const { return GetUpTime >= 0; }
    ERideGetUpExit GetGetUpExit() const { return GetUpExit; }
    /** 0 at the snapshot (until the bodies are handed over) to 1 at the end of the get-up blend (1 when none runs). */
    float GetGetUpAlpha() const;
    /** Blend a mesh-indexed local pose from the last snapshot by Alpha (0 the snapshot, 1 the pose), the root staying
     *  the pose's. False when there is no snapshot for this mesh or Alpha >= 1. */
    bool BlendFromSnapshot(TArray<FTransform>& LocalPose, float Alpha) const;

    /** The tumbling board while it is ours, and where its deck is (scaled), for the board's meshes to follow. */
    UBoxComponent* GetLooseBoard() const { return LooseBoard; }
    FTransform GetLooseBoardDeck() const;
    /** Hand the loose board over: it keeps simulating, and the rider never moves or destroys it again. */
    UBoxComponent* TakeLooseBoard();
    /** Destroy the loose board if it is still ours (the ride's board is back under the rider). */
    void DropLooseBoard();

    /** The physics asset built from the bone contract: a capsule per part, wide joint limits that every riding pose
     *  fits, no collision between the rider's own bodies. */
    static UPhysicsAsset* BuildPhysicsAsset(USkeletalMesh* Mesh, const ISkateRider* Api, UObject* Outer);

    /** Rebuild the profiles from the settings and apply the current one (skate.RidePhysicalReload). */
    void ReloadProfiles();
    // Logs every body (skate.RidePhysicalDump).
    void Dump() const;

    /** Telemetry: the bodies' distance from the animated pose (cm). In a bail the pose is carried as far as the
     *  ground under the pelvis has gone since the bail began, as a root that follows the body would carry it. */
    float GetPelvisError() const { return PelvisError; }
    float GetWorstError() const { return WorstError; }
    float GetFootError() const { return FootError; }
    FString Describe() const;

    // FTickableGameObject
    virtual void Tick(float DeltaTime) override;
    virtual ETickableTickType GetTickableTickType() const override;
    virtual bool IsTickable() const override { return Control != nullptr || GetUpTime >= 0; }
    virtual TStatId GetStatId() const override;
    virtual UWorld* GetTickableGameObjectWorld() const override;

private:
    UPROPERTY() TObjectPtr<ACharacter> Rider;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Mesh;
    UPROPERTY() TObjectPtr<UPhysicsControlComponent> Control;
    UPROPERTY() TObjectPtr<UPhysicsControlAsset> Asset;
    UPROPERTY() TObjectPtr<UPhysicsAsset> Built;
    UPROPERTY() TObjectPtr<USkeletalMesh> BuiltFor;
    UPROPERTY() TObjectPtr<UPhysicsAsset> SavedPhysicsAsset;
    UPROPERTY() TObjectPtr<UBoxComponent> LooseBoard;
    TWeakObjectPtr<UPrimitiveComponent> TakenBoard;
    const ISkateRider* Api = nullptr;
    bool bBuiltAsset = false, bOwnControlAsset = false;
    /** Whether the anchors are in the board's frame (the kinematic root body) rather than the world. */
    bool bBoardFrame = false;
    FName RootBone;
    FName SavedProfile;
    uint8 SavedUpdateMode = 0;
    FName PelvisBone, HeadBone, FootBones[2], ThighBones[2];

    ERidePhysicalPhase Phase = ERidePhysicalPhase::Off;
    float LandingLeft = 0;
    uint64 DrivenFrame = 0;
    bool bSimulating = false, bEndWhenOut = false;
    float Weight = 0, WeightTarget = 0, WeightRate = 0, AppliedWeight = -1;

    // Bail.
    bool bBail = false, bBailOffered = false;
    ERideBailKind LastBailKind = ERideBailKind::Fall;
    float BailTime = 0, Quiet = 0, BailLimit = 2500, BailRise = 400;
    FVector BailStart = FVector::ZeroVector, BailFloor = FVector::ZeroVector, BodyGround = FVector::ZeroVector;
    // The body's ground the frame before, Physics Control's root bone when the bail began (the bail's pose is
    // measured with it carried as far as the body's ground has gone), and the pelvis's height above the ground under
    // it (-1: none within HipsGroundRange).
    FVector LastBodyGround = FVector::ZeroVector, BailRoot = FVector::ZeroVector;
    float HipsAboveGround = -1;
    UPROPERTY() TObjectPtr<UPhysicalMaterial> BailMaterial;
    UPROPERTY() TObjectPtr<UPhysicalMaterial> SavedMaterial;
    bool bBailMaterial = false;
    float BoardScale = 1;

    // Get-up. GetUpWait counts the frames the bodies have waited for the animation to show the snapshot (-1: not
    // waiting).
    float GetUpTime = -1;
    int32 GetUpWait = -1;
    ERideGetUpExit GetUpExit = ERideGetUpExit::Board;
    TArray<FTransform> SnapshotWorld;
    TWeakObjectPtr<USkeletalMesh> SnapshotMesh;
    TWeakObjectPtr<USkeletalMeshComponent> SnapshotComponent;
    TWeakObjectPtr<UWorld> TickWorld;

    // Surfaces made physical around the body.
    TArray<TWeakObjectPtr<UPrimitiveComponent>> MadePhysical;
    FVector PhysicalCentre = FVector(1e30);
    // Where the mesh was last frame: a rider placed further than it can ride in a frame takes its body along, and
    // a launch in the frames after a placement too.
    FVector LastMeshLocation = FVector(1e30);
    FVector LastRiderVelocity = FVector::ZeroVector;
    int32 PlacedFrames = 0;
    // The frame Begin ran: Physics Control has no copy of the pose before its first update.
    uint64 BeganFrame = 0;

    float PelvisError = 0, WorstError = 0, FootError = 0;

    FName Bone(const TCHAR* Contract) const;
    UPhysicsControlAsset* BuildControlAsset(const UPhysicsAsset* Physics);
    void FillProfiles(UPhysicsControlAsset* Target) const;
    void ApplyPhase(ERidePhysicalPhase NewPhase);
    void SetSimulating(bool bSimulate, const FVector* Velocity = nullptr);
    void ApplyWeight();
    /** The bodies' physical material: BailFriction in a fall, the physics asset's own otherwise. */
    void ApplyBailMaterial(bool bBailing);
    /** The rider's own physics asset switches to the riding or the bail constraint profile; bWiden lets riding poses
     *  past a limit widen it. */
    void ApplyJointLimits(bool bRidingProfile, bool bWiden);
    void AdvanceGetUp(float Dt);
    /** Whether Physics Control's copy of the animation shows the snapshot (pelvis and head within SnapshotShown). */
    bool AnimationShowsSnapshot() const;
    /** The get-up's switch: weight 0, the bodies kinematic on the animation, the GetUp profile, the clock running. */
    void HandOverGetUp();
    void MakeWorldPhysical(const FVector& Centre);
    void RestoreWorld();
    /** The bodies' distance from Physics Control's copy of the animation. False when it has none (no errors). */
    bool Measure();
    /** Puts every body back on the animation, at rest (a placement, or a body carried off). */
    void ResetToAnimation();
    FVector TraceGround(const FVector& At) const;
};
