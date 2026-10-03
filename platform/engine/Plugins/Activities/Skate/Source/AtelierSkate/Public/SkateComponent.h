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
    /** On the board, including a bail (the component drives the character until they are back on it). */
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
    /** The whole ride, called from the movement component's PhysCustom in the game's skate mode. */
    void PhysSkate(float Dt);
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    const TArray<FTransform>& GetRetailPose() const { return RetailPose; }
    FString GetRetailState() const;
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
    bool LaunchNativeSession(const FVector& Where, float Yaw, FString& Failure);
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
    void SetMeshForRiding(bool bRiding);
    FQuat AlignUp(const FQuat& Q,const FVector& NewUp,float Alpha) const;

    // The Ride backend (USkateSettings::Backend; Private/Ride, RIDE.md). It publishes through RetailRuntime's outputs,
    // so everything after the step (modes, cues, board placement, retargeting) is shared with the native backend.
    TSharedPtr<FRideSession> Ride;
    UPROPERTY() TObjectPtr<UBoxComponent> LooseBoard;          // the board tumbling on its own during a bail
    UPROPERTY() TObjectPtr<UPhysicsAsset> RagdollAsset;        // built from the rider's skeleton when it has none
    bool bOwnPhysicsAsset=false;                               // the ragdoll uses the rider's own physics asset
    FName SavedMeshProfile;
    bool bRagdoll=false;
    float RagdollTime=0.f,RagdollQuiet=0.f,GetUpBlend=-1.f;    // GetUpBlend >= 0: the body blends from physics to the pose
    FVector RagdollStart=FVector::ZeroVector,RagdollFloor=FVector::ZeroVector;
    float RagdollLimit=2500.f;                                 // a body faster than this has gone unstable (cm/s)
    // Worlds built for the board's sweeps are often query-only; the surfaces near a fallen body are made physical
    // while it lies there, then put back.
    TArray<TWeakObjectPtr<UPrimitiveComponent>> MadePhysical;
    FVector PhysicalCentre=FVector::ZeroVector;
    void MakeWorldPhysical(const FVector& Centre);
    void RestoreWorld();
    bool StartRide();
    bool StepRide(float Dt);
    void AfterRideFrame(float Dt);
    void StopRide();
    void PreloadRide();
    bool StartRagdoll();
    void UpdateRagdoll(float Dt);
    void EndRagdoll();
    UPhysicsAsset* BuildRagdollAsset();
};
