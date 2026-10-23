#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/EngineTypes.h"
#include "UObject/SoftObjectPath.h"
#include "DrivingComponent.generated.h"

class ACharacter;
class UAudioComponent;
class UPrimitiveComponent;
class USoundAttenuation;
class USoundWave;
class USceneComponent;
class UStaticMesh;
class UStaticMeshComponent;
struct FDrivingCar;

/** Host-authored cockpit in centimetres, +X forward and +Y right. Length data is unscaled. */
struct FDrivingCockpit
{
    FVector Seat = FVector::ZeroVector, Pelvis = FVector::ZeroVector, Steering = FVector::ZeroVector;
    FVector SteeringColumnBase = FVector::ZeroVector;
    FVector Foot = FVector::ZeroVector, Knee = FVector::ZeroVector, Elbow = FVector::ZeroVector;
    FVector FootForward = FVector::ForwardVector, BodyHalfExtents = FVector::ZeroVector;
    FVector WheelPositions[4] = {};
    float SteeringRadius = 0.f, SteeringTubeRadius = 0.f, SteeringTilt = 0.f, GripElevation = 0.f, Recline = 0.f;
    float ReferenceLegLength = 0.f, MinScale = 0.f, MaxScale = 0.f;
    float WheelRadius = 0.f, WheelWidth = 0.f;
};

namespace AtelierDrivingSide
{
/** The rider's left hand/foot is side 0; Unreal component space puts it at -Y. */
constexpr float Sign(int Side) { return Side ? 1.f : -1.f; }
static_assert(Sign(0) == -1.f, "side 0 is the rider's left, at component -Y");
static_assert(Sign(1) == 1.f, "side 1 is the rider's right, at component +Y");
}

/** Drives a four-wheel car from a character: summons it onto the ground beside the rider, mounts, steps the simulation
 *  at its fixed 60 Hz, and puts the rider back on their feet beside it. The simulation owns the chassis; this component
 *  only reads the world (a ray per wheel) and moves the actor it is attached to. */
UCLASS(ClassGroup=(Atelier), meta=(BlueprintSpawnableComponent))
class ATELIERDRIVING_API UDrivingComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UDrivingComponent();
    virtual ~UDrivingComponent() override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

    void Initialize(ACharacter* InRider);
    /** Configure before mounting; an unconfigured or incomplete cockpit cannot be summoned. */
    bool Configure(const FDrivingCockpit& InCockpit);
    /** True once a valid cockpit and a fitted rider are configured; a host retries the configuration after the rider's
     *  mesh arrives. */
    bool IsConfigured() const { return bConfigured; }
    /** Summon and mount, or (stopped) step off and park. False with the reason in GetStatus(). */
    bool Toggle();
    void StowImmediately();
    /** Kart-only: right an inverted, slow car after one second, and let the step-out button right it at once. */
    void SetAutoRight(bool On) { bAutoRight = On; }
    bool IsInverted() const;
    /** Test hook for the native flip scenario; it only changes this equipped car's rigid body. */
    bool ForceInvertedForQA();

    bool IsEquipped() const { return bEquipped; }
    bool IsDriving() const { return bEquipped; }
    /** Ground speed in centimetres per second (the game's unit). */
    float GetSpeed() const;
    float GetSpeedKph() const;
    /** The kart's mounted scale, fitted to the rider's leg length; fixed for the ride. */
    float GetKartScale() const { return KartScale; }
    FString GetStatus() const { return Hint; }
    /** The chassis pose: origin at the centre of gravity, +X the nose. */
    FTransform GetCarTransform() const;

    /** Intent from the rider: Move.X steers (right positive), Move.Y drives (forward) or brakes (back). */
    void SetInput(FVector2D Move);
    void SetHandbrake(bool bOn) { bHandbrake = bOn; }

    /** Four required meshes: body (ground origin, +X nose), seat, wheel (axle +Y), steering wheel (hub origin, axis +X). */
    void SetMeshes(const FSoftObjectPath& Body, const FSoftObjectPath& Seat, const FSoftObjectPath& Wheel,
                   const FSoftObjectPath& Steering);
    /** Whole-kart scale, fitted before mounting to the rider's reference leg length. */
    void SetKartScale(float Scale);
    /** All authored bone frames are wheel-local; the current animated wheel carries them. */
    void SetAuthoredGrips(TMap<FName, FTransform> Frames) { AuthoredGrips = MoveTemp(Frames); }
    void SetAuthoredElbow(FVector Point) { AuthoredElbow = Point; }
    bool SetAuthoredFit(float Lean, float Height, float Tilt);
    float GetSteeringTilt() const { return Cockpit.SteeringTilt; }
    void RequireAuthoredGrips(bool Required) { bRequireAuthoredGrips = Required; }
    bool HasAuthoredGrips() const { return AuthoredGrips.Num() == 32; }
    bool AuthoredGripWorld(FName Bone, FTransform& Out) const;
    float GetRecline() const { return Cockpit.Recline - AuthoredLean; }
    FVector GetFootForward() const { return Cockpit.FootForward; }
    float GetGripRadius() const { return Cockpit.SteeringRadius * KartScale; }
    float GetGripTubeRadius() const { return Cockpit.SteeringTubeRadius * KartScale; }

    /** The kart's own frame (centimetres, origin on the ground under its middle, +X the nose): where the driver sits
     *  and grips, for the animation stance. */
    FVector PosePoint(const FVector& Local) const;
    FVector PoseDirection(const FVector& Local) const;
    /** Folder the host game stages its driving cues in (impact and suspension one-shots, the engine, tyre, skid and
     *  wind loops). A game that stages none there drives silently. */
    void SetAudioRoot(const FString& InRoot) { AudioRoot = InRoot; }
    /** Each loop's applied volume and pitch (engine, tyre, skid, wind), for QA and offline film mixing. */
    FString GetAudioState() const;
    /** Ride telemetry: chassis height and vertical speed, pitch/roll, and per-wheel compression, height and contact. */
    FString GetRideState() const;
    /** Engine revolutions the engine loop was pitched from; zero while the kart is put away. */
    float GetAudioRevs() const { return AudioRevs; }
    /** Worst tyre skid among the grounded wheels, 0 to 1. */
    float GetAudioSlip() const { return AudioSlip; }
    /** Throttle intent: 0 released, 1 held. */
    float GetThrottle() const { return FMath::Max(MoveInput.Y, 0.f); }
    /** Skid of one wheel (0 front left, then front right, rear left, rear right), 0 to 1. */
    float GetWheelSlip(int32 Index) const;
    bool IsWheelGrounded(int32 Index) const;
    /** The tyre's contact point in world space (the wheel's ground origin). */
    FVector GetWheelContact(int32 Index) const;
    /** The wall hit since the last call, for effects: closing speed in cm/s and the point it met. */
    bool ConsumeImpact(float& OutSpeed, FVector& OutAt);
    FVector SeatPoint() const { return Cockpit.Pelvis; }
    FVector HandPoint(int32 Side) const;
    FVector ElbowPoint(int32 Side) const { return SidePoint(HasAuthoredGrips() ? AuthoredElbow : Cockpit.Elbow, Side); }
    FVector FootPoint(int32 Side) const { return SidePoint(Cockpit.Foot, Side); }
    FVector KneePoint(int32 Side) const { return SidePoint(Cockpit.Knee, Side); }
    FVector GripForward(int32 Side) const;
    FVector GripUp(int32 Side) const;
    FVector GripAxis(int32 Side) const;
    /** The channel the car reads the world on (default ECC_Visibility). */
    void SetTraceChannel(ECollisionChannel InChannel) { TraceChannel = InChannel; }

private:
    static FVector SidePoint(FVector Point, int32 Side) { Point.Y = FMath::Abs(Point.Y) * AtelierDrivingSide::Sign(Side); return Point; }
    bool Summon();
    bool Dismount();
    void EndDrive(const FVector& GroundSpot);
    /** Restore the rider and hide the kart without moving the actor (forced cleanup keeps the capsule centre). */
    void FinishDrive();
    bool StandingRoom(const FVector& Ground) const;
    void Recover();
    void StartRighting(bool bImmediate = false);
    void UpdatePose(float DeltaSeconds);
    void LoadSounds();
    bool PlayCue(FName Cue, float Volume, float Pitch);
    void UpdateAudio(float DeltaSeconds);
    void StopAudio();
    bool GroundBelow(const FVector& At, float Reach, FVector& Out) const;
    bool FreeAt(const FVector& At, const FQuat& Rotation) const;
    void FindGroundOffset();

    UPROPERTY() TObjectPtr<ACharacter> Rider;
    UPROPERTY() TObjectPtr<USceneComponent> CarRoot;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Body;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Seat;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Wheel[4];
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Steering;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> SteeringColumn;
    UPROPERTY() TObjectPtr<UStaticMesh> ColumnMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> BodyMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> SeatMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> WheelMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> SteeringMesh;
    TSharedPtr<FDrivingCar> Car;
    ECollisionChannel TraceChannel = ECC_Visibility;
    FSoftObjectPath BodyMeshPath;
    FSoftObjectPath SeatMeshPath;
    FSoftObjectPath WheelMeshPath;
    FSoftObjectPath SteeringMeshPath;
    FVector2D MoveInput = FVector2D::ZeroVector;
    FString Hint;
    float GroundOffset = 0.f;
    float KartScale = 1.f;
    FDrivingCockpit Cockpit;
    TMap<FName, FTransform> AuthoredGrips;
    FVector AuthoredElbow = FVector::ZeroVector;
    float AuthoredLean = 0.f;
    bool bConfigured = false, bRequireAuthoredGrips = false;
    float Spin[4] = {0.f, 0.f, 0.f, 0.f};
    FQuat SteeringBase = FQuat::Identity;
    FVector LastGround = FVector::ZeroVector;
    bool bHandbrake = false;
    bool bEquipped = false;
    bool bHasGround = false;
    bool bAutoRight = false;
    bool bRighting = false;
    float InvertedTime = 0.f;
    float RightingTime = 0.f;
    FVector RightFrom = FVector::ZeroVector;
    FVector RightTo = FVector::ZeroVector;
    FQuat RightFromQ = FQuat::Identity;
    FQuat RightToQ = FQuat::Identity;
    bool bSavedUseControllerYaw = false;
    FString AudioRoot = TEXT("/Game/Audio/Driving");
    UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
    UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
    UPROPERTY() TArray<TObjectPtr<UAudioComponent>> Loops;
    TMap<FName, FIntPoint> CueRange;
    TArray<float> LoopVolume;
    TArray<float> LoopPitch;
    int32 EngineFirst = 0, EngineCount = 0, TyreFirst = 0, TyreCount = 0;
    int32 SkidFirst = 0, SkidCount = 0, WindFirst = 0, WindCount = 0;
    int32 LastVariant = INDEX_NONE;
    float AudioRevs = 0.f, AudioSlip = 0.f, ImpactSpeed = 0.f, BumpWait = 0.f, ImpactWait = 0.f;
    float PendingImpact = 0.f;
    FVector PendingImpactAt = FVector::ZeroVector;
    bool bAudioReady = false;
    bool bWheelWasGrounded[4] = {false, false, false, false};
};
