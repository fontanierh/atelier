#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BotwCreature.generated.h"

class UCapsuleComponent;
class USkeletalMeshComponent;
class UAnimSequence;
class FJsonObject;
class AWandererCharacter;

USTRUCT()
struct FBotwCreatureNetState
{
    GENERATED_BODY()
    UPROPERTY() FString SpecName;
    UPROPERTY() FName Clip;
    UPROPERTY() uint32 Serial = 0;
    UPROPERTY() float Began = 0.f;
    UPROPERTY() float Rate = 1.f;
    UPROPERTY() bool bLoop = false;
    UPROPERTY() uint8 Mode = 0;
    UPROPERTY() uint8 Phase = 0;
    UPROPERTY() int32 Health = 3;
};

/** One character of Content/Data/botw/roster.json (import_botw.py): its mesh, clips by name, and the clip each role plays. */
struct FBotwSpec
{
    FString Name, Label;
    FSoftObjectPath Mesh;
    float MeshYaw = -90.f, Scale = 1.f, HeightCm = 170.f, RadiusCm = 40.f, WalkSpeed = 0.f, RunSpeed = 0.f;   // at Scale
    TMap<FName, FSoftObjectPath> Clips;
    TMap<FName, bool> Loops;
    TMap<FName, FName> Roles;   // idle, walk, run, notice, angry, battle, attack, hit, down, getup, dance, sleep, talk
    /** A playable character's move set (moves.py `record`, read by UBotwMoveSet); null for the others. */
    TSharedPtr<FJsonObject> Moves;
    /** The roster, loaded once; empty when the BOTW characters have not been built (assets/characters/botw/README.md). */
    static const TMap<FString, FBotwSpec>& All();
    static const FBotwSpec* Find(const FString& Name);
};

UENUM()
enum class EBotwMode : uint8
{
    Idle,       // the idle role, on the spot
    Showcase,   // every clip in turn
    Wander,     // walk between random points around home, resting between
    Camp,       // hostile: notices the player, chases, attacks; sword hits stagger it and knock it down
    Scripted,   // only what Play and MoveTo ask
};

/**
 * A BOTW character in the world: a skeletal mesh playing its baked clips, kept on the ground by a trace, with a capsule
 * the sword sweeps hit (WandererSword.cpp, BotwMoveSetCombat.cpp). In camp mode it strikes a player with a move set, who can
 * guard, parry or dodge it; a crouched player is noticed only close by and in front, and can sneakstrike it. Spawned by
 * the live verbs (YorimichiLive BotwSpawn and friends), which the demo films use.
 */
UCLASS()
class YORIMICHI_API ABotwCreature : public AActor
{
    GENERATED_BODY()
public:
    ABotwCreature();
    /** Spawn `Name` standing at `Ground` (a point on the ground), facing `Yaw`. Null when the roster lacks it. */
    static ABotwCreature* SpawnAt(UWorld* World, const FString& Name, const FVector& Ground, float Yaw, EBotwMode Mode);

    virtual void Tick(float Dt) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

    /** Play a clip by name, or by role ("role:attack"); returns its length in seconds (0 when unknown). */
    float Play(const FString& ClipOrRole, bool bLoop, float Rate = 1.f, float Blend = .2f);
    /** Walk (or run) to a ground point, then go back to the mode's own behaviour. */
    void MoveTo(const FVector& Ground, bool bRun);
    void SetMode(EBotwMode NewMode);
    void TakeSwordHit(int32 Strength, AActor* From);
    bool IsDown() const { return Phase == EPhase::Down; }
    /** It has noticed the player (a sneakstrike needs it unaware). */
    bool IsAlerted() const { return Phase == EPhase::Notice || Phase == EPhase::Chase || Phase == EPhase::Attack || Phase == EPhase::Hit; }
    const FBotwSpec& Spec() const { return Data; }
    FString CurrentClip() const { return Current.ToString(); }
    USkeletalMeshComponent* GetMesh() const { return Mesh; }

private:
    UPROPERTY(ReplicatedUsing=OnRep_NetworkState) FBotwCreatureNetState NetworkState;
    UPROPERTY() TObjectPtr<AWandererCharacter> CombatTarget;
    UFUNCTION() void OnRep_NetworkState();
    void PublishNetworkState();
    void PresentNetworkState();
    double ClipBegan = 0.;
    float ClipRate = 1.f;
    uint32 ClipSerial = 0, AppliedClipSerial = 0;
    bool bClipLoop = false, bHealthScaled = false;
    void EngageNetworkEncounter();
    bool bReturningFromEncounter = false;
    enum class EPhase : uint8 { Rest, Moving, Action, Notice, Chase, Attack, Hit, Down, GetUp };
    void Initialize(const FBotwSpec& Spec, EBotwMode StartMode);
    UAnimSequence* Clip(FName Name) const;
    FName Role(FName RoleName) const { const FName* C = Data.Roles.Find(RoleName); return C ? *C : NAME_None; }
    float PlayRole(FName RoleName, bool bLoop, float Rate = 1.f);
    void Rest();
    void Steer(const FVector& Target, float Speed, float Dt);
    void Ground();
    void Think(float Dt);

    UPROPERTY() TObjectPtr<UCapsuleComponent> Capsule;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Mesh;
    UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> Loaded;
    FBotwSpec Data;
    EBotwMode Mode = EBotwMode::Idle;
    EPhase Phase = EPhase::Rest;
    FName Current;
    FVector Home = FVector::ZeroVector, Target = FVector::ZeroVector;
    bool bRunning = false;
    float PhaseLeft = 0.f, PhaseTotal = 0.f, Clock = 0.f, AttackCooldown = 0.f;
    bool bStruck = false;   // this attack has struck (or missed) the player
    FVector Knockback = FVector::ZeroVector;   // a blow's shove (cm/s), slowing to a stop
    // BOTW lays a downed creature on its back itself: its down clips stand the lying pose on end. The mesh is tipped back
    // about its feet by as much as the pose's head stands above its standing height (so the getup rises out of it).
    FTransform MeshRest = FTransform::Identity;
    float StandHead = 0.f, LieWeight = 0.f;
    void AdvanceLying(float Dt);
    void Strike(APawn* Player);
    int32 Showcased = 0, Health = 3;
    TArray<FName> ShowcaseOrder;
};
