#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "JapanHorseState.h"
#include "JapanHorseAppearance.h"
#include "JapanSkateClock.h"
#include "HorseComponent.generated.h"

class AWandererCharacter;
class USceneComponent;
class USkeletalMeshComponent;
class UAnimSequence;
class UMaterialInterface;
class UMaterialInstanceDynamic;
struct FHorseRiderNode;

/** What the horse and its rider are doing: one clip each, the rider's A_Horse<Role> on his rig and the breed's roster clip
 *  (mounting and dismounting stand the horse in its Idle). The order is fixed: a shared game sends the index
 *  (FJapanHorseState::Role). */
enum class EHorseRole : uint8
{
    Idle, IdleLook, IdleGraze, IdleShake, IdleFlehmen, IdleAffection, Walk, Trot, Canter, Gallop, Sprint, Mount, Dismount, Count
};

/** One simulation step's controls. Stick X steers, Y rides on (+) or reins in (-); Walk and Jog cap the gait; a menu
 *  reins in and lets go of the steering. */
struct FHorseInput
{
    FVector2D Stick = FVector2D::ZeroVector;
    bool bWalk = false;
    bool bJog = false;
    bool bMenu = false;
};

/** A horse to ride (assets/horses; Content/Data/horses/roster.json, written by Scripts/import_horses.py). Summoned under
 *  him, mounted, ridden with walking physics and sent away when he gets off. As on the bike, floors, slopes, steps, falls
 *  and walls stay the movement component's: the horse only sets his velocity and heading, before the movement component
 *  moves him. The rider's clips are authored on his rig (assets/horses/rider.py); the horse plays its breed's clip on the
 *  rider's clock, and FHorseRiderNode keeps him in the saddle. */
UCLASS()
class YORIMICHI_API UHorseComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    enum class EPhase : uint8 { Stowed, Mounting, Riding, Dismounting };
    UHorseComponent();
    void Initialize(AWandererCharacter* InRider);
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    /** H / hold RB: summon and mount standing on the ground (not crouching), or get off once stopped on the ground.
     *  False with the reason in GetStatus(). */
    bool Toggle();
    void StowImmediately();
    /** The controls TickComponent steps with (offline: AWandererCharacter::Tick). */
    void SetInput(const FHorseInput& In) { Input = In; }
    /** Shift / left stick press while riding: sprint until pressed again or the horse comes to a halt. False when he is
     *  not riding. */
    bool ToggleSprint();
    /** One step of the ride, deterministic from this state, the input and the world: speed, heading (the actor's yaw), the
     *  movement component's velocity, the phase, the clip and its clock. No presentation, sound or randomness, so a shared
     *  game can run it inside the movement component's moves and replay it. False when the horse has gone (offline, at the
     *  end of dismounting or on reaching swimming depth: stow him); online either waits in
     *  NeedsNetworkStow() for the host instead. */
    bool AdvanceSimulation(float Dt, const FHorseInput& In);
    bool NeedsNetworkStow() const { return bTerminal; }

    // A shared game (HorseNetwork.cpp, as BikeNetwork.cpp): the owner and the host simulate inside the movement component's
    // moves (bounded substeps); TickComponent only presents. Remote players show the host's 20 Hz presentation.
    /** Online the simulation ticks after the movement component; offline before it. */
    void RefreshTickOrder();
    void SimulateNetwork(float Dt, const FHorseInput& In);
    FJapanHorseState CaptureNetworkState() const;
    /** A correction restores simulation fields only; RestoreFacing false (presentation) never turns the actor. */
    bool ApplyNetworkState(const FJapanHorseState& Snapshot, bool RestoreFacing = true);
    /** An activity handoff: the state, the walking physics' friction and braking held off, the horse shown. */
    bool ApplyNetworkActivity(const FJapanHorseState& Snapshot);
    void ReceiveNetworkPresentation(uint32 Epoch, double Stamp, const FJapanHorseState& Snapshot);
    /** The horses are installed and this rider has horse clips for his skeleton. */
    bool CanRide() const;
    /** Whether a character (its class default will do) has horse clips on its rig: the character switch asks before it
     *  spawns a mounted rider. */
    static bool HasRiderClips(const AWandererCharacter* Character);
    bool IsHorseVisible() const;

    /** N: a random breed, tack, coat, mask, hair and tint. */
    void RandomizeHorse();
    /** U / I / O: the next (Delta 1) or previous (-1) breed, tack set or coat, wrapping round. */
    void CycleBreed(int32 Delta = 1);
    void CycleTack(int32 Delta = 1);
    void CycleCoat(int32 Delta = 1);
    /** The looks those would choose, without applying them (a shared game asks the host). */
    FJapanHorseAppearance RandomAppearance() const;
    FJapanHorseAppearance NextBreed(int32 Delta = 1) const;
    FJapanHorseAppearance NextTack(int32 Delta = 1) const;
    FJapanHorseAppearance NextCoat(int32 Delta = 1) const;
    FJapanHorseAppearance GetAppearance() const { return Appearance; }
    bool IsValidAppearance(const FJapanHorseAppearance& Candidate) const;
    /** False, changing nothing, when an index is out of the roster's range. */
    bool ApplyAppearance(const FJapanHorseAppearance& NewAppearance);
    /** By roster ids (breed slug, tack id, coat id or "native", mask, hair colour id or "native", hair pattern, tint); an
     *  empty id keeps that part. False, changing nothing, for an unknown id. */
    bool ResolveAppearance(const FString& Breed, const FString& Tack, const FString& Coat, const FString& Mask,
        const FString& HairColor, const FString& HairPattern, const FString& Tint, FJapanHorseAppearance& Out) const;
    bool ConfigureHorse(const FString& Breed, const FString& Tack, const FString& Coat, const FString& Mask,
        const FString& HairColor, const FString& HairPattern, const FString& Tint);

    bool IsAvailable() const { return bAssetsReady; }
    /** He is on (or getting on or off) the horse: it owns his movement, his animation and his buttons. */
    bool IsEquipped() const { return Phase != EPhase::Stowed; }
    bool IsRiding() const { return Phase == EPhase::Riding; }
    bool IsSprinting() const { return bSprint; }
    EPhase GetState() const { return Phase; }
    EHorseRole GetRole() const { return Role; }
    /** Bumped by every new clip, so the animation instance blends into it. */
    uint32 GetSerial() const { return Serial; }
    float GetSpeed() const { return Speed; }
    float GetSteering() const { return Steering; }
    /** The pitch (degrees, nose up) he and the horse take from the ground under its hooves. */
    float GetGroundPitch() const { return GroundPitch; }
    /** The rider's clip for the current role, and where it should be: the gait cycle's phase on the clip's length. */
    UAnimSequence* GetSequence() const;
    /** The breed's clip for the current role, or its Idle when it has none. */
    UAnimSequence* GetHorseSequence() const;
    float GetPoseTime() const;
    FName GetRiderClip() const;
    FName GetHorseClip() const;
    /** Breed, coat, tack and gait, then why the last request was refused. */
    FString GetStatus() const;
    FTransform GetHorseTransform() const;
    FString GetBreedId() const;
    FString GetTackId() const;
    FString GetCoatId() const;
    FString GetMaskId() const;
    FString GetHairColorId() const;
    FString GetHairPatternId() const;
    FString GetTintId() const;

    /** The rider node's torso spring, seat and rein and stirrup targets. */
    void PopulateRiderNode(FHorseRiderNode& OutNode) const;

private:
    friend class FJapanHorseWaterTest;
    bool IsInDeepWater() const;
    struct FBreed
    {
        FString Slug, Name, Mesh;
        float MeshYaw = 0.f;
        float ScaleRatio = 1.f;
        TArray<FString> Clips;   // per EHorseRole: the breed's clip path, empty when it has none
        TMap<FString, FString> Saddles, Reins;   // tack id -> mesh path
        // Contacts less the reference breed's, in the rider mesh's component space (cm, +X forward, +Y right, +Z up).
        FVector Seat = FVector::ZeroVector, StirrupL = FVector::ZeroVector, StirrupR = FVector::ZeroVector;
        FVector GripL = FVector::ZeroVector, GripR = FVector::ZeroVector;
    };
    struct FHairColor { FString Id; FLinearColor Primary, Secondary; };
    struct FHairPattern { FString Id; float Mix = 0.f; };
    struct FTint { FString Id; FLinearColor Color; };
    struct FCoatVariant { FString Id, Texture; };

    bool LoadRoster();
    /** The rider's rig, naming his horse clips: his own, or (as on the bike) the default character's. */
    FString RiderRig() const;
    static FString RigOf(const AWandererCharacter* Character);
    void LoadRiderClips();
    void ApplyCurrentBreedAndTack();
    void ApplyCurrentMaterials();
    void Play(EHorseRole NewRole);
    EHorseRole SelectRole() const;
    float ClipLength(EHorseRole Of) const;
    /** How long mounting (Of Mount) or dismounting (Dismount) lasts: the rider's clip for it. */
    float TransitionLength(EHorseRole Of) const;
    static bool Loops(EHorseRole Of);
    void AdvanceGait(float Dt);
    void Present(float Dt);
    void ResetPresentation();
    /** Mounted, the walking physics' friction and braking are held off (the horse sets the speed); saved once a ride. */
    void HoldFriction();
    void ReleaseFriction();
    void PresentNetwork(float Dt);
    void SampleNetworkPresentation();
    bool QueueNetworkAction(FName Button, bool& Accepted);
    void FollowGround(float Dt);
    void StepTorsoSpring(float Dt);
    void EmitHoofsteps(float From, float To);

    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY() TObjectPtr<USceneComponent> HorseRoot;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> HorseMesh;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> SaddleMesh;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> ReinsMesh;
    // The roster's coat and hair masters: a body slot whose imported instance derives from one gets a dynamic instance.
    UPROPERTY() TObjectPtr<UMaterialInterface> CoatMaster;
    UPROPERTY() TObjectPtr<UMaterialInterface> HairMaster;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> CoatMaterials;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> HairMaterials;
    // Per EHorseRole: the rider's clip on his rig, and the current breed's.
    UPROPERTY() TArray<TObjectPtr<UAnimSequence>> RiderClips;
    UPROPERTY() TArray<TObjectPtr<UAnimSequence>> HorseClips;

    TArray<FBreed> Breeds;
    TArray<FString> TackIds;
    TArray<TPair<FString, FString>> CoatMasks;   // mask id -> texture path, in the roster's order
    TArray<FCoatVariant> CoatVariants;
    TArray<FHairColor> HairColors;
    TArray<FHairPattern> HairPatterns;
    TArray<FTint> Tints;
    FJapanHorseAppearance Appearance;
    bool bAssetsReady = false;

    // The simulation (AdvanceSimulation): what a shared game checkpoints (FJapanHorseState).
    EPhase Phase = EPhase::Stowed;
    EHorseRole Role = EHorseRole::Idle;
    EHorseRole ForcedIdle = EHorseRole::Idle;   // an idle variant playing out, or Idle for none
    uint32 Serial = 0;
    float PhaseTime = 0.f;   // s into mounting or dismounting
    float GaitPhase = 0.f;   // 0..1 through the rider's clip
    float Speed = 0.f;
    float Steering = 0.f;
    float IdleTimer = 0.f;   // s left of the idle variant
    float IdleCooldown = 0.f;   // s until the next idle variant
    bool bSprint = false;
    bool bReinIn = false;
    bool bTerminal = false;
    FHorseInput Input;

    // Presentation only (Present): the ground's pitch, the lean into a turn, the torso spring and the clip on the horse.
    float GroundPitch = 0.f, BankAngle = 0.f, PresentedSpeed = 0.f, SmoothedAccelForward = 0.f;
    float TorsoPitchDeg = 0.f, TorsoPitchVel = 0.f, TorsoRollDeg = 0.f, TorsoRollVel = 0.f, TorsoYawDeg = 0.f, TorsoYawVel = 0.f;
    float PelvisHeaveCm = 0.f, PelvisHeaveVel = 0.f;
    uint32 PresentedSerial = 0;
    float PresentedGaitPhase = 0.f;
    bool bHorseClipStale = true;

    // A shared game: the tick order, and a remote player's buffered host presentation.
    bool bTickModeSet = false, bNetworkTickOrder = false;
    uint32 PresentationBufferEpoch = 0;
    struct FNetworkPose { double At; FJapanHorseState State; };
    TArray<FNetworkPose> NetworkPoses;
    FJapanSkatePlayout NetworkPlayout;
    double LastPresentationStamp = -1.;

    FString Hint;
    float SavedFriction = 0.f, SavedBraking = 0.f;
    bool bFrictionSaved = false;
    FVector MeshLocation = FVector::ZeroVector;
    FRotator MeshRotation = FRotator::ZeroRotator;
};
