// The physical rider (RIDE.md, "Physical rider"): the rider's own bodies simulate in the world's Chaos scene and a
// Physics Control component drives them toward the animated pose, with the feet, pelvis and hands anchored where the
// animation (which stands on the deck) puts them. The same bodies go limp in a bail, and the get-up blends from a
// snapshot of the fallen body into the get-up clip.
#pragma once
#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "PhysicsControlComponent.h"
#include "PhysicsEngine/ConstraintInstance.h"
#include "Tickable.h"
#include "RidePhysicalRider.generated.h"

class ACharacter;
class ISkateRider;
class UBoxComponent;
class UInstancedStaticMeshComponent;
class UPhysicalMaterial;
class UPhysicsAsset;
class UPhysicsControlAsset;
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
    /** Continuous collision on every body: a body that would pass through a surface in one physics step (a hand
     *  thrown at the ground in a fall) is stopped at it. */
    UPROPERTY(EditAnywhere, Category = Body) bool bContinuousCollision = false;
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
    /** A physics asset built from the bone contract fits each body to the skin it carries: the convex hull of the
     *  mesh's vertices whose strongest weight is on its bone (or on a bone under it without a body), at the mass of
     *  the contract's capsule. Off: the contract's capsules, sized for a slim 1.7 m rider. The next mount uses a
     *  change. */
    UPROPERTY(Config, EditAnywhere, Category = Rider) bool bFitBodiesToSkin = true;

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
     *  metres: the reference's body travels its entry speed times 1.0 to 1.4 s, at any speed. */
    UPROPERTY(Config, EditAnywhere, Category = Bail, meta = (ClampMin = 0)) float BailFriction = .06f;
    /** A drag on the fallen bodies while the pelvis is down near the ground (linear damping on top of the physics
     *  asset's, 1/s). It takes speed in proportion to the speed, so a slide's length grows with its entry speed, as the
     *  reference's does; friction alone makes it grow with the square. */
    UPROPERTY(Config, EditAnywhere, Category = Bail, meta = (ClampMin = 0)) float BailDrag = 1.5f;
    /** The drag comes in smoothly from BailDragFrom to BailDragFull seconds after the bail (equal: at once). The
     *  reference's body keeps its speed for most of a second, then stops within about another. */
    UPROPERTY(Config, EditAnywhere, Category = Bail, meta = (ClampMin = 0)) float BailDragFrom = .7f;
    UPROPERTY(Config, EditAnywhere, Category = Bail, meta = (ClampMin = 0)) float BailDragFull = 1.1f;

    /** Query-only surfaces within this distance of the body are made physical so the bodies can touch them (cm). */
    UPROPERTY(Config, EditAnywhere, Category = World) float WorldRadius = 1200.f;

    const FRidePhysicalProfile& Profile(ERidePhysicalPhase Phase) const;
};

/** A joint's angular envelope as a live constraint holds it: its frame on the child body (Frame1) and on the parent
 *  (Frame2), its three angular motions and limits (degrees) and whether the limits are soft. The physical rider keeps
 *  two per joint of the built asset, riding and bail, and copies one onto the live constraint; the asset itself is
 *  shared by every rider on the mesh and never changes. */
struct FRideJointEnvelope
{
    FTransform Frame1 = FTransform::Identity, Frame2 = FTransform::Identity;
    TEnumAsByte<EAngularConstraintMotion> Swing1Motion = ACM_Limited, Swing2Motion = ACM_Limited, TwistMotion = ACM_Limited;
    float Swing1 = 0.f, Swing2 = 0.f, Twist = 0.f;
    bool bSoftSwing = true, bSoftTwist = true;
    float SwingStiffness = 0.f, SwingDamping = 0.f, TwistStiffness = 0.f, TwistDamping = 0.f;
    float AngularProjection = 0.f;   // Chaos's semi-physical angular projection (hard limits only), 0 to 1

    /** The envelope a constraint holds. */
    static FRideJointEnvelope Of(const FConstraintInstance& Constraint);
    /** Puts it on a live constraint, frames and limits, with the given limits in place of its own (twist, Swing1,
     *  Swing2; degrees). */
    void ApplyTo(FConstraintInstance& Constraint, const FVector& Limits) const;
    void ApplyTo(FConstraintInstance& Constraint) const { ApplyTo(Constraint, FVector(Twist, Swing1, Swing2)); }
    /** Whether a constraint's frames are this envelope's (within a tenth of a degree). */
    bool HasFrames(const FConstraintInstance& Constraint) const;
};

/** Physics Control that keeps last frame's drives through a frame without a pose. Under load the mesh can reach
 *  Physics Control's update with no component-space pose (its evaluation buffers out for the frame); Physics Control
 *  then aims every control at the identity, and the anchors pull the whole body onto the board in one step. */
UCLASS(Transient)
class URidePhysicsControl : public UPhysicsControlComponent
{
    GENERATED_BODY()
public:
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    /** The mesh whose pose the controls follow. */
    TWeakObjectPtr<USkeletalMeshComponent> Posed;
    /** Updates skipped for want of a pose, since the rider began. */
    int32 Skipped = 0;
    /** The frame of the last update (GFrameCounter): a profile invoked after it reaches the physics a frame late
     *  unless the controls are applied again. */
    uint64 UpdatedFrame = 0;
    /** Forgets that the controls widened Mesh's joint limits. Physics Control remembers a widened joint and, the next
     *  time it clamps that joint's target (ClampLinear, ClampExact) or stops widening it (None), puts the asset's
     *  limits back on the live constraint: over the bail's envelope, which it does not know about. Called after the
     *  rider has set the live limits itself. */
    void ForgetWidenedLimits(const USkeletalMeshComponent* Mesh);
private:
    float SkippedTime = 0;
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
    /** Put the loose board's deck at Deck (scaled, as GetLooseBoardDeck) and hold it there, out of physics: another
     *  simulation (the hybrid's Native session) moves the board. ReleaseLooseBoard gives it back to physics, moving
     *  with Velocity (cm/s) and Spin (rad/s). */
    void PlaceLooseBoard(const FTransform& Deck);
    void ReleaseLooseBoard(const FVector& Velocity, const FVector& Spin);
    /** Keep the loose board and the one handed over out of what the rider collides with (Pawn-blocking geometry,
     *  including the query-only surfaces physics does not see): each frame either is swept, moved and turned in steps
     *  (FRideClipPlayer::SweepBox), from where it was to where physics took it, and goes back to the last pose found free
     *  when it would have passed or turned into a face. Update calls it; so does the handed-over board's follower. */
    void GuardBoards();

    /** The physics asset built from the bone contract: a body per part (fitted to the skin, or a capsule), wide joint
     *  limits that every riding pose fits, no collision between the rider's own bodies. Fitted: how many bodies were
     *  fitted to the skin. BailEnvelopes, when given, gets each joint's bail envelope (Native's, by joint name): the
     *  asset keeps the riding one. */
    static UPhysicsAsset* BuildPhysicsAsset(USkeletalMesh* Mesh, const ISkateRider* Api, UObject* Outer, bool bFitToSkin,
        int32* Fitted = nullptr, TMap<FName, FRideJointEnvelope>* BailEnvelopes = nullptr);

    /** Where Component shows this frame: its parent's transform now with its own relative one. Inside
     *  CharacterMovement's move (the ride's step) a child's own transform is the frame before's until the move ends. */
    static FTransform ShownTransform(const USceneComponent* Component);

    /** Rebuild the profiles from the settings and apply the current one (skate.RidePhysicalReload). */
    void ReloadProfiles();
    // Logs every body (skate.RidePhysicalDump).
    void Dump() const;

    /** Telemetry: the bodies' distance from the animated pose (cm). In a bail the pose is carried as far as the
     *  ground under the pelvis has gone since the bail began, as a root that follows the body would carry it. */
    float GetPelvisError() const { return PelvisError; }
    float GetWorstError() const { return WorstError; }
    float GetFootError() const { return FootError; }
    /** How far the skin goes under the ground (cm along the ground's normal; below 0 it stays above): the deepest of
     *  a sample of the mesh's vertices, skinned on the CPU as the mesh shows them, each traced against the ground's
     *  complex collision. Bone is the body that carries the deepest; Groups, when given, gets the deepest of each of
     *  SkinGroupCount groups of bodies (SkinGroupName). False without CPU vertex data. */
    bool MeasureSkinDepth(float& Depth, FName& Bone, float* Groups = nullptr) const;
    static constexpr int32 SkinGroupCount = 7;
    /** torso (pelvis, spine, chest), head, upperarms, forearms, hands, legs (thighs, shins), feet. */
    static const TCHAR* SkinGroupName(int32 Group);
    /** How far each hand's skin (fingers included) stays from the torso's and thighs' bodies, as the mesh shows them
     *  (cm; below 0: that deep inside one): Gap[0] the left hand, Gap[1] the right, Near the body it comes closest
     *  to. Measured against the bodies' shapes, so on bodies fitted to the skin it says where the hand meets the
     *  skin. False without CPU vertex data. */
    bool MeasureHandGap(float Gap[2], FName Near[2]) const;
    /** The joint furthest past its range (Past in degrees, below 0 inside every range; Angles its twist, Swing1 and
     *  Swing2, as Chaos measures them against the live constraint's frames and limits, Limits those limits and bSoft
     *  whether they are soft), from the bodies' rotations, and the two bodies that may meet (in a bail) deepest in
     *  each other (Depth in cm, below 0 apart). False without bodies. */
    bool MeasureJoints(float& Past, FName& Joint, FVector& Angles, float& Depth, FName Pair[2], FVector* Limits = nullptr,
        bool* bSoft = nullptr) const;
    /** Which envelope the live joints of the built asset hold: OnBail and OnRiding count the joints on the bail's and
     *  the riding frames, Lost those whose limits are not what the rider set (in a bail the ramp's, hard; riding at
     *  least the asset's, which Physics Control's widening only opens), Ramp how far the bail's limits still stand
     *  open past its envelope (degrees). */
    void CheckEnvelope(int32& OnBail, int32& OnRiding, int32& Lost, float& Ramp) const;
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
    bool bBuiltFit = false;
    int32 BuiltFitted = 0;
    // Each joint's envelopes, by joint name: riding (the asset's, read as the rider begins) and bail (Native's, made
    // with the built asset). In a bail, RampLimits holds each joint's limits now (twist, Swing1, Swing2): they start
    // open to the pose the bail began in and close to the envelope at skate.RideBailTightenRate.
    TMap<FName, FRideJointEnvelope> RidingEnvelopes, BailEnvelopes;
    TMap<FName, FVector> RampLimits;
    bool bBailEnvelope = false;
    // The joints whose limits Physics Control had changed when the bail's first update ran, and the drives' fade
    // (skate.RideBailDriveFade) last applied.
    int32 EnvelopeLostAtStart = 0;
    float DriveFadeApplied = 1.f;
    UPROPERTY() TObjectPtr<UPhysicsAsset> SavedPhysicsAsset;
    UPROPERTY() TObjectPtr<UBoxComponent> LooseBoard;
    TWeakObjectPtr<UPrimitiveComponent> TakenBoard;
    // Where each board was when last guarded (GuardBoards).
    FTransform LooseLast = FTransform::Identity, TakenLast = FTransform::Identity;
    void GuardBoard(UPrimitiveComponent* Board, FTransform& Last);
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
    // The bail's first frames (skate.RideBailTrace): the frame it began and the pelvis's velocity then.
    uint64 BailFrame = 0;
    FVector BailPelvisVelocity = FVector::ZeroVector;
    int32 BailTraced = 0;
    FVector BailStart = FVector::ZeroVector, BailFloor = FVector::ZeroVector, BodyGround = FVector::ZeroVector;
    // The pelvis at the last bail update (a pelvis that crossed a face since, cut off from the bail's floor, went through
    // something); kept while the pelvis only reaches a face.
    FVector BailHips = FVector::ZeroVector;
    // The body's ground the frame before, Physics Control's root bone when the bail began (the bail's pose is
    // measured with it carried as far as the body's ground has gone), and the pelvis's height above the ground under
    // it (-1: none within HipsGroundRange).
    FVector LastBodyGround = FVector::ZeroVector, BailRoot = FVector::ZeroVector;
    float HipsAboveGround = -1;
    UPROPERTY() TObjectPtr<UPhysicalMaterial> BailMaterial;
    UPROPERTY() TObjectPtr<UPhysicalMaterial> SavedMaterial;
    bool bBailMaterial = false;
    float BailDragApplied = 0;
    float BoardScale = 1;

    // Get-up. GetUpWait counts the frames the bodies have waited for the animation to show the snapshot (-1: not
    // waiting).
    float GetUpTime = -1;
    int32 GetUpWait = -1;
    ERideGetUpExit GetUpExit = ERideGetUpExit::Board;
    TArray<FTransform> SnapshotWorld;
    TWeakObjectPtr<USkeletalMesh> SnapshotMesh;
    TWeakObjectPtr<USkeletalMeshComponent> SnapshotComponent;
    // Each body's shape as points in its bone's space (a hull's vertices, a capsule's or sphere's surface), and its
    // lowest point where the body lay: the get-up keeps every shape above the lower of its two ends, not just the
    // bones (BlendFromSnapshot).
    struct FGetUpShape { int32 Bone = INDEX_NONE; TArray<FVector> Points; double SnapshotLow = 0.; };
    TArray<FGetUpShape> GetUpShapes;
    TWeakObjectPtr<UWorld> TickWorld;

    // Surfaces made physical around the body: whole components, and instances of instanced meshes one by one (a
    // component's own switch never reaches its instances' bodies).
    TArray<TWeakObjectPtr<UPrimitiveComponent>> MadePhysical;
    struct FMadeInstance { TWeakObjectPtr<UInstancedStaticMeshComponent> Mesh; int32 Index = INDEX_NONE; };
    TArray<FMadeInstance> MadeInstances;
    FVector PhysicalCentre = FVector(1e30);
    // Where the mesh was last frame: a rider placed further than it can ride in a frame takes its body along, and
    // a launch in the frames after a placement too.
    FVector LastMeshLocation = FVector(1e30);
    FVector LastRiderVelocity = FVector::ZeroVector;
    int32 PlacedFrames = 0;
    // The frame Begin ran: Physics Control has no copy of the pose before its first update.
    uint64 BeganFrame = 0;

    float PelvisError = 0, WorstError = 0, FootError = 0;
    // The vertices the skin depth samples (LOD0) and the body bone that carries each, for this mesh with these bodies.
    mutable TArray<int32> SkinSamples;
    mutable TArray<FName> SkinSampleBones;
    mutable TArray<uint8> SkinSampleGroups;
    mutable TWeakObjectPtr<const UPhysicsAsset> SkinSamplesFor;
    // The vertices each hand's body carries (LOD0), for MeasureHandGap.
    mutable TArray<int32> HandSamples[2];
    mutable TWeakObjectPtr<const UPhysicsAsset> HandSamplesFor;
    // Each body's shape as points in its bone's space (empty for a body that touches nothing), for the bodies' overlaps.
    mutable TArray<TArray<FVector>> BodyPoints;
    mutable TWeakObjectPtr<const UPhysicsAsset> BodyPointsFor;
    // The pairs of bodies that may meet (indices, the lower first: every pair the physics asset lets collide) and
    // those Chaos ignores now: all of them riding; in a bail, those that overlapped as it began, kept apart until they
    // come apart (ReleaseKeptPairs). PairsReleased counts the pairs this bail has let meet again. A pair is added to
    // Chaos's ignore list or taken off it only three frames after the last change the other way (PairsAddedFrame,
    // PairsRemovedFrame), so the two never cross on the physics thread; bIgnorePending: riding wants every pair
    // ignored and some still wait for that.
    TArray<FIntPoint> RiderPairs;
    TSet<FIntPoint> IgnoredPairs;
    int32 PairsReleased = 0;
    uint64 PairsAddedFrame = 0, PairsRemovedFrame = 0;
    bool bIgnorePending = false;

    FName Bone(const TCHAR* Contract) const;
    UPhysicsControlAsset* BuildControlAsset(const UPhysicsAsset* Physics);
    void FillProfiles(UPhysicsControlAsset* Target) const;
    void ApplyPhase(ERidePhysicalPhase NewPhase);
    void SetSimulating(bool bSimulate, const FVector* Velocity = nullptr);
    void ApplyWeight();
    /** The bodies' physical material: BailFriction in a fall, the physics asset's own otherwise. */
    void ApplyBailMaterial(bool bBailing);
    /** The bodies' linear damping: the physics asset's plus Drag (1/s). */
    void ApplyBailDrag(float Drag);
    /** The rider's own physics asset switches to the riding or the bail constraint profile; the built asset's joints
     *  take their riding or bail envelope (ApplyEnvelopes). bWiden lets riding poses past a limit widen it. */
    void ApplyJointLimits(bool bRidingProfile, bool bWiden);
    /** Every joint of the built asset takes its riding envelope, or its bail envelope with the limits open to the
     *  pose it is in (RampLimits). */
    void ApplyEnvelopes(bool bTighten);
    /** The bail's limits close toward its envelope (skate.RideBailTightenRate). */
    void UpdateRamp(float Dt);
    /** The Bail profile's joint drives scaled by Multiplier (skate.RideBailDriveFade). */
    void ApplyDriveFade(float Multiplier);
    /** Whether the bodies meet each other (in a bail), less the pairs that overlap where they are as it is switched on. */
    void SetSelfCollision(bool bOn);
    /** Chaos ignores every pair of the rider's bodies (RiderPairs) not ignored yet; bWithAsset adds the pairs the
     *  physics asset keeps apart to each body's list too. */
    void IgnoreRiderPairs(bool bWithAsset);
    /** Takes these pairs off Chaos's ignore list (on the physics thread). */
    void RemoveIgnoredPairs(const TArray<FIntPoint>& Pairs);
    /** In a bail: the pairs kept apart as it began that have come apart meet again. */
    void ReleaseKeptPairs();
    /** Each body's extent along the overlap test's directions, where the physics has it. */
    void BodyExtents(TArray<TArray<FVector2D>>& Extent) const;
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
