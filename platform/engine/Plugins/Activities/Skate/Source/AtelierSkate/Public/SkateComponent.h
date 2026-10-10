#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SkateInput.h"
#include "SkateFeel.h"
#include "SkateSettings.h"
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
class FRideClipPlayer;
class UBoxComponent;
class UPhysicsAsset;
class URidePhysicalRider;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UAnimInstance;
struct FRideTransition; enum class ERideFoot : uint8; enum class ERideBailKind : uint8; enum class ERideGrab : uint8; struct FSkateHostPad;
class FSkatePadReader;

/** The controller's sticks as ReadInput read them in a frame, for the 120 Hz flick reading (FSkateFeel::Flick120Hz) to
 *  read the off-thread readings (Private/SkatePadReader.h) the same way. Valid only when the player's controller drove
 *  the frame. */
struct FSkateFrameSticks
{
    bool bValid = false;
    double Time = 0;                      // FPlatformTime::Seconds when ReadInput ran
    float Raw[4] = {};                    // the engine's raw axes, LeftX LeftY RightX RightY (the viewport negates RightY)
    float DeadZone[4] = {}, Exponent[4] = {1, 1, 1, 1}, Scale[4] = {1, 1, 1, 1};   // each axis's UPlayerInput massage
    float KeysX = 0;                      // the arrow and A/D keys on the left stick
    FVector2D Mouse = FVector2D::ZeroVector, Keys = FVector2D::ZeroVector;   // the mouse's and the space bar's right stick
};

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
    /** Visual-only peer: no simulation preload, input, physics bodies or local rider simulation. */
    void InitializeNetworkProxy(ACharacter* Character);
    bool ApplyNetworkPose(const TArray<FTransform>& ComponentPose, const FTransform& MeshWorld);
    void ClearNetworkPose();
    void ApplyNetworkBoard(const FTransform& DeckWorld, float Shown);
    void SilenceNetworkAudio(float Dt);
    void ApplyNetworkAudio(uint8 InMode, uint8 InSurface, uint8 Flags, const FVector& Velocity, float Dt);
    uint8 GetNetworkSurface() const { return uint8(Surface); }
    uint8 GetNetworkAudioFlags() const { return (bPowerslide ? 1 : 0) | (bBraking ? 2 : 0) | (bSlide ? 4 : 0); }
    float GetBoardShown() const;
    bool IsNetworkProxy() const { return bNetworkProxy; }
    bool IsAvailable() const { return bAvailable; }
    /** On the board, including a bail (the component drives the character until they are back on it), or getting on
     *  or off it (a mount or dismount clip drives the character). */
    bool IsRiding() const { return Mode != ESkateMode::Off || bRideClip; }
    ESkateMode GetMode() const { return Mode; }
    /** Get on (from standing or running) or off. */
    bool Toggle();
    /** The board button on foot (RIDE.md, "Transitions"): a board dissolves into the hand, a
     *  held one is put away, a lying one dissolves and a fresh one comes to the hand. Not while the hands are busy
     *  (ISkateRider::CanCarrySkateBoard). Callable from scripts (Python: recall_board()). */
    UFUNCTION(BlueprintCallable, Category="Skate")
    void RecallBoard();
    /** On foot: whether the character's own move (a sprint, a dash, a double jump...) may take
     *  over from the board now. Not riding or getting on; a clip on foot once the stick may end it (a jump with the
     *  board in hand at once). Without a board or a clip, always. */
    bool CanYieldToCharacter() const;
    /** Gives the character its own control back for such a move: a clip ends where it is, a board in hand is put away
     *  as the board button puts it (dissolving in the hand), one the clip had flies or rolls on, a lying one stays.
     *  bOwnVelocity: the move sets the velocity itself (else the speed carries on as the stick's). False when it may
     *  not (CanYieldToCharacter). */
    UFUNCTION(BlueprintCallable, Category="Skate")
    bool YieldToCharacter(bool bOwnVelocity);
    void StowImmediately();
    void SetGoofy(bool bNewGoofy);
    bool IsGoofy() const { return bGoofy; }
    /** The player's skating feel (SkateFeel.h): applied at once while riding, and to every later ride. False (with the
     *  reason) when a value is out of its range; the feel then stays as it was. */
    bool SetFeel(const FSkateFeel& NewFeel, FString& Error);
    /** QA / live bridge: replace the player's controls; nullptr gives them back. */
    void SetScriptedInput(const FSkateInput* Input) { bScripted = Input != nullptr; if (Input) Scripted = *Input; }
    /** The whole ride, called from the movement component's PhysCustom in the game's skate mode. */
    void PhysSkate(float Dt);
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    const TArray<FTransform>& GetRiderPose() const { return RiderPose; }
    /** The switches between the skate pose and the character's own that should be blended (FAnimNode_SkateRider):
     *  the count changes at each one, and the blend takes GetPoseBlendTime seconds (0: cut). */
    uint32 GetPoseBlendSerial() const { return PoseBlendSerial; }
    float GetPoseBlendTime() const { return PoseBlendTime; }
    /** A bail the player asked to leave on foot (the skate button during the bail): the settled body gets up with
     *  BeginGetUpOnFoot rather than back onto the board. */
    bool WantsGetUpOnFoot() const;
    /** The physical rider's get-up on foot, where the body lies, with the board left lying. */
    void BeginGetUpOnFoot(bool bFaceUp);
    FString GetSimulationState() const;
    bool GetSimulationCamera(FTransform& Out, float& FOV) const;
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
    /** "volume pitch" pairs for the roll, grind, slide, skid and scrape loops, then the surfaces' own rolls (wood, metal,
     *  asphalt, stone, dirt, grass, sand; see ESkateSurface) (films mix them offline). */
    FString GetLoopState() const;

    // QA
    FName GetLastTrick() const { return LastTrickName; }
    int32 GetLandedCount() const { return Landed; }
    int32 GetBailCount() const { return Bails; }
    int32 GetGrindCount() const { return Grinds; }
    FVector GetBoardVelocity() const { return Vel; }

private:
    UPROPERTY() TObjectPtr<ACharacter> Rider;
    ISkateRider* RiderApi = nullptr;
    UPROPERTY() TObjectPtr<USceneComponent> BoardRoot;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Deck;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Trucks;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Wheels;
    UPROPERTY() TObjectPtr<USkateRailSubsystem> RailSystem;
    // Sounds (USkateSettings::SoundFolder): board-attached loops and one-shot variants.
    UPROPERTY() TArray<TObjectPtr<UAudioComponent>> Loops;      // roll, grind, slide, skid, scrape, then roll_<surface>
    UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
    UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
    TMap<FName, FIntPoint> CueRange;                              // first wave index, count
    TArray<float> LoopVolume;
    ESkateSurface Surface = ESkateSurface::None;
    int32 LastVariant = -1;
    void LoadSounds();
    void PlayCue(FName Cue, float Volume, float Pitch = 1.f);
    /** Cue's bank for the surface under the board (land_wood), else Cue's. */
    void PlaySurfaceCue(FName Cue, float Volume, float Pitch = 1.f);
    static const TArray<const TCHAR*> SurfaceRolls;
    void UpdateAudio(float Dt);
    bool bNetworkProxy = false;
    ESkateMode NetworkAudioMode = ESkateMode::Off;
    bool bAvailable=false, bGoofy=false, bScripted=false;
    FSkateFeel Feel;                 // FSkateFeel::Defaults() at Initialize unless SetFeel came first
    bool bFeelSet=false;
    ESkateMode Mode=ESkateMode::Off;
    FSkateInput In,Scripted;
    TSharedPtr<FSkateRuntime> ShownRuntime;
    bool bSimulationActive=false;
    TArray<FTransform> RiderPose;
    float BailVisualLift=0.f,ShownFloorClearance=0.f;
    bool bSimulationPreloaded=false;
    bool LaunchSimulationSession(TSharedPtr<FSkateRuntime>& Into, const FVector& Where, float Yaw, FString& Failure);
    /** Place a simulation session at the ride's start (Pos, Rot, Vel), refreshing its collision first if needed. */
    bool ActivateSimulation(FSkateRuntime& Runtime);
    /** Step a simulation session one frame (neutral controls if bNeutral): whether a new pose arrived. */
    bool StepSimulation(FSkateRuntime& Runtime, float Dt, bool bNeutral, bool& bFailed);
    /** Count the air's spin from the shown pose and name it at the landing (the simulation names none). */
    void NameSimulationSpin(ESkateMode Was);
    /** Show each successful pump the simulation's session counted in the trick line (the simulation names none). */
    void NameSimulationPump();
    /** Keep a simulation session's world around At (the ride's position, or the rider's on foot when bIdle). */
    void RefreshSimulationCollision(FSkateRuntime& Runtime, const FVector& At, float Yaw, bool bIdle);
    void PreloadSimulation();
    void PollIdleSimulation();
    bool StartSimulation();
    void SuspendSimulation();
    void TickSimulation(float Dt);
    void LaunchSimulation(const FVector& V);
    void ConfigureSimulation();
    void RetargetRiderPose();
    /** The visible board's growth about the ground contact Pos (ISkateRider::GetSkateBoardScale). */
    float BoardScale() const;
    FTransform BoardGrowth() const;
    void RuntimeFailure(const FString& Message);
    void ResetInput();
    FVector2D MouseStick=FVector2D::ZeroVector;
    FSkateFrameSticks FrameSticks;
    TSharedPtr<FSkatePadReader> PadReader;   // while the feel reads flicks at 120 Hz (SkateRuntime.cpp)
    /** Runtime's readings for its next step, of Dt, of the sticks since its last (FSkateFeel::Flick120Hz), converted as
     *  ReadInput converts the frame's into Pad; none (the step reads the packet) unless the reader's agree with it. */
    void ReadFineSticks(FSkateRuntime& Runtime, float Dt, const FSkateHostPad& Pad);
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
    /** The host's half of the canonical pad (Private/SkatePad.h) that the session samples: In, whether the board is
     *  rolling, and the buttons and analog triggers of the player's controller when it drives the ride. */
    FSkateHostPad ReadHostPad() const;
    void SetMeshForRiding();
    FQuat AlignUp(const FQuat& Q,const FVector& NewUp,float Alpha) const;

    // Ride (Private/Ride, RIDE.md): the simulation's session rides (the board, its
    // controls, tricks, airs, grinds, bail rules and pose) and Ride keeps the rest: the body (the physical rider follows
    // the retargeted pose), the transitions, the bails (a simulation wipeout hands the rider to the Chaos body) and the
    // get-up where the body lies. RideSimulation is that session, kept apart from ShownRuntime (what the rider shows), so a
    // transition clip published between rides never ends it. Clips plays the transitions' clips on the simulation rig.
    TSharedPtr<FRideClipPlayer> Clips;
    // The rider's bodies: an active ragdoll while riding (skate.RidePhysical), the bail's ragdoll and loose board, and
    // the get-up from where the body lies.
    UPROPERTY() TObjectPtr<URidePhysicalRider> PhysicalRider;
    bool StartRide();
    /** Pos onto the floor under the board (or out of one it starts a little inside) for the simulation's session to start on. */
    void SettleRideStart();
    void StopRide();
    void PreloadRide();
    TSharedPtr<FSkateRuntime> RideSimulation;
    bool bSimulationBail = false;                  // a simulation wipeout handed to the body: the body falls
    FVector RideSpin = FVector::ZeroVector;    // the simulation deck's angular velocity (rad/s, world)
    // Through the body's bail the session goes on with its wipeout (controls neutral) and the loose board is placed on
    // the simulation's board, so it rolls on and catches on edges.
    bool bSimulationBoardInBail = false;
    FTransform SimulationBoardLast = FTransform::Identity;   // the board placed last, and its motion (cm/s, rad/s)
    FVector SimulationBoardVelocity = FVector::ZeroVector, SimulationBoardSpin = FVector::ZeroVector;
    float SimulationBoardSince = 0.f;                       // seconds since it was placed
    bool StartSimulationRide();
    void SuspendSimulationRide();
    void RelaunchSimulationRide();
    void BeginSimulationBoardInBail();
    void FollowSimulationBoardInBail(float Dt);
    void EndSimulationBoardInBail();
    void AfterSimulationRideFrame(float Dt);
    void GetUpFromSimulationBail();
    // The simulation's rider off the board on foot (its Biped states) becomes the character once that outlasts the frames a
    // wipeout passes through it: the session ends, the board rolls on by itself.
    float SimulationOnFootTime = 0.f;                        // seconds in BipedGround, and the rider's root and motion there
    FVector SimulationOnFootRoot = FVector::ZeroVector, SimulationOnFootVelocity = FVector::ZeroVector;
    bool IsSimulationOnFoot() const;
    bool TakeSimulationOnFoot(float Dt);
    // The simulation's session state starts with Prefix (FSkateRuntime lives in SkateRuntime.cpp).
    bool SimulationStateStarts(const TCHAR* Prefix) const;
    /** The ride's root: the simulation's. */
    FTransform RideRoot() const;
    // The bail's velocity and spin: the simulation's board's.
    FVector BailVelocity() const;
    FVector BailSpin() const;
    // The grab held in the air (an air dismount steps off from it): the simulation's, from the trick line and the triggers.
    ERideGrab RideGrab() const;
    // The stance the state reports: the simulation's own.
    bool ShownFakie() const;
    bool ShownSwitch() const;
    // The rider crouched on the board (the simulation's hips low over the deck): the dismount, run-out and kick-out clips' LO.
    bool ShownCrouch() const;

    // Getting on and off (Private/Ride/RideTransition.cpp, RIDE.md "Transitions"): one
    // continuous character. The actor never jumps, the capsule changes about its centre, the mesh keeps its world
    // place across each switch and eases back to its on-foot offset, the pose switch is inertialized and the speed
    // carries over both ways; the board dissolves in and out rather than popping.
    TSharedPtr<FRideTransition> Transition;
    bool bRideClip=false;                                      // a mount or dismount clip drives the character (IsRiding)
    // The off-board pose (carry, mount, dismount clips through FRideClipPlayer::Step) published by
    // PublishOffBoardPose through RetargetRiderPose: the visible deck follows the clip's board, on the ground or in
    // the hand (OffBoardDeck, scaled), and the body rises onto a bigger deck by OffBoardLift.
    bool bOffBoardPose=false;
    float OffBoardLift=0.f;
    FTransform OffBoardDeck=FTransform::Identity;
    // The visible deck eases from where it was (in the hand of the character's own pose) onto the clip's board.
    FTransform OffBoardDeckFrom=FTransform::Identity;
    float OffBoardDeckBlend=1.f;
    /** bPlaceBoard: the visible board goes where the clip has it (false: it stays where it is, lying or kicked away). */
    bool PublishOffBoardPose(float Lift, bool bPlaceBoard = true);
    /** Place the visible board's parts from a source board (the published one, ShownRuntime's, by default), its deck
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
     *  RetargetRiderPose writes it, so the character's graph reads the request and the pose together. */
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
    /** The share of the clip after which it gives way to the stick (and to the character's own moves). */
    float ClipFreeFrom() const;
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
