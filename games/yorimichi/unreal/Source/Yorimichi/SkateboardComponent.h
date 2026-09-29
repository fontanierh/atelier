#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SkateboardComponent.generated.h"

class AWandererCharacter;
class UStaticMeshComponent;
class USceneComponent;
class UAnimSequence;

enum class ESkateState : uint8 { Stowed, Mounting, Riding, Pushing, Braking, Dismounting, OllieStart, OllieAir, OllieLand };

/** Equippable cruiser, authored pose clock and ground-contact animation data. */
UCLASS()
class YORIMICHI_API USkateboardComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    USkateboardComponent();
    void Initialize(AWandererCharacter* Character);
    bool Toggle();
    void StowImmediately();
    bool BeginMega();
    FVector2D GetInput() const { return Input; }
    bool IsMenuOpen() const { return bMenu; }
    void SetPreferredGoofy(bool bGoofy);
    bool IsGoofy() const { return bGoofy; }
    bool IsPreferredGoofy() const { return bPreferredGoofy; }
    FName GetPushFootBone() const { return bGoofy ? TEXT("foot_L") : TEXT("foot_R"); }
    void RequestOllie();
    void Landed();
    void SetInput(FVector2D Intent, bool bMenuOpen);
    virtual void TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick) override;
    bool IsEquipped() const { return State != ESkateState::Stowed; }
    bool IsPushingGround() const { return State == ESkateState::Pushing && PoseTime >= PlantTime && PoseTime < ReleaseTime; }
    bool IsContinuousPush() const { return State == ESkateState::Pushing && bPushCycle; }
    bool IsStopping() const { return bStowRequested || bMenu || Input.Y < -.15f; }
    bool CanRoll() const { return State != ESkateState::Mounting && State != ESkateState::Dismounting; }
    float GetSteering() const { return Steering; }
    float GetPoseTime() const { return PoseTime; }
    uint32 GetSerial() const { return Serial; }
    UAnimSequence* GetSequence() const;
    FName GetClipName() const;
    FString GetStatus() const;
    float GetContactWeight() const { return bContact ? 1.f : 0.f; }
    FVector GetContactLocation() const { return ContactLocation; }
    FTransform GetBoardTransform() const;
    int32 GetBoardStencil() const;
    bool IsOllie() const { return State == ESkateState::OllieStart || State == ESkateState::OllieAir || State == ESkateState::OllieLand; }
    float GetBlendTime() const { return State == ESkateState::OllieAir ? 0.f : .12f; }
    static constexpr float MaxSpeed = 1400.f; // 50.4 km/h, built up through repeated pushes.
    static constexpr float PlantTime = .48f, ReleaseTime = .70f, StrokeLength = 42.f;

private:
    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY() TObjectPtr<USceneComponent> BoardRoot;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Deck;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Trucks;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Wheels;
    ESkateState State = ESkateState::Stowed;
    FVector2D Input = FVector2D::ZeroVector;
    FVector OriginalMeshLocation, LastPosition, ContactLocation;
    FQuat OriginalMeshRotation, GroundRotation = FQuat::Identity;
    float PoseTime = 0.f, StrokeTravel = 0.f, ContactSeconds = 0.f;
    float Steering = 0.f, Bank = 0.f, WheelAngle = 0.f, OriginalStepHeight = 45.f;
    uint32 Serial = 0;
    bool bAssetsReady = false, bStowRequested = false, bMenu = false, bContact = false;
    bool bPushCycle = false;
    bool bGoofy = false, bPreferredGoofy = false, bRemountForStance = false;
    float AirFloorGap = 0.f;
    FName LastMegaClip;
    void SetState(ESkateState Next);
    void PlantFoot();
    void UpdateVisuals(float Dt, float Distance);
};
