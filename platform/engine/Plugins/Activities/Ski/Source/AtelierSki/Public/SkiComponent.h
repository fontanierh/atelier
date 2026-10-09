#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SkiComponent.generated.h"

class ACharacter;
class ISkiRider;
class UStaticMeshComponent;
class UStaticMesh;
class UMaterialInterface;
class USkiPhysicalBody;
struct FSkiRuntime;

/** Deletes the runtime where its type is complete: UHT's generated code instantiates the member's destructor. */
struct ATELIERSKI_API FSkiRuntimeDeleter { void operator()(FSkiRuntime* Ptr) const; };

/** The skier's controls for one frame (README.md, "Controls"). */
USTRUCT(BlueprintType)
struct ATELIERSKI_API FSkiInput
{
    GENERATED_BODY()
    /** -1 left to 1 right: lean into a turn. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = Ski) float Steer = 0.f;
    /** -1 back to 1 forward: the weight over the skis. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = Ski) float Lean = 0.f;
    /** Held: crouch; released: extend and pop. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = Ski) bool bCrouch = false;
    /** -1 to 1: wind up a spin before the pop. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = Ski) float Spin = 0.f;
    /** 0 none, 1 mute, 2 safety. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = Ski) int32 Grab = 0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = Ski) bool bBrake = false;
};

/** The skiing pose in the mesh's component space, for FAnimNode_SkiRider. Index 0 is left, 1 right. */
struct ATELIERSKI_API FSkiPose
{
    float Weight = 0.f;
    FName Pelvis, Spine[3], Neck, Head, Thigh[2], Shin[2], Foot[2], UpperArm[2], Forearm[2], Hand[2];
    FTransform PelvisTarget = FTransform::Identity;
    FQuat FootRotation[2] = {FQuat::Identity, FQuat::Identity};
    FVector Ankle[2] = {FVector::ZeroVector, FVector::ZeroVector}, Knee[2] = {FVector::ZeroVector, FVector::ZeroVector};
    FVector HandTarget[2] = {FVector::ZeroVector, FVector::ZeroVector}, Elbow[2] = {FVector::ZeroVector, FVector::ZeroVector};
    /** The trunk bends forward about BendAxis by Bend (radians) over the spine; the head looks back up by Look. */
    FVector BendAxis = FVector::RightVector;
    float Bend = 0.f, Look = 0.f;
};

/** Physics-based freestyle skiing (README.md): the native simulation (Private/Native) runs in a custom movement mode of
 *  the game's movement component (its PhysCustom calls PhysSki), reads the world's static collision and the terrain
 *  parks (ASkiPark), and the character's own body rides it as an active ragdoll. The character implements ISkiRider. */
UCLASS(ClassGroup = Atelier, meta = (BlueprintSpawnableComponent))
class ATELIERSKI_API USkiComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    USkiComponent();

    /** The custom movement mode the skiing runs in: the game's PhysCustom calls PhysSki for it. */
    static constexpr uint8 MovementMode = 6;

    /** Character must implement ISkiRider. */
    void Initialize(ACharacter* InCharacter);
    /** Skis on (standing on the ground) or off (riding, not in a crash or the air). */
    UFUNCTION(BlueprintCallable, Category = Ski) bool Toggle();
    UFUNCTION(BlueprintCallable, Category = Ski) bool Start();
    UFUNCTION(BlueprintCallable, Category = Ski) void Stop();
    /** Skis on at a place, facing a way, at a speed (cm, degrees, cm/s): for scripts and QA. */
    UFUNCTION(BlueprintCallable, Category = Ski) bool StartAt(FVector Location, float Yaw, float Speed);
    /** Replaces the player's controls until cleared (QA and scripts). */
    UFUNCTION(BlueprintCallable, Category = Ski) void SetScriptedInput(bool bOn, FSkiInput Input);

    /** On the skis, including a crash. */
    UFUNCTION(BlueprintPure, Category = Ski) bool IsSkiing() const { return bSkiing; }
    UFUNCTION(BlueprintPure, Category = Ski) bool IsCrashed() const;
    UFUNCTION(BlueprintPure, Category = Ski) bool IsAirborne() const;
    /** Speed over the snow (cm/s). */
    UFUNCTION(BlueprintPure, Category = Ski) float GetSpeed() const;
    /** "carving", "skidding", "air", "stopping", "crash" or "off". */
    UFUNCTION(BlueprintPure, Category = Ski) FString GetStatus() const;
    /** The last trick named or landed, and how long ago (s). */
    UFUNCTION(BlueprintPure, Category = Ski) FString GetLastTrick(float& Age) const;
    UFUNCTION(BlueprintPure, Category = Ski) int32 GetScore() const;
    /** One line for logs and QA: mode, speed, edge, lean, ground and the last event. */
    UFUNCTION(BlueprintCallable, Category = Ski) FString Describe() const;

    /** Called from the movement component's PhysCustom for MovementMode. */
    void PhysSki(float Dt);
    /** The pose for the anim node; false while it has no weight. */
    bool GetPose(FSkiPose& Out) const;

    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
    FSkiInput ReadInput() const;
    bool BeginRide(const FVector& Feet, float Yaw, float Speed);
    void StepSimulation(float Dt, const FSkiInput& Input);
    void HandleEvents();
    void PlaceActor();
    void UpdatePose(float Dt);
    void PlaceSkis();
    void GetUp();
    FName Bone(const TCHAR* Contract) const;

    UPROPERTY() TObjectPtr<ACharacter> Character;
    ISkiRider* Rider = nullptr;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Skis[2];
    UPROPERTY() TObjectPtr<USkiPhysicalBody> Body;
    UPROPERTY() TObjectPtr<UStaticMesh> DefaultSkiMesh;
    UPROPERTY() TObjectPtr<UMaterialInterface> DefaultSkiMaterial;

    TUniquePtr<FSkiRuntime, FSkiRuntimeDeleter> Runtime;
    FSkiPose Pose;
    /** The skis on the snow under the simulated boots, and relative to the feet once a crash lets the body go. */
    FTransform SkiWorld[2], SkiOnFoot[2];
    bool bSkiing = false, bScripted = false, bCrashed = false, bSkisOnFeet = false, bCubeSkis = false;
    FSkiInput Scripted;
    float Accumulator = 0.f, CrashClock = 0.f, PoseWeight = 0.f, GrabWeight = 0.f, AirArms = 0.f;
    int32 GrabSide = 0;
    FString LastTrick, LastEvent;
    double LastTrickTime = -1e9;
    int32 Score = 0;
    float CapsuleHalfHeight = 0.f;
    TEnumAsByte<ECollisionResponse> SavedCapsuleToBodies = ECR_Block;
};
