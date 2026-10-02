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
class USkateProfile;
class USkateRuntimeAsset;
class USkateCollisionAsset;

UENUM(BlueprintType)
enum class ESkateMode : uint8 { Off, Ground, Air, Grind, Bail };

/** Preserve the outcome and failure message in Blueprint and Python callers. */
USTRUCT(BlueprintType)
struct ATELIERSKATE_API FSkateProfileChangeReport
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="Skate") bool bAccepted=false;
    UPROPERTY(BlueprintReadOnly, Category="Skate") FString Failure;
};

/** A copied diagnostic view. Blueprint callers never touch the native worker. */
USTRUCT(BlueprintType)
struct ATELIERSKATE_API FSkateRuntimeDiagnostics
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="Skate") bool bReady=false;
    UPROPERTY(BlueprintReadOnly, Category="Skate") bool bAwaitingPose=false;
    UPROPERTY(BlueprintReadOnly, Category="Skate") bool bBuildingCollision=false;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int64 NativeTick=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int64 PoseGeneration=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 PoseBones=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 CollisionTriangles=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 CollisionRails=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 CollisionRevision=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 CollisionRefreshes=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 MissingCollisionMeshes=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 MaterialOverrideTriangles=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") int32 SurfaceTriangles=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") float CollisionReachMetres=0;
    UPROPERTY(BlueprintReadOnly, Category="Skate") FString State;
    UPROPERTY(BlueprintReadOnly, Category="Skate") FString DataIdentity;
    UPROPERTY(BlueprintReadOnly, Category="Skate") FString LastError;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FSkateModeChanged, ESkateMode, Previous, ESkateMode, Current);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FSkateTrickChanged, FName, Trick, int32, Score);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FSkateContactEvent, FVector, BoardVelocity);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FSkateFailureEvent, const FString&, Message);

/** Skateboarding with skate.-style controls (README.md): the actor is the board, the ride runs in a custom movement mode
 *  of the game's movement component (its PhysCustom calls PhysSkate), tricks come from Flick-It on the right stick.
 *  The rider is an ACharacter that implements ISkateRider. */
UCLASS(BlueprintType, meta=(BlueprintSpawnableComponent))
class ATELIERSKATE_API USkateComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    USkateComponent();
    /** Set before Initialize, or use SetProfile while walking. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Skate") TObjectPtr<USkateProfile> Profile;
    UPROPERTY(BlueprintAssignable, Category="Skate|Events") FSkateModeChanged OnModeChanged;
    UPROPERTY(BlueprintAssignable, Category="Skate|Events") FSkateTrickChanged OnTrickChanged;
    UPROPERTY(BlueprintAssignable, Category="Skate|Events") FSkateContactEvent OnLanded;
    UPROPERTY(BlueprintAssignable, Category="Skate|Events") FSkateContactEvent OnBailed;
    UPROPERTY(BlueprintAssignable, Category="Skate|Events") FSkateFailureEvent OnRuntimeFailure;
    /** Change content atomically while off the board; existing sessions are discarded. */
    UFUNCTION(BlueprintCallable, Category="Skate") bool SetProfile(USkateProfile* NewProfile, FString& Failure);
    UFUNCTION(BlueprintCallable, Category="Skate") FSkateProfileChangeReport SetProfileReport(USkateProfile* NewProfile);
    UFUNCTION(BlueprintPure, Category="Skate|Debug") FSkateRuntimeDiagnostics GetRuntimeDiagnostics() const;
    /** The custom movement mode the ride runs in: the game's PhysCustom calls PhysSkate for it. */
    static constexpr uint8 MovementMode = 2;
    /** Character must implement ISkateRider. */
    void Initialize(ACharacter* Character);
    bool IsAvailable() const { return bAvailable; }
    /** On the board, including a bail (the component drives the character until they are back on it). */
    UFUNCTION(BlueprintPure, Category="Skate") bool IsRiding() const { return Mode != ESkateMode::Off; }
    UFUNCTION(BlueprintPure, Category="Skate")
    ESkateMode GetMode() const { return Mode; }
    /** Get on (from standing or running) or off. */
    UFUNCTION(BlueprintCallable, Category="Skate") bool Toggle();
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
    uint32 GetPoseGeneration() const { return PoseGeneration; }
    uint32 GetPoseSerial() const;
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
    UPROPERTY(Transient) TObjectPtr<USkateRuntimeAsset> RuntimeData;
    UPROPERTY(Transient) TArray<TObjectPtr<USkateCollisionAsset>> LoadedCollisionCatalogs;
    FString LastRuntimeError;
    uint32 PoseGeneration=0;
    bool LoadProfileContent(USkateProfile* Candidate, FString& Failure);
    void PublishModeChange(ESkateMode Previous);
    UPROPERTY() TObjectPtr<ACharacter> Rider;
    ISkateRider* RiderApi = nullptr;
    UPROPERTY() TObjectPtr<USceneComponent> BoardRoot;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Deck;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Trucks;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Wheels;
    UPROPERTY() TObjectPtr<USkateRailSubsystem> RailSystem;
    // Sounds (USkateProfile::SoundFolder): board-attached loops and one-shot variants.
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
};
