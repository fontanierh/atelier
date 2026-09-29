#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SkateFlick.h"
#include "SkateComponent.generated.h"

class AWandererCharacter;
class UStaticMeshComponent;
class USceneComponent;
class UAnimSequence;
class USkateRailSubsystem;
class UCharacterMovementComponent;
class UAudioComponent;
class USoundWave;
class USoundAttenuation;

enum class ESkateMode : uint8 { Off, Ground, Air, Grind, Bail };

/** Skateboarding with skate.-style controls (docs/SKATE.md): the actor is the board, the ride runs in the custom movement
 *  mode 2 of UJapanCharacterMovement, tricks come from Flick-It on the right stick. */
UCLASS()
class YORIMICHI_API USkateComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    USkateComponent();
    void Initialize(AWandererCharacter* Character);
    bool IsAvailable() const { return bAvailable; }
    /** On the board, including a bail (the component drives the character until he is back on it). */
    bool IsRiding() const { return Mode != ESkateMode::Off; }
    ESkateMode GetMode() const { return Mode; }
    /** Get on (from standing or running) or off. */
    bool Toggle();
    void StowImmediately();
    void SetGoofy(bool bNewGoofy);
    bool IsGoofy() const { return bGoofy; }
    /** QA / live bridge: replace the player's controls; nullptr gives them back. */
    void SetScriptedInput(const FSkateInput* Input) { bScripted = Input != nullptr; if (Input) Scripted = *Input; }
    const FSkateInput& GetInput() const { return In; }
    /** UJapanCharacterMovement::PhysCustom, custom mode 2: the whole ride. */
    void PhysSkate(float Dt);
    virtual void TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick) override;
    /** Teleport the rider (and board) to a spot, stopped, on the board. */
    bool PlaceAt(const FVector& GroundPoint, float Yaw);
    /** QA: set the board's velocity (cm/s, world). */
    void Launch(const FVector& Velocity);

    // Animation
    FName GetClipName() const { return ClipName; }
    float GetClipTime() const { return ClipTime; }
    bool IsClipLooping() const { return bClipLoops; }
    uint32 GetSerial() const { return Serial; }
    float GetBlendTime() const { return ClipBlend; }
    UAnimSequence* GetSequence() const { return FindClip(ClipName, bClipSwitch); }
    /** bSwitch: the other stance's copy (pushing fakie is a switch push, the other foot on the ground). */
    UAnimSequence* FindClip(FName Name, bool bSwitch = false) const;
    float GetCrouch() const { return CrouchAlpha; }
    /** -1 heel side .. +1 toe side. */
    float GetLean() const { return LeanAlpha; }
    /** Deck frames (centre of the deck top; X nose, Z up) now and where the clips assume the deck. */
    FTransform GetDeckWorld() const;
    FTransform GetDeckRestWorld() const;
    /** The deck as the rider's feet follow it: pop pitch, manual and carve lean, but not a flip trick's roll and shove
     *  (the feet leave the board for those; carrying them round with it twisted the legs). */
    FTransform GetDeckCarryWorld() const;
    /** How much each limb holds the board (0 foot_L, 1 foot_R, 2 hand_L, 3 hand_R), from the clip contacts. */
    float GetLimbContact(int32 Limb) const { return Limb >= 0 && Limb < 4 ? Contact[Limb] : 0.f; }
    bool IsOnBoard() const { return Mode == ESkateMode::Ground || Mode == ESkateMode::Air || Mode == ESkateMode::Grind; }

    // HUD
    FString GetComboLine() const;
    float GetComboAlpha() const;
    int32 GetScore() const { return Score; }
    bool ShowBalance() const { return bManual || Mode == ESkateMode::Grind; }
    float GetBalance() const { return Balance; }
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
    FString GetLastFlick() const { return Flick.LastDebug; }
    FVector GetBoardVelocity() const { return Vel; }
    bool IsFakie() const { return bFakie; }
    bool IsManual() const { return bManual; }

private:
    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY() TObjectPtr<USceneComponent> BoardRoot;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Deck;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Trucks;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Wheels;
    UPROPERTY() TObjectPtr<USkateRailSubsystem> RailSystem;
    // Sounds (japan/audio/skate via Scripts/import_skate_audio.py): board-attached loops and one-shot variants.
    UPROPERTY() TArray<TObjectPtr<UAudioComponent>> Loops;      // roll, grind, slide, skid, scrape
    UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
    UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
    TMap<FName, FIntPoint> CueRange;                              // first wave index, count
    float LoopVolume[5] = {0.f, 0.f, 0.f, 0.f, 0.f};
    int32 LastVariant = -1;
    void LoadSounds();
    void PlayCue(FName Cue, float Volume, float Pitch = 1.f);
    void UpdateAudio(float Dt);
    bool bCaught = false;

    bool bAvailable = false, bGoofy = false, bScripted = false;
    ESkateMode Mode = ESkateMode::Off;
    FSkateInput In, Scripted, Previous;
    FSkateFlick Flick;
    FVector2D MouseStick = FVector2D::ZeroVector;
    // The mouse stick springs back to the centre a moment after a flick it made (not after the load's pull).
    float MouseQuiet = 0.f; bool bMouseSwiped = false, bMouseRight = false;
    float MousePower = -1.f;
    float SpaceHeld = -1.f, SpaceRelease = -1.f;

    // Board frame: Pos = ground point under the deck centre, Rot = X nose / Z up.
    FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
    FQuat Rot = FQuat::Identity;
    float BodyLift = 77.f;       // capsule centre above the board's ground point
    float SavedRadius = 30.f, SavedHalf = 74.f, SavedStep = 45.f;
    FVector SavedMeshLocation = FVector::ZeroVector;
    FQuat SavedMeshRotation = FQuat::Identity;

    // Ground
    bool bFakie = false, bManual = false, bNoseManual = false, bPowerslide = false, bBraking = false;
    float ManualHold = 0.f, SlideAngle = 0.f, SlideSign = 1.f;
    bool bManualLock = false;
    FVector SlideTravel = FVector::ForwardVector;
    bool bPushing = false, bPushAgain = false; float PushTime = 0.f, PushStroke = 0.f;
    float LandTime = 10.f, SinceGrounded = 0.f, GroundTime = 0.f;
    float Balance = 0.f, Drift = 0.f, DriftClock = 0.f;
    float ManualTilt = 0.f;   // degrees the board is tipped on its back (+) or front (-) wheels, eased
    float BumpCooldown = 0.f;
    float RevertLeft = 0.f, RevertSign = 1.f, DeckLean = 0.f;   // a revert still turning (degrees left); the carve's deck roll
    float SurfaceDrag = 1.f, SurfaceClock = 0.f;   // rolling resistance of what is under the wheels (1 smooth concrete)
    float ReadSurface() const;
    mutable FString SurfaceName;

    // Air
    FSkateTrick Trick;          // the board trick in progress (flips/shove)
    float TrickTime = 0.f, TrickDuration = 0.f, FlipsDone = 0.f;
    // This flick's part of the trick (an air flick adds a flip): it starts at TrickStart from FlipBase/ShoveBase turns;
    // the board turns after FlipDelay (the feet leave it first). CatchTime runs from the moment the board is caught.
    float TrickStart = 0.f, FlipBase = 0.f, ShoveBase = 0.f, CatchTime = 0.f;
    float TrickProgress() const { return TrickDuration > TrickStart ? FMath::Clamp((TrickTime - TrickStart) / (TrickDuration - TrickStart), 0.f, 1.f) : 1.f; }
    float FlipProgress() const;
    float AirTime = 0.f, SpinRate = 0.f, SpinTotal = 0.f, PopTime = 10.f, AirStuck = 0.f;
    bool bPopped = false, bNolliePop = false;
    FVector LandingNormal = FVector::UpVector;
    bool bVertAir = false; FVector VertNormal = FVector::UpVector, VertPoint = FVector::ZeroVector;
    int32 PredictClock = 0;
    FName Grab; float GrabTime = 0.f, GrabTotal = 0.f;
    bool bGrabHeldAtStart = false;
    bool bAirTrickAgain = false;

    // Grind
    int32 Rail = INDEX_NONE; float RailS = 0.f, RailSpeed = 0.f, RailDir = 1.f;
    FName GrindName; bool bSlide = false; float GrindYaw = 0.f, GrindPitch = 0.f, GrindTime = 0.f;
    FVector GrindPivot = FVector::ZeroVector;
    bool GrindFakie = false;
    float LeaveRailCooldown = 0.f;
    int32 LastRail = INDEX_NONE;

    // Bail
    float BailTime = 0.f, BailRoll = 0.f, SavedBraking = 2048.f, SavedFriction = 8.f;
    FVector BoardFreePos = FVector::ZeroVector, BoardFreeVel = FVector::ZeroVector, BoardFreeSpin = FVector::ZeroVector;
    FQuat BoardFreeRot = FQuat::Identity;

    // Animation
    FName ClipName; float ClipTime = 0.f, ClipBlend = .12f; bool bClipLoops = true, bClipSwitch = false; uint32 Serial = 0;
    FTransform DeckCarry;   // relative to the board root
    float CrouchAlpha = 0.f, LeanAlpha = 0.f, Contact[4] = {1.f, 1.f, 0.f, 0.f}, StanceClock = 0.f;
    float WheelAngle = 0.f, Steering = 0.f;
    TMap<FName, TArray<FVector4f>> ClipContacts;   // per clip: (limb, t0, t1, unused)

    // Score
    TArray<FString> Combo; int32 ComboPoints = 0, Score = 0; float ComboFade = 0.f, ComboIdle = 0.f; FString ShownCombo;
    FName LastTrickName; int32 Landed = 0, Bails = 0, Grinds = 0;
    FString AirName, AirWhy;
    mutable FString ProbeDebug;

    UCharacterMovementComponent* Movement() const;
    FVector Up() const { return Rot.GetUpVector(); }
    FVector Forward() const { return Rot.GetForwardVector(); }
    float StanceSign() const { return bGoofy ? -1.f : 1.f; }
    void ReadInput(float Dt);
    void Enter(ESkateMode Next);
    void StepGround(float H);
    void StepAir(float H);
    void StepGrind(float H);
    void StepBail(float H);
    bool ProbeGround(const FVector& At, const FQuat& Q, FVector& OutPoint, FVector& OutNormal, bool& bBlocked, float& LeadRise) const;
    bool MoveBody(FHitResult& Hit);
    void Pop(const FSkateTrick& Flicked, const FVector& Base, float Scale);
    void StartTrick(const FSkateTrick& Flicked);
    void TryLand(const FVector& Point, const FVector& Normal);
    bool TryGrind();
    void LeaveGrind(bool bPopOff, float SideKick);
    void StartBail(const TCHAR* Why);
    void EndBail();
    void AddCombo(const FString& Name, int32 Points);
    void EndCombo(bool bLanded);
    FString SpinName() const;
    void UpdateClip(float Dt);
    void UpdateBoard(float Dt);
    void LoadContacts();
    void SetMeshForRiding(bool bRiding);
    FQuat AlignUp(const FQuat& Q, const FVector& NewUp, float Alpha) const;
};
