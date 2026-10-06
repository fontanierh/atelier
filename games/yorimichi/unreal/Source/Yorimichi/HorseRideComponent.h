#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HorseRideComponent.generated.h"

class AWandererCharacter;
class AHippodromeFigure;
class USoundBase;

/**
 * Riding a hippodrome horse about the world (docs/HIPPODROME.md). H brings round the horse last ridden at the hippodrome
 * (Saved/hippodrome.json, else Momo) and mounts it; slowed to a walk, H steps off and leaves it standing, and H near it
 * mounts again. The horse is an AHippodromeFigure carrying the player's rider (RiderCairo, or Link's for Link): the
 * character's capsule keeps its walking physics (floors, slopes, walls) and is hidden while the figure follows it.
 * W trots, Shift gallops, Alt walks, S reins in, A / D turn, Space spurs (three, refilling) and Q rears at a standstill.
 */
UCLASS()
class YORIMICHI_API UHorseRideComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UHorseRideComponent();
    void Initialize(AWandererCharacter* Character);
    /** H: mount (the horse left nearby, or the chosen horse brought round), or step off. False with the reason in GetStatus(). */
    bool Toggle();
    /** Off the horse at once and the horse gone (travel, leaving the world, a race). */
    void StowImmediately();
    void SetInput(FVector2D Intent, bool bGallopHeld, bool bWalkHeld, bool bMenuOpen);
    bool Spur();
    bool Rear();
    virtual void TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    bool IsAvailable() const;
    bool IsEquipped() const { return bRiding; }
    float GetSpeed() const { return Speed; }
    int32 GetSpurs() const { return Spurs; }
    FName GetGait() const { return Gait; }
    FString GetHorse() const { return HorseName; }
    FString GetStatus() const { return Hint; }
    AHippodromeFigure* GetFigure() const;
    /** The roster rider for this character in the saddle: RiderCairo for Cairo, Rider<Name> for a BOTW rider; empty if none. */
    static FString RiderFor(const AWandererCharacter* Character);
    static constexpr int32 MaxSpurs = 3;

private:
    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY() TArray<TObjectPtr<USoundBase>> Hooves;
    UPROPERTY() TObjectPtr<USoundBase> SpurSound;
    TWeakObjectPtr<AHippodromeFigure> Figure;
    FString HorseName, Hint = TEXT("H horse");
    FName Gait;
    FVector2D Input = FVector2D::ZeroVector;
    bool bGallop = false, bWalk = false, bMenu = false, bRiding = false;
    float Speed = 0.f, Steering = 0.f, Pitch = 0.f, SpurLeft = 0.f, SpurRefill = 0.f, RearLeft = 0.f, StrideClock = 0.f;
    int32 Spurs = MaxSpurs;
    float SavedFriction = 0.f, SavedBraking = 0.f;
    void Mount(AHippodromeFigure* Horse);
    void Dismount(bool bPark);
    void Pose(float Dt);
    /** The horse onto the capsule's feet, once the movement component has moved it this frame (OnCharacterMovementUpdated). */
    UFUNCTION() void Place(float Dt, FVector OldLocation, FVector OldVelocity);
    bool ClearFor(const FVector& Ground, float Yaw) const;
    FVector Feet() const;
    static FString ChosenHorse();
};
