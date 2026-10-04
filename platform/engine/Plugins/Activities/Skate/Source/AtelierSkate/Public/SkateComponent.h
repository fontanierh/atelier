#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SkateInput.h"
#include "SkateComponent.generated.h"

class ACharacter;
class ISkateRider;
class UStaticMeshComponent;
class USceneComponent;
class USkateRailSubsystem;
class UCharacterMovementComponent;
class UAudioComponent;
class USoundWave;
class USoundAttenuation;
class FSkateRuntime;
class FRideSession;
class UBoxComponent;
class UPhysicsAsset;
class URidePhysicalRider;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UAnimInstance;
struct FRideTransition; enum class ERideFoot : uint8; enum class ERideBailKind : uint8; enum class ERideGrab : uint8; struct FSkateHostPad;

enum class ESkateMode : uint8 { Off, Ground, Air, Grind, Bail };

/** Skateboarding with skate.-style controls (README.md): the actor is the board, the ride runs in a custom movement mode
 *  of the game's movement component (its PhysCustom calls PhysSkate), tricks come from Flick-It on the right stick.
 *  The rider is an ACharacter that implements ISkateRider. */
UCLASS()
class ATELIERSKATE_API USkateComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    USkateComponent();
    /** The custom movement mode the ride runs in: the game's PhysCustom calls PhysSkate for it. */
    static constexpr uint8 MovementMode = 2;
    /** Character must implement ISkateRider. */
    void Initialize(ACharacter* Character);
    bool IsAvailable() const { return bAvailable; }
    /** On the board, including a bail (the component drives the character until they are back on it), or getting on
     *  or off it with the Ride backend (a mount or dismount clip drives the character). */
    bool IsRiding() const { return Mode != ESkateMode::Off || bRideClip; }
    ESkateMode GetMode() const { return Mode; }
    /** Get on (from standing or running) or off. */
    bool Toggle();
    /** The board button on foot with the Ride backend (RIDE.md, "Transitions"): a board dissolves into the hand, a
     *  held one is put away, a lying one dissolves and a fresh one comes to the hand. Not while the hands are busy
     *  (ISkateRider::CanCarrySkateBoard). Callable from scripts (Python: recall_board()). */
    UFUNCTION(BlueprintCallable, Category="Skate")
    void RecallBoard();
    /** On foot with the board in hand (the board-carry locomotion). */
    bool IsBoardInHand() const;
    void StowImmediately();
    void SetGoofy(bool bNewGoofy);
    bool IsGoofy() const { return bGoofy; }
    /** QA / live bridge: replace the player's controls; nullptr gives them back. */
    void SetScriptedInput(const FSkateInput* Input) { bScripted = Input != nullptr; if (Input) Scripted = *Input; }
    const FSkateInput& GetInput() const { return In; }
    /** The whole ride, called from the movement component's PhysCustom in the game's skate mode. */
    void PhysSkate(float Dt);
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    const TArray<FTransform>& GetRetailPose() const { return RetailPose; }
    /** The switches between the skate pose and the character's own that should be blended (FAnimNode_SkateRider):
     *  the count changes at each one, and the blend takes GetPoseBlendTime seconds (0: cut). */
    uint32 GetPoseBlendSerial() const { return PoseBlendSerial; }
    float GetPoseBlendTime() const { return PoseBlendTime; }
    /** A bail the player asked to leave on foot (the skate button during the bail): the settled body gets up with
     *  BeginGetUpOnFoot rather than back onto the board. */
    bool WantsGetUpOnFoot() const;
    /** The physical rider's get-up on foot, where the body lies (Ground, facing Yaw) with the board left lying. */
    void BeginGetUpOnFoot(const FVector& Ground, float Yaw, bool bFaceUp);
    FString GetRetailState() const;
    /** QA: a bone of the shown ride pose in the world under the Ride backend's Native solver (the hybrid; Native's
     *  skeleton names, as SKATEBOARD_ROOT or HIPS). False without one: the Ride solver's pose is on its pose mesh. */
    UFUNCTION(BlueprintCallable, Category="Skate")
    bool GetRidePoseBone(FName Bone, FTransform& World) const;
    bool GetRetailCamera(FTransform& Out, float& FOV) const;
    virtual void TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick) override;
    /** Teleport the rider (and board) to a spot, stopped, on the board. */
    bool PlaceAt(const FVector& GroundPoint, float Yaw);
    /** QA: set the board's velocity (cm/s, world). */
    void Launch(const FVector& Velocity);

    uint32 GetSerial() const { return Serial; }
    FTransform GetDeckWorld() const;
    bool IsOnBoard() const { return Mode==ESkateMode::Ground || Mode==ESkateMode::Air || Mode==ESkateMode::Grind; }

    // HUD
    FString GetComboLine() const { return ShownCombo; }
    float GetComboAlpha() const;
    int32 GetScore() const { return Score; }
    FString GetStatus() const;
    float GetSpeed() const { return Vel.Size(); }
    /** The yaw the chase camera should follow, when there is a clear direction of travel. */
    bool GetCameraYaw(float& Yaw) const;
    FString GetDebug() const;
    /** "volume pitch" pairs for the roll, grind, slide, skid and scrape loops (films mix them offline). */
    FString GetLoopState() const;

    // QA
    FName GetLastTrick() const { return LastTrickName; }
    int32 GetLandedCount() const { return Landed; }
    int32 GetBailCount() const { return Bails; }
    int32 GetGrindCount() const { return Grinds; }
    FVector GetBoardVelocity() const { return Vel; }
    bool IsFakie() const { return bFakie; }
    bool IsManual() const { return bManual; }

private:
    UPROPERTY() TObjectPtr<ACharacter> Rider;
    ISkateRider* RiderApi = nullptr;
    UPROPERTY() TObjectPtr<USceneComponent> BoardRoot;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Deck;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Trucks;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Wheels;
    UPROPERTY() TObjectPtr<USkateRailSubsystem> RailSystem;
    // Sounds (USkateSettings::SoundFolder): board-attached loops and one-shot variants.
    UPROPERTY() TArray<TObjectPtr<UAudioComponent>> Loops;      // roll, grind, slide, skid, scrape
    UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
    UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
    TMap<FName, FIntPoint> CueRange;                              // first wave index, count
    float LoopVolume[5] = {0.f, 0.f, 0.f, 0.f, 0.f};
    int32 LastVariant = -1;
    void LoadSounds();
    void PlayCue(FName Cue, float Volume, float Pitch = 1.f);
    void UpdateAudio(float Dt);
    bool bAvailable=false, bGoofy=false, bScripted=false;
    ESkateMode Mode=ESkateMode::Off;
    FSkateInput In,Scripted;
    TSharedPtr<FSkateRuntime> RetailRuntime;
    bool bRetailActive=false;
    TArray<FTransform> RetailPose;
    float BailVisualLift=0.f,RetailFloorClearance=0.f;
    bool bRetailPreloaded=false;
    bool LaunchNativeSession(TSharedPtr<FSkateRuntime>& Into, const FVector& Where, float Yaw, FString& Failure);
    /** Place a Native session at the ride's start (Pos, Rot, Vel), refreshing its collision first if needed. */
    bool ActivateNative(FSkateRuntime& Runtime);
    /** Step a Native session one frame (neutral controls if bNeutral): whether a new pose arrived. */
    bool StepNative(FSkateRuntime& Runtime, float Dt, bool bNeutral, bool& bFailed);
    /** Under the hybrid: count the air's spin from the shown pose and name it at the landing (Native names none). */
    void NameNativeSpin(ESkateMode Was);
    /** Keep a Native session's world around At (the ride's position, or the rider's on foot when bIdle). */
    void RefreshNativeCollision(FSkateRuntime& Runtime, const FVector& At, float Yaw, bool bIdle);
    void PreloadRetailRuntime();
    void PollIdleRetail();
    bool StartRetailRuntime();
    void SuspendRetailRuntime();
    void StepRetailRuntime(float Dt);
    void LaunchRetail(const FVector& V);
    void ConfigureRetail();
    void RetargetRetailPose();
    /** The visible board's growth about the ground contact Pos (ISkateRider::GetSkateBoardScale). */
    float BoardScale() const;
    FTransform BoardGrowth() const;
    void RuntimeFailure(const FString& Message);
    void ResetInput();
    FVector2D MouseStick=FVector2D::ZeroVector;
    float MouseQuiet=0; bool bMouseSwiped=false;
    float SpaceHeld=-1.f,SpaceRelease=-1.f;
    FVector Pos=FVector::ZeroVector,Vel=FVector::ZeroVector;
    FQuat Rot=FQuat::Identity;
    float BodyLift=77.f,SavedRadius=30.f,SavedHalf=74.f,SavedStep=45.f;
    FVector SavedMeshLocation=FVector::ZeroVector;
    FQuat SavedMeshRotation=FQuat::Identity;
    bool bFakie=false,bManual=false,bNoseManual=false,bPowerslide=false,bBraking=false,bPushing=false,bSlide=false;
    float SlideAngle=0,RailSpeed=0,ComboFade=0;
    uint32 Serial=0;
    int32 Score=0,Landed=0,Bails=0,Grinds=0;
    FString ShownCombo;
    FName LastTrickName;
    UCharacterMovementComponent* Movement() const;
    FVector Up() const { return Rot.GetUpVector(); }
    FVector Forward() const { return Rot.GetForwardVector(); }
    void ReadInput(float Dt);
    /** The host's half of the canonical pad (Private/SkatePad.h) that both backends sample: In, whether the board is
     *  rolling, and the buttons and analog triggers of the player's controller when it drives the ride. */
    FSkateHostPad ReadHostPad() const;
    void SetMeshForRiding(bool bRiding);
    FQuat AlignUp(const FQuat& Q,const FVector& NewUp,float Alpha) const;

    // The Ride backend (USkateSettings::Backend; Private/Ride, RIDE.md). It publishes through RetailRuntime's outputs,
    // so everything after the step (modes, cues, board placement, retargeting) is shared with the native backend.
    TSharedPtr<FRideSession> Ride;
    // The rider's bodies: an active ragdoll while riding (skate.RidePhysical), the bail's ragdoll and loose board, and
    // the get-up from where the body lies.
    UPROPERTY() TObjectPtr<URidePhysicalRider> PhysicalRider;
    bool StartRide();
    bool StepRide(float Dt);
    void AfterRideFrame(float Dt);
    void StopRide();
    void PreloadRide();
    void GetUpFromBody();
    // The Ride backend's riding solver (skate.RideSolver): Native's session rides (the board, its controls, tricks,
    // airs, grinds, bail rules and pose) and Ride keeps the rest: the body (the physical rider follows the retargeted
    // pose), the transitions, the bails (a Native wipeout hands the rider to the Chaos body) and the get-up where the
    // body lies. RideNative is that session, kept apart from RetailRuntime (what the rider shows), so a transition clip
    // published between rides never ends it. Ride's own board model (FRideSession) still animates the transitions.
    static bool RideSolverIsNative();
    TSharedPtr<FSkateRuntime> RideNative;
    bool bRideNative = false;                  // the current ride's solver is Native
    bool bNativeBail = false;                  // a Native wipeout handed to the body: the body falls
    FVector RideSpin = FVector::ZeroVector;    // the Native deck's angular velocity (rad/s, world)
    // Through the body's bail the session goes on with its wipeout (controls neutral) and the loose board is placed on
    // Native's board (skate.BailNativeBoard): it rolls on and catches on edges as on the Native backend.
    bool bNativeBoardInBail = false;
    FTransform NativeBoardLast = FTransform::Identity;   // the board placed last, and its motion (cm/s, rad/s)
    FVector NativeBoardVelocity = FVector::ZeroVector, NativeBoardSpin = FVector::ZeroVector;
    float NativeBoardSince = 0.f;                       // seconds since it was placed
    bool StartNativeRide();
    void SuspendNativeRide();
    void RelaunchNativeRide();
    void BeginNativeBoardInBail();
    void FollowNativeBoardInBail(float Dt);
    void EndNativeBoardInBail();
    void AfterNativeRideFrame(float Dt);
    void GetUpFromNativeBail();
    /** The ride's root: Native's under the Ride body, otherwise the Ride session's. */
    FTransform RideRoot() const;
    // The bail's velocity and spin, and whether the rider rides switch: the solver's own (Native's under the hybrid).
    FVector BailVelocity() const;
    FVector BailSpin() const;
    bool RideSwitched() const;
    // The grab held in the air (an air dismount steps off from it): Native's, from the trick line and the triggers.
    ERideGrab RideGrab() const;
    // The stance the state reports: Native's own under the hybrid.
    bool ShownFakie() const;
    bool ShownSwitch() const;

    // Getting on and off with the Ride backend (Private/Ride/RideTransition.cpp, RIDE.md "Transitions"): one
    // continuous character. The actor never jumps, the capsule changes about its centre, the mesh keeps its world
    // place across each switch and eases back to its on-foot offset, the pose switch is inertialized and the speed
    // carries over both ways; the board dissolves in and out rather than popping.
    TSharedPtr<FRideTransition> Transition;
    bool bRideBody=false;                                      // the current or last ride used the Ride backend
    bool bRideClip=false;                                      // a mount or dismount clip drives the character (IsRiding)
    // The off-board pose (carry, mount, dismount clips through FRideSession::StepOffBoard) published by
    // PublishOffBoardPose through RetargetRetailPose: the visible deck follows the clip's board, on the ground or in
    // the hand (OffBoardDeck, scaled), and the body rises onto a bigger deck by OffBoardLift.
    bool bOffBoardPose=false;
    float OffBoardLift=0.f;
    FTransform OffBoardDeck=FTransform::Identity;
    // The visible deck eases from where it was (in the hand of the character's own pose) onto the clip's board.
    FTransform OffBoardDeckFrom=FTransform::Identity;
    float OffBoardDeckBlend=1.f;
    /** bPlaceBoard: the visible board goes where the clip has it (false: it stays where it is, lying or kicked away). */
    bool PublishOffBoardPose(float Lift, bool bPlaceBoard = true);
    /** Place the visible board's parts from a source board (the published one, RetailRuntime's, by default), its deck
     *  at DeckWorldScaled. */
    void PlaceBoardParts(const FTransform& DeckWorldScaled, const FSkateRuntime* Source = nullptr);
    uint32 PoseBlendSerial=0;
    float PoseBlendTime=0.f;
    float PendingPoseBlend=0.f;        // a blend for the pose the ride publishes next (RequestPoseBlendWithNextPose)
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> BoardFade;  // USkateSettings::BoardDissolveMaterial, shared by the parts
    bool bBoardFadeTried = false;                                 // looked up once (LoadBoardFade): a missing one is not looked for every frame
    FRideTransition& Transit();
    void RequestPoseBlend(float Seconds) { ++PoseBlendSerial; PoseBlendTime=Seconds; PendingPoseBlend=0.f; }
    /** The blend for a pose not published yet (the ride's first, after the pose shown is held a frame): asked where
     *  RetargetRetailPose writes it, so the character's graph reads the request and the pose together. */
    void RequestPoseBlendWithNextPose(float Seconds) { PendingPoseBlend=Seconds; }
    bool RideMount(bool bInstant);
    bool RideDismount();
    void LeaveBoard();
    bool GetOnBoard(const FVector& Ground, const FQuat& Rotation, const FVector& Velocity, float Blend);
    bool StandUpOffBoard(float Yaw, bool bMayStand = true);
    bool PrepareRideClips();
    bool BeginMountClip();
    bool BeginDismountClip();
    void StepRideClip(float Dt);
    void FinishRideClip();
    void EndRideClip(bool bKeepDrive = false);
    void BeginCarry(float Phase);
    void StepCarry(float Dt);
    void PutBoardAway();
    FVector OffBoardGround() const;
    float FeetPhase(bool bMirror) const;
    void TrackFeet(float Dt);
    void HoldBoardAtHand();
    void ReleaseBoardFromHand();
    void UseWorldBoard();
    void SetDrive(const FVector& Velocity);
    void StopDrive();
    /** Off the board at Velocity (flat): the drive holds it for one more move, then ReleaseDrive. */
    void HoldDriveForInput(const FVector& Velocity);
    /** The held speed split by the stick now given: the character's own (as far as it may run), the rest momentum. */
    void ReleaseDrive();
    bool BeginAirMountClip();
    bool BeginAirDismountClip();
    bool BeginCarryJump(float Speed);
    bool BeginLandClip();
    bool StartClip(UAnimSequence* Clip, ERideFoot Foot, bool bMirror, float Yaw, float BlendIn);
    void AnchorClipAt(FName Bone, const FVector& World);
    bool MatchPelvis();
    float ClipPhase(const UAnimSequence* Clip, float Time, bool bMirror) const;
    float AirTimeLeft(float* Height = nullptr) const;
    void TickTransition(float Dt);
    /** skate.RideTrace: a line a frame about each switch (the actor, the mesh, the pelvis published and shown). */
    void TraceTransition();
    void ResetTransition();
    /** While the skate pose shows, the character's anim instance takes no root motion (its own mode comes back with
     *  its own pose): with root motion from everything CharacterMovement updates the graph before the ride steps and
     *  publishes, and the character would show each skate pose a frame late, behind its board. */
    void SyncRootMotion();
    void ReleaseRootMotion();          // gives the held instance its own mode back
    TWeakObjectPtr<UAnimInstance> RootMotionAnim;   // the instance whose mode is held
    bool bRootMotionHeld=false;
    uint8 SavedRootMotionMode=0;      // ERootMotionMode::Type
    void ShowBoard(float Target, bool bInstant);
    void ApplyBoardShown();
    void LoadBoardFade();
    void SetMeshOffset(const FVector& Offset, const FQuat& Turn);
    /** The mesh's offset and turn that keep it at MeshWorld under the actor as it is now. */
    void KeepMeshWorld(const FTransform& MeshWorld);
    /** Turn the actor upright to Yaw, the mesh keeping its world place and easing back onto the capsule. */
    void TurnActor(float Yaw);
    // Bails left on foot, a board kicked away, a lying board stepped onto.
    /** URidePhysicalRider::OnBailStart: a run-out is taken on foot (RUNOUT_*, after the ride's frame). */
    bool TakeRunOut(ERideBailKind Kind);
    bool BeginRunOut();
    bool BeginRecover();
    bool BeginStepOnClip();
    /** The board leaves the clip (kicked away, or rolling on after a run-out): it flies or rolls on by itself as a
     *  projectile, or settles where it is when it barely moves. */
    void LaunchBoard();
    void StepLooseBoard(float Dt);
    void SettleBoard();
    /** A clip that ends without the board in hand: the character's own pose and movement take over. */
    void EndOnFoot(float Blend);
    void StartMomentum(const FVector& Excess);
    void StopMomentum();
    void DropLyingBoard();
    /** For GetDebug (QA): the board, the body's hips and the character's speed. */
    FString DescribeTransition() const;
};
