#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Engine/DataAsset.h"
#include "Math/RandomStream.h"
#include "FoxHunter.generated.h"

class USkeletalMesh;
class UAnimSequence;
class UBlendSpace;
class AWandererCharacter;
class UMaterialInstanceDynamic;

/** Gameplay data of one fox clip, in clip seconds at 1x (from the animation-r04 manifest through the export). */
USTRUCT(BlueprintType)
struct FFoxHunterClip
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FName Role;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float Duration = 0.f;
    // Strike sweeps register a hit only inside [HitStart, HitEnd], along StrikeBone -> StrikeTipBone.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float HitStart = -1.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float HitEnd = -1.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FName StrikeBone;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FName StrikeTipBone;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float ReachCm = 0.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) bool RootMotion = false;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) bool Loop = false;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) bool HoldsLastPose = false;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float TravelCm = 0.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float YawDegrees = 0.f;
};

/** Cookable enemy content for the fox-masked hunter (animation-r04 on the tripo-rig-r02 body). */
UCLASS(BlueprintType)
class YORIMICHI_API UFoxHunterDefinition : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<USkeletalMesh> Mesh;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UBlendSpace> Locomotion;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TMap<FName, TObjectPtr<UAnimSequence>> Actions;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FFoxHunterClip> Clips;
    // Authored travel speeds of the in-place loops (cm/s at the export scale).
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float CreepSpeed = 59.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float RunSpeed = 591.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float CapsuleRadius = 26.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float CapsuleHalfHeight = 86.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float SoleHeight = .65f;
    UAnimSequence* FindAction(FName Name) const;
    const FFoxHunterClip* FindClip(FName Role) const;
    bool IsComplete() const { return Mesh != nullptr && Locomotion != nullptr && Clips.Num() > 0; }
};

UENUM()
enum class EFoxState : uint8 { Idle, Approach, Stalk, Attack, Recover, Lunge, Retreat, Turn, Hurt, Dead, Withdraw, Return };

/**
 * The fox-masked hunter: Yorimichi's first enemy, fought with the sword set. A small state machine drives it:
 * it idles until the player comes near, runs in, creeps the last stretch, claws and kicks from the authored
 * attack clips (the hit lands inside each clip's window along the striking hand or foot), lunges from mid
 * range, springs back after landing a hit, staggers when struck or parried, and dies on the Death clip. Its
 * strikes reach the player through the sword's parry/dodge/hit contract; the player's blade reaches it through
 * TakeSwordHit. It respawns at its home spot a while after dying, so the fight can be replayed.
 */
USTRUCT()
struct FFoxNetworkState
{
    GENERATED_BODY()
    UPROPERTY() FName Action;
    UPROPERTY() uint32 Serial = 0;
    UPROPERTY() uint32 Encounter = 0;
    UPROPERTY() TObjectPtr<AWandererCharacter> Target;
    UPROPERTY() int32 MaximumHealth = 6;
    UPROPERTY() float Time = 0.f;
    UPROPERTY() float StateTime = 0.f;
    UPROPERTY() float Blend = .16f;
    UPROPERTY() float ServerTime = 0.f;
    UPROPERTY() float Flash = 0.f;
    UPROPERTY() int32 Health = 6;
    UPROPERTY() uint8 State = 0;
    UPROPERTY() bool bLoop = false;
};

UCLASS()
class YORIMICHI_API AFoxHunter : public ACharacter
{
    GENERATED_BODY()
public:
    AFoxHunter(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    virtual void BeginPlay() override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    virtual void Tick(float Dt) override;
    // ---- combat contract with the player's sword
    /** The player's blade landed: Strength 1 light, 2 charged, 3 full charge. */
    void TakeSwordHit(int32 Strength, AActor* From);
    bool IsAlive() const { return State != EFoxState::Dead; }
    int32 GetHealth() const { return Health; }
    static constexpr int32 MaxHealth = 6;
    // ---- animation interface (read by the native graph)
    const UFoxHunterDefinition* GetDefinition() const { return Definition; }
    FName GetAnimationAction() const { return AnimationAction; }
    uint32 GetActionSerial() const { return ActionSerial; }
    float GetActionBlendTime() const { return ActionBlendTime; }
    float GetActionTime() const { return ActionTime; }
    bool DoesActionLoop() const { return bActionLoops; }
    bool IsReady() const { return Definition != nullptr && Definition->IsComplete(); }
    // ---- state, telemetry and the harness
    EFoxState GetState() const { return State; }
    FString StateName() const;
    FString LastEvent() const { return Event; }
    float LastEventAge() const { return Clock - EventTime; }
    bool IsEngaged() const { return State != EFoxState::Idle && State != EFoxState::Dead && State != EFoxState::Return; }
    void SetHome(const FVector& Where, float Yaw) { Home = Where; HomeYaw = Yaw; }
    /** Harness: fix the random stream so attack choices repeat. */
    void SetSeed(int32 Seed) { Rand.Initialize(Seed); }
    /** Harness: the next attack uses this clip (None = the weighted choice). */
    void ForceNextAttack(FName Role) { ForcedAttack = Role; }
    /** Harness: never attack or lunge (approach and stalk only). */
    void SetPassive(bool bValue) { bPassive = bValue; }
    int32 StrikesLanded = 0, StrikesParried = 0, StrikesDodged = 0, StrikesMissed = 0, HitsTaken = 0, Deaths = 0, Attacks = 0;
    FVector StrikePoint() const;
    static constexpr float NoticeRadius = 900.f, ForgetRadius = 2600.f, RunUntil = 250.f, AttackRange = 110.f, StopDistance = 92.f, ChaseSpeed = 480.f, StalkSpeed = 75.f;
    static constexpr float ClawDamage = 20.f, KickDamage = 30.f, DeadBodyTime = 4.3f, RespawnTime = 10.f;
    // Death: the body lands (DeathFallTime), then burns away into embers from DissolveStart over DissolveTime.
    static constexpr float DeathFallTime = 1.95f, DissolveStart = 2.45f, DissolveTime = 1.7f;
private:
    UPROPERTY(ReplicatedUsing=OnRep_NetworkState) FFoxNetworkState NetworkState;
    UFUNCTION() void OnRep_NetworkState();
    void PublishNetworkState();
    void PresentNetworkState();
    double LastNetworkPublication = -1.;
    void EngageNetworkEncounter();
    void PresentDeath();
    bool bHealthScaled = false;
    int32 EncounterHealth = MaxHealth;
    void Enter(EFoxState Next, FName Clip, float Blend, bool bLoop = false);
    void SetAction(FName Action, bool bLoop, float Blend);
    void AdvanceAction(float Dt);
    void StartAttack();
    void SweepStrike();
    void FaceYaw(float TargetYaw, float RateDegPerSec, float Dt);
    void MoveToward(const FVector& Target, float Speed);
    void Note(const FString& Text);
    const FFoxHunterClip* Clip(FName Role) const;
    void Die();
    void Respawn();
    void SetCollisionAlive(bool bAlive);
    UPROPERTY() TObjectPtr<UFoxHunterDefinition> Definition;
    UPROPERTY() TObjectPtr<AWandererCharacter> Target;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Paint;
    EFoxState State = EFoxState::Idle;
    FName AnimationAction, CurrentClip, ForcedAttack;
    uint32 ActionSerial = 0;
    float ActionTime = 0.f, ActionDuration = 0.f, ActionBlendTime = .16f;
    bool bActionLoops = false, bPassive = false, bStruckThisAttack = false, bKnockedPlayerDown = false, bComboFollowUp = false, bSwipeCue = false, bDeathCues[3] = { false, false, false };
    void Cue(FName Sound, const FVector& At, float Volume = 1.f);
    void DashDust();
    float StateTime = 0.f, Cooldown = 0.f, Poise = 2.f, NoticeBlock = 0.f, Flash = 0.f, StalkClock = 0.f, Clock = 0.f, EventTime = -100.f;
    int32 Health = MaxHealth, ConsecutiveAttacks = 0;
    FVector Home = FVector::ZeroVector; float HomeYaw = 0.f, RootMotionScale = 1.f;
    FString Event;
    TArray<FVector> PreviousStrike;
    FRandomStream Rand;
    friend struct FJapanEnemyProbe;
};
