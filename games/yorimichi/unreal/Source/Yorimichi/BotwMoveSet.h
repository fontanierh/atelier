#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "BotwMoveSet.generated.h"

class AWandererCharacter;
class FJsonObject;
class UStaticMeshComponent;
class USkeletalMeshComponent;
class UAnimSequence;
class UAtelierTrail;
struct FHitResult;

/** One action of a move set (assets/characters/botw/moves.py `record`): where its clip starts and ends, the rate it plays
 *  at and its windows, all in clip seconds (-1 when it has none), and for a driven clip the root path it moves along. */
struct FBotwMove
{
    FName Name;
    float Length = 0.f, Rate = 1.f, Start = 0.f, End = 0.f, Blend = 0.f;
    float Speed = 0.f;   // a locomotion loop's ground speed (cm/s), from its root path
    // From `Input` the next press is acted on; from `Cancel` anything may follow; at `Idle` it is over; at `Bind` and
    // `Unbind` the equipment goes to the hands and back.
    float Input = -1.f, Cancel = -1.f, Idle = -1.f, Bind = -1.f, Unbind = -1.f;
    bool bLoop = false;
    TArray<FVector2f> Active, Guard;   // hits land; a strike is parried
    // Driven: per 30 fps frame, forward, right and up (cm) and the turn (degrees, positive right) from the clip's start.
    TArray<FVector4f> Path;
    FVector4f PathAt(float SourceTime) const;
    bool InWindow(const TArray<FVector2f>& Windows, float SourceTime) const;
};

/** What the character is doing with its body: the move set's state machine has one branch for each. */
enum class EBotwMoveMode : uint8 { Ground, Air, Glide, Climb, Swim };

/**
 * The player's move set, Cairo's and Link's merged (the roster's `moves` record, assets/characters/botw/moves.toml, or
 * Cairo's retargeted copy, Content/Data/cairo/botw.json): Breath of the Wild's jumping, landing and sprint, Cairo's
 * double jump (his own somersault, or a tucked one turned by the game), the side hop and backflip, the paraglider,
 * climbing any steep surface, swimming, and sword combat (the four-cut combo, the charged spin, the dash, jump and plunge
 * attacks, the sneakstrike, the guard and parry, lock-on strafing, the flurry rush after a perfect dodge, hit reactions).
 * The shield is optional (the "Shield" setting, off by default): with it the shield guards and parries, without it the
 * sword does, on BOTW's sword-only clips and the same timelines. There is no dash. The "Move set" setting can also bring
 * back the legacy BOTW set (SetLegacy: no double jump, the shield always carried) or Cairo's legacy moves (no
 * UBotwMoveSet at all; ACairoCharacter). It drives the character's action clip,
 * timing every action by BOTW's own action timelines, and moves the capsule itself while gliding, climbing and swimming
 * (UJapanCharacterMovement's custom mode). It names actions and equipment slots only, never a character's bones or
 * clips, so any character with the actions and a carry bone map can use it. Stamina is BOTW's: 1000 to a ring.
 */
UCLASS()
class YORIMICHI_API UBotwMoveSet : public UObject
{
    GENERATED_BODY()
public:
    /** The custom movement mode the move set's own physics runs in (the skate board's is 2). */
    static constexpr uint8 MovementMode = 3;
    /** Read the record and attach the equipment; false when the character lacks an action the set needs. */
    bool Initialize(AWandererCharacter* Owner, const TSharedPtr<FJsonObject>& Record);
    /** Per frame, in place of the character's own action bookkeeping. */
    void Advance(float Dt);
    /** UJapanCharacterMovement::PhysCustom in MovementMode. */
    void Phys(float Dt, int32 Iterations);
    /** UJapanCharacterMovement::CalcVelocity on the ground and in the air: a driven attack or a hop sets the velocity. */
    bool OverrideVelocity(FVector& Velocity) const;
    /** The move set turns the character itself (lock-on, gliding, climbing, driven clips). */
    bool ControlsRotation() const;
    void Landed(const FHitResult& Hit);
    /** UJapanCharacterMovement::HandleImpact: the capsule ran into something (a steep slope it walks into is a wall). */
    void Impact(const FHitResult& Hit);
    /** Stand on the ground with nothing in hand or underway: travel, the board, the sailboat, the character switch. */
    void Reset();
    /** A button through the character's input handler: "jump", "jump_release", "dodge", "attack", "attack_release",
     *  "guard", "guard_release", "weapon", "crouch", "dash". True when the move set took it. */
    bool Press(FName Button);
    /** The "Move set" setting: 0 merged (the default), 1 Cairo's legacy moves, 2 the legacy BOTW set; -moveset=merged,
     *  cairo or botw on the command line decides instead. */
    enum EChoice : int32 { Merged = 0, LegacyCairo = 1, LegacyBotw = 2 };
    static int32 Chosen();
    /** The legacy BOTW set: no double jump, the shield always carried, the guard button only locking on when sheathed. */
    void SetLegacy(bool bOn);
    bool IsLegacy() const { return bLegacy; }
    /** The "Shield" setting: carry the shield and guard and parry with it, or leave it off and use the sword. */
    void SetShield(bool bOn);
    bool HasShield() const { return bShield || bLegacy; }
    /** The menu opened: buttons held down are let go without acting. */
    void DropHolds() { bAttackHeld = bGuardHeld = false; }
    /** An enemy strike: 0 hit, 1 parried, 2 dodged, 3 absorbed (guarded or recovering) (UWandererSwordComponent's contract). */
    int32 IncomingStrike(AActor* Source, float Damage, const FVector& From);

    // Queries for the character, its animation graph, the HUD and the QA scenarios.
    EBotwMoveMode GetMode() const { return Mode; }
    FString ModeName() const;
    bool LocksMovement() const;
    bool CanSprint() const { return Mode == EBotwMoveMode::Ground && !bLocked && !bGuardHeld && !bCharging; }
    /** Stamina recovers only standing on the ground (BOTW's EnergyAutoRecoverInAir is 0). */
    bool HoldsStamina() const { return Mode != EBotwMoveMode::Ground || bCharging; }
    bool IsArmed() const { return bArmed; }
    bool IsGuarding() const { return bGuardHeld && bArmed; }
    bool IsSwordGuarding() const { return IsGuarding() && !HasShield(); }
    bool IsLocked() const { return bLocked; }
    bool IsDown() const { return bDown; }
    bool InFlurry() const { return FlurryTime > 0.f; }
    /** Carry layers of the animation graph: the sword arm's pose over locomotion, and the raised shield. */
    float SwordCarryWeight() const { return SwordCarry; }
    float GuardWeight() const { return GuardCarry; }
    float SwordGuardWeight() const { return SwordGuardCarry; }
    /** The guard pose's off-hand arm: a two-handed guard (Cairo's bokken) holds the grip; a one-handed one (Link's
     *  sword-only guard) leaves that arm free, not holding up a shield that is not there. */
    float SwordGuardOffHandWeight() const { return GetParam(TEXT("TwoHandedGuard")) > .5f ? SwordGuardCarry : 0.f; }
    /** Without the shield, the off hand's arm swings free (locomotion) over sword work instead of the clips' shield pose. */
    float FreeArmWeight() const { return FreeArm; }
    /** A two-handed hold (Cairo's bokken guard, parry and recoil) on the move set's sword: how much the off hand is put on
     *  its handle, and where that is from the sword hand's bone (one hand's width along the handle toward the pommel). */
    float TwoHandGripWeight() const { return TwoHandGrip; }
    FVector TwoHandGripOffset() const { return GripOffset; }
    float GetMaxWalkSpeed(float Default) const;
    float GetParam(const TCHAR* Key, float Default = 0.f) const;
    const FBotwMove* Find(FName Name) const { return Moves.Find(Name); }
    AActor* GetTarget() const { return Target.Get(); }
    int32 HitsLanded() const { return HitCount; }
    int32 Parries() const { return ParryCount; }
    int32 Dodges() const { return DodgeCount; }
    int32 DoubleJumps() const { return DoubleJumpCount; }
    /** Live and QA: the facts the scenarios check, as JSON. */
    FString Describe() const;

private:
    struct FSlot
    {
        FName Hand, Back;
        FTransform Held, Carry;   // relative to the hand and back bones
        bool bInHand = false;
    };
    UPROPERTY() TObjectPtr<AWandererCharacter> Character;
    UPROPERTY() TMap<FName, TObjectPtr<UStaticMeshComponent>> Props;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Glider;
    UPROPERTY() TObjectPtr<UAnimSequence> GliderClip;
    UPROPERTY() TObjectPtr<UAtelierTrail> BladeTrail;
    TMap<FName, FBotwMove> Moves;
    TMap<FString, float> Params;
    TMap<FName, FSlot> Slots;
    TWeakObjectPtr<AActor> Target;

    EBotwMoveMode Mode = EBotwMoveMode::Ground;
    // Input
    bool bAttackHeld = false, bGuardHeld = false, bJumpHeld = false;
    float AttackPressTime = -100.f, AttackBuffer = 0.f, JumpBuffer = 0.f, Clock = 0.f;
    // Ground and air
    bool bJumped = false, bLocked = false, bArmed = false, bRunFoot = false, bAttackAfterDraw = false;
    float SinceGrounded = 0.f, FallSpeed = 0.f, FallStartZ = 0.f, NoClimb = 0.f, PushTime = 0.f, LockYaw = 0.f;
    FVector HopVelocity = FVector::ZeroVector;
    int32 Combo = 0;
    // The double jump: once per time in the air. A tucked one (no somersault clip) turns the mesh about its middle.
    bool bAirJumpUsed = false;
    float FlipTime = -1.f, FlipAngle = 0.f;
    FVector FlipPivot = FVector::ZeroVector;   // in the capsule's frame
    float FlipHips = 0.f, FlipLift = 0.f, FlipSettle = 0.f;   // the hips' height (mesh frame) at take-off; the mesh's lift
    FQuat MeshBaseRotation = FQuat::Identity;
    bool bMeshTurned = false;
    // Driven clips: where the clip started and how its path maps onto the world.
    FVector DriveOrigin = FVector::ZeroVector, DriveForward = FVector::ForwardVector, DriveRight = FVector::RightVector, DriveUp = FVector::UpVector;
    FVector DriveScale = FVector::OneVector;   // fitted to a ledge: forward, right, up
    FVector DriveMesh = FVector::ZeroVector;   // a placed drive: the mesh's world offset from the capsule at the clip's start
    float DriveYaw = 0.f, DrivePrevious = 0.f;
    bool bDriving = false, bDriveSweep = true;
    FVector DriveVelocity = FVector::ZeroVector;
    // The mesh's offset in the capsule: the lean into a climbed wall, a pose and capsule that disagree for a moment (into
    // and out of the water), and a placed drive's start, each eased out.
    FVector MeshBase = FVector::ZeroVector, MeshOffsetStart = FVector::ZeroVector, MeshDriveLocal = FVector::ZeroVector;
    float MeshOffsetTime = 0.f, MeshOffsetLength = 0.f;
    bool bMeshOffset = false;
    // Gliding
    float GlideSpeed = 0.f, GlideYaw = 0.f, GlideTime = 0.f, GlideTurn = 0.f;
    bool bGlideBrake = false, bGliderShown = false;
    // Climbing
    FVector WallNormal = FVector::ForwardVector, WallPoint = FVector::ZeroVector;
    float ClimbShift = 0.f, ClimbShiftTarget = 0.f, ClimbStill = 0.f;
    // A climb direction that has stopped getting anywhere (an overhang, a corner) holds on instead.
    FVector ClimbProbeFrom = FVector::ZeroVector;
    float ClimbProbe = 0.f;
    int32 ClimbBlocked = -1;
    FHitResult LastImpact;
    float SinceImpact = 1.f;
    // Swimming
    float WaterSurface = 0.f, SwimSpeed = 0.f, SwimDashTime = 0.f, SwimYaw = 0.f;
    FVector SafeShore = FVector::ZeroVector;
    bool bHasSafeShore = false;
    // Combat
    bool bShield = false, bLegacy = false;
    float FreeArm = 0.f, TwoHandGrip = 0.f;
    FVector GripOffset = FVector::ZeroVector;
    // The paraglider's grips: the bar's two (its own frame) and the hands' two (each in its hand bone's frame); gliding,
    // the bar is fitted to both hands every frame, so it banks with them and neither lets go.
    FTransform GliderHeld = FTransform::Identity;
    FVector BarGrip[2] = { FVector::ZeroVector, FVector::ZeroVector }, HandGrip[2] = { FVector::ZeroVector, FVector::ZeroVector };
    FName GripBone[2];
    float GliderGripWeight = 0.f;
    bool bBarKnown = false;
    // A cut's step in toward the enemy it is aimed at (BOTW's attack homing), and the reach a cut's arc counts.
    TWeakObjectPtr<AActor> LungeTarget;
    float LungeTime = 0.f, LungeStand = 0.f;
    float ArcEnd = -1.f;   // a homing cut's contact lasts to here (clip seconds): past its swing, until it has closed in
    float SwordCarry = 0.f, GuardCarry = 0.f, SwordGuardCarry = 0.f, ChargeTime = 0.f, Invulnerable = 0.f, FlurryTime = 0.f, JustAvoid = 0.f, DownTime = 0.f;
    bool bCharging = false, bFullCharge = false, bDown = false, bSwung = false;
    int32 HitCount = 0, ParryCount = 0, DodgeCount = 0, DoubleJumpCount = 0, Strength = 1;
    // Effects: the sprint's dust and speed lines, the glider's wind.
    float SprintFX = 0.f, GlideFX = 0.f;
    bool bWasSprinting = false;
    TSet<TWeakObjectPtr<AActor>> HitThisSwing;
    TArray<FVector> PreviousBlade;
    FVector BladeBase = FVector::ZeroVector, BladeTip = FVector::ZeroVector;   // in the sword mesh's frame
    FName LastPlayed;

    // Actions
    bool Has(FName Name) const { return Moves.Contains(Name); }
    const FBotwMove* Current() const;
    FName CurrentName() const;
    float SourceTime() const;
    bool Playing(FName Name) const;
    bool Over() const;
    /** Where the stick takes over again: the cancel point, else the idle point, else the end. */
    static float FreeAt(const FBotwMove& M);
    /** A locking action (an attack, a hop, a reaction, a climb or swim transition) before its free point. */
    bool Busy() const;
    /** Play a move from its timeline's start (or StartAt in clip seconds), at its timeline's rate times Speed. */
    void Play(FName Name, float Blend = -1.f, float StartAt = -1.f, float Speed = 1.f);
    /** Switch between directional loops keeping the phase. */
    void PlayLoop(FName Name, float Blend = .2f);
    void Stop(float Blend = .16f);
    int32 StrengthOf(FName Name) const;
    /** Move along the playing clip's root path from here; Fit scales it (forward, right, up) to a ledge, and MeshFrom is
     *  the mesh's world offset from the capsule at the start of a placed drive (bSweep false). */
    void BeginDrive(bool bSweep, const FVector& Fit = FVector::OneVector, const FVector& MeshFrom = FVector::ZeroVector);
    void AdvanceDrive(float Dt);
    FVector WorldPath(const FVector4f& P) const;
    float DriveProgress() const;

    // Branches
    void AdvanceGround(float Dt);
    void AdvanceAir(float Dt);
    void AdvanceGlide(float Dt);
    void AdvanceClimb(float Dt);
    void AdvanceSwim(float Dt);
    void AdvanceDown(float Dt);
    void AdvanceCombat(float Dt);
    void AdvanceFlurry();
    void AdvanceEquipment(float Dt);
    void AdvanceMeshOffset(float Dt);
    void AdvanceEffects(float Dt);
    void AdvanceGliderGrip(float Dt);
    /** A blow's arc in front: anything targetable within the blade's reach and the cut's arc counts, as in BOTW. */
    void SweepArc();
    /** The blade's length in the world (the sword mesh's grip to tip, at its scale). */
    float BladeLength() const;
    /** How far the hips have drawn up into the tuck since take-off (capsule cm): the mesh rises that much. */
    float HipLift() const;
    void PhysGlide(float Dt);
    void PhysClimb(float Dt);
    void PhysSwim(float Dt);

    // Transitions
    bool CanJump() const;
    bool CanDodge() const;
    bool CanGlide() const;
    bool CanDoubleJump() const;
    void StartJump();
    void StartDoubleJump();
    void AdvanceDoubleJump(float Dt);
    void StartHop();
    void OpenGlider();
    void CloseGlider(bool bLanding);
    void StartClimb(const FHitResult& Wall, bool bFromAir);
    void LeaveClimb(bool bFall);
    bool TryClimbTop();
    void StartSwim();
    void LeaveSwim(const FVector& Stand);
    bool TrySwimOut(const FHitResult& Wall);
    void StartAttack();
    void StartCut(int32 Index);
    void Face(float Range);
    void Strike(AActor* Victim, int32 Power, const FVector& At, const FVector& Direction);
    void TakeHit(float Damage, const FVector& From, bool bHeavy, AActor* Source, bool bReact);
    void SetArmed(bool bNow);
    void Attach(FName Slot);
    void ShowGlider(bool bShow);
    void EaseMesh(const FVector& From, float Seconds);

    // World queries
    FVector Wish() const;   // the stick as a world direction (camera-relative), length 0..1
    bool Trace(const FVector& From, const FVector& To, FHitResult& Hit) const;
    bool Blocked(const FVector& Center) const;   // the capsule does not fit there
    bool Climbable(const FHitResult& Hit) const;
    bool FindWall(const FVector& Direction, FHitResult& Hit, float Up = 0.f, float Side = 0.f, float Reach = 0.f) const;
    void ClimbBasis(FVector& Forward, FVector& Right, FVector& Up) const;
    bool WaterAt(const FVector& Where, float& Surface) const;
    AActor* FindTarget(float Range, float Cone) const;
    bool IsTargetable(AActor* Actor) const;
    bool IsUnawareTarget(AActor* Actor) const;
    void SweepBlade();
    void BladePoints(TArray<FVector>& Out) const;
    /** Where a guard meets a blow: the shield, or without it the sword's blade. */
    FVector GuardPoint() const;
    /** BOTW's metres to the character's centimetres: the record's BodyScale, else the mesh's scale. */
    float Scale() const;
    float Gravity() const;
    float Feet() const;
    float HalfHeight() const;
    float Reach() const;
    float BodyHold() const;
    float HoldDistance() const;
    float SwimHang() const;
    void UseStamina(float Rings);
    bool HasStamina() const;
};
