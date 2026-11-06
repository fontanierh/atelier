#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GameFramework/Actor.h"
#include "WandererSword.generated.h"

class AWandererCharacter;
class UWandererDefinition;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class ASwordDummy;
class UAtelierTrail;
struct FWandererSwordClip;

/** Weapon state. The sword is a rigid static mesh on the right hand; "Stowed" hides it. */
UENUM()
enum class ESwordState : uint8 { Stowed, Guard, Draw, Sheath, Attack, Parry, ParryHit, ChargeUp, ChargeHold, ChargeRelease };

/** One registered strike, for telemetry and the QA harness. */
struct FSwordStrikeEvent
{
    float Time = 0.f; FName Clip; int32 Combo = 0; bool bCharged = false, bFull = false; TArray<TWeakObjectPtr<AActor>> Targets;
};

/**
 * Sword combat on the game-r13 clip set: draw/sheathe, a three-strike chain with input buffering and
 * link/cancel windows, a parry with a short active window and a counter, and a charged attack with an
 * arbitrary-length hold, early/full release, hit-stop and a safe cancel. Blade hits are swept only in
 * each clip's active window, exclude the wielder and land once per target per strike. Timing is in
 * clip source seconds at the played rate, so it is frame-rate independent.
 */
UCLASS()
class YORIMICHI_API UWandererSwordComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UWandererSwordComponent();
    void Initialize(AWandererCharacter* Owner);
    /** Per-frame state machine; called by the character before its generic action bookkeeping. */
    void Advance(float Dt);
    // Input
    void AttackPressed();
    void AttackReleased();
    /** The button is no longer held but must not fire (menu, focus loss): drops the hold without a release strike. */
    void DropAttackHold() { bAttackHeld = false; }
    void ParryPressed();
    void ToggleWeapon();
    /** Show or hide the sword in the hand at once (no draw or sheathe clip). */
    void SetArmed(bool bArmed);
    /** The clip for standing still with the sword out. */
    FName StandClip() const;
    /** A roll/dash/jump/menu wants to interrupt: cancels charges and post-cancel-window recoveries. Returns true when the sword no longer blocks. */
    bool CancelForInterrupt(bool bStow);
    /** An enemy strike lands now: parry-active deflects it and starts the counter; otherwise the wielder is hit. Returns true when parried. */
    bool IncomingStrike(AActor* Source) { return IncomingStrike(Source, 0.f, FVector::ZeroVector) == 1; }
    /** The full contract: 0 hit (Damage taken, flinch, knock-down at zero health), 1 parried, 2 dodged (rolling), 3 absorbed (recovering from a hit). */
    int32 IncomingStrike(AActor* Source, float Damage, const FVector& From);
    // Health of the wielder: enemy strikes take it; at zero the character is knocked down for a few seconds and gets up restored.
    float GetHealth() const { return Health; }
    /** Non-lethal health cost after a server-approved recovery to shore. */
    void ApplyRecoveryDamage(float Damage);
    /** Presentation of the server's health on an online pawn; not a damage request. */
    void ApplyNetworkHealth(float Value, int32 Hits) { Health = FMath::Clamp(Value, 0.f, MaxHealth); HitsTakenCount = FMath::Max(0, Hits); }
    /** Full health again (a sparring bout's start and end, ASwordTrainer). */
    void RestoreHealth() { Health = MaxHealth; }
    bool IsDown() const { return bDown; }
    static constexpr float MaxHealth = 100.f;
    // Harness only: movement intent and a roll through the character's real handlers.
    void ReviewMove(FVector2D Intent);
    void ReviewRoll(FVector2D Intent);
    // Queries
    bool IsArmed() const { return State != ESwordState::Stowed; }
    bool IsInstalled() const;
    bool OwnsAction(FName Action) const;
    bool LocksMovement() const;
    bool BlocksActions() const;
    bool IsParryActive() const;
    ESwordState GetState() const { return State; }
    FString StateName() const;
    /** Right-arm carry layer weight while armed but not playing a sword clip. */
    float CarryWeight() const { return Carry; }
    const TArray<FSwordStrikeEvent>& Strikes() const { return StrikeLog; }
    int32 HitsTaken() const { return HitsTakenCount; }
    int32 ParriesMade() const { return ParryCount; }
    float LastFeedbackAge() const;
    FString LastFeedback() const { return Feedback; }
    bool WasFullCharge() const { return bFullCharge; }
    float ChargeFraction() const;
    FVector BladeTipWorld() const;
    // Constants (seconds)
    // HoldThreshold: a press still held this long after strike 1 began turns into a charge once the cut has landed.
    static constexpr float DrawTime = .3f, HoldThreshold = .25f, FullChargeTime = .9f, BufferWindow = .3f, ParryActiveStart = .03f, ParryActiveEnd = .3f;
private:
    friend class UAdventureMoveSet;   // a move set keeps the wielder's health and hit counts here
    void Enter(ESwordState Next, FName Clip, float Blend, float Rate = 1.f, bool bLoop = false, float StartTime = 0.f);
    void StartAttack(int32 Combo, float Blend);
    /** Faces the stick/camera, or a soft-locked fox: StepToDistance > 0 steps in to that distance during the wind-up; YawOffset
     *  turns the facing so the clip's actual contact zone (measured per strike) passes through the target. */
    void FaceInput(float StepToDistance = -1.f, float YawOffsetDeg = 0.f);
    void SweepBlade(float Dt);
    void BladePoints(TArray<FVector>& Out) const;
    void SetFeedback(const FString& Text);
    const FWandererSwordClip* Clip(FName Role) const;
    void UpdateSwordVisibility();
    UPROPERTY() TObjectPtr<AWandererCharacter> Character;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Blade;
    UPROPERTY() TObjectPtr<UAtelierTrail> Trail;
    bool bSwingCue = false, bChargeReadyCue = false;
    void Effects(float Dt);
    ESwordState State = ESwordState::Stowed;
    FName CurrentClip;
    bool bFastCarry = false;
    float StateTime = 0.f, Carry = 0.f, ChargeTime = 0.f, HitStop = 0.f, FeedbackTime = -100.f;
    float LastAttackPress = -100.f, LastRelease = -100.f, AttackStartClock = -100.f;
    bool bAttackHeld = false, bFullCharge = false, bPendingDrawAttack = false, bCharged = false, bCounter = false, bCounterStrike = false, bChargeFromStrike = false, bDown = false;
    float Health = MaxHealth, Invulnerable = 0.f, DownTime = 0.f;
    void ForceGuard();
    int32 ComboIndex = 0, HitsTakenCount = 0, ParryCount = 0;
    float FacingTarget = 0.f, FacingBlend = 0.f, LockDistance = -1.f, StepInRemaining = 0.f;
    FVector StepInDir = FVector::ForwardVector;
    TArray<FVector> PreviousBlade;
    TSet<TWeakObjectPtr<AActor>> HitThisStrike;
    TArray<FSwordStrikeEvent> StrikeLog;
    FString Feedback;
    float Clock = 0.f;
};

/**
 * Deterministic training fixture: a post that can be hit, and that swings on request or on a
 * period, telling the player's sword when its strike lands. It stands in for an enemy; it does not
 * prove real enemy combat.
 */
UCLASS()
class YORIMICHI_API ASwordDummy : public AActor
{
    GENERATED_BODY()
public:
    ASwordDummy();
    virtual void Tick(float Dt) override;
    /** Registers a hit from the player's blade; Strength 1 light, 2 charged, 3 full charge. */
    void TakeSwordHit(int32 Strength);
    /** Begin a swing that lands after WindupSeconds. */
    void StrikeIn(float WindupSeconds);
    void SetAutoStrike(float Period) { AutoPeriod = Period; AutoClock = 0.f; }
    void SetTarget(AWandererCharacter* T) { Target = T; }
    int32 HitsTaken = 0, StrikesLanded = 0, StrikesParried = 0, StrikesMissed = 0;
    float LastHitTime = -100.f, Reach = 190.f;
private:
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Post;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Paint;
    UPROPERTY() TObjectPtr<AWandererCharacter> Target;
    float Windup = -1.f, Stagger = 0.f, Flash = 0.f, AutoPeriod = 0.f, AutoClock = 0.f, Clock = 0.f;
};
