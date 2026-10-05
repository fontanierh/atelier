#pragma once
#include "CoreMinimal.h"
#include "WandererCharacter.h"
#include "SwordTrainer.generated.h"

class AJapanWorld;
class SWidget;
class FJsonObject;

/** How hard Kaede pushes: the three levels the player picks when asking her to train (docs/SWORD_TRAINER.md). */
struct FTrainerStyle
{
    const TCHAR* Name;
    float Reaction;        // seconds before she answers a blow she sees coming
    float Parry, Dodge, Guard;   // how she meets a blow: parry it, hop away, guard it (the rest land)
    float PerfectDodge;    // a hop timed into the flurry rush
    float Aggression;      // chances a second to start an attack when ready
    int32 MaxCombo;        // cuts in a row
    float Recovery;        // seconds she stands open after her own attack
    float Charge, DashCut, JumpCut, DoubleJump, Feint;   // shares of her openings (the rest are combos)
    float Damage;          // her blows' share of the full sparring damage
    float Strafe;          // circling: 0 walks, 1 runs
};

/**
 * Kaede, the sword teacher of Momiji Hamlet: ask her (Interact) and she spars with the player at one of three levels,
 * with the sword or the sword and shield, each side's shield chosen in her menu. She is a person in the game's own
 * body (AWandererCharacter, IsNpc) playing the player's merged move set (UBotwMoveSet, her retargeted copy of Link's
 * clips with Cairo's double jump and two-handed guard): an AI presses the same buttons and holds the same stick a
 * player does, so every move she makes is one the player can make, and the move set's guard, parry, dodges, flurry
 * rush and hit reactions answer both sides alike. A bout ends when either is knocked down at no health.
 */
UCLASS()
class YORIMICHI_API ASwordTrainer : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ASwordTrainer(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual bool IsNpc() const override { return true; }
    virtual bool IsSparringWith(const AActor* Other) const override;
    virtual float SparringDamage(int32 Power) const override;

    /** Her place in Momiji Hamlet (the village record's offset carries the authored spot); -notrainer leaves her out. */
    static ASwordTrainer* SpawnInVillage(AJapanWorld* World, const TSharedPtr<FJsonObject>& Village);
    static ASwordTrainer* Find(const UObject* WorldContext);
    /** The player's Interact: talks to her when she is near and free (her menu); false when she is not there. */
    static bool TryInteract(AWandererCharacter* Player);
    /** Move her home (a ground point, UE cm) and the way she waits there; ends a bout. */
    void PlaceAt(const FVector& Ground, float Yaw);

    enum class EBout : uint8 { Home, Talking, Ready, Fighting, Over, Return };
    EBout GetBout() const { return Bout; }
    FString BoutName() const;
    /** Start a bout with Player: Level 0 gentle, 1 steady, 2 master; her shield and the player's (the "Shield" setting). */
    bool StartBout(AWandererCharacter* Player, int32 Level, bool bOwnShield, bool bPlayerShield);
    void EndBout(const FString& Why);
    void OpenMenu(AWandererCharacter* Player);
    void CloseMenu();
    bool IsMenuOpen() const { return Menu.IsValid(); }

    // HUD and live.
    bool CanTalk(const AWandererCharacter* Player) const;
    int32 GetLevel() const { return Level; }
    const FTrainerStyle& GetStyle() const;
    float GetHealthFraction() const;
    bool HasOwnShield() const { return bOwnShield; }
    /** The line under her bar ("Ready...", "Begin!", her words after a bout) and how visible it is. */
    FString GetCallout(float& Alpha) const;
    int32 GetWins() const { return Wins; }
    int32 GetLosses() const { return Losses; }
    FString Describe() const;
    /** Live and QA: what her brain is doing ("approach", "combo", "parry"...). */
    FString GetIntent() const { return Intent; }
    /** QA: make her open with this attack next ("combo", "charge", "dash", "jump", "double", "feint"); empty clears. */
    void ForceNext(const FString& Attack) { Forced = Attack; }
    /** QA: make her meet the next blow this way ("parry", "dodge", "perfect", "guard", "take"); empty clears. */
    void ForceDefence(const FString& Defence) { ForcedDefence = Defence; }
    /** Counters: how she met the player's blows, and her own blows that landed. */
    TMap<FString, int32> Counts;

private:
    EBout Bout = EBout::Home;
    TWeakObjectPtr<AWandererCharacter> Opponent;
    FVector Home = FVector::ZeroVector;
    float HomeYaw = 0.f;
    int32 Level = 1, Wins = 0, Losses = 0;
    bool bOwnShield = false;
    float BoutTime = 0.f, CalloutTime = 0.f;
    FString Callout;
    TSharedPtr<SWidget> Menu;
    int32 MenuLevel = 1;
    bool bMenuOwnShield = false;

    // The brain: what she holds and presses, like a player's hands.
    FString Intent = TEXT("home"), Forced, ForcedDefence;
    float Think = 0.f, IntentTime = 0.f, Cooldown = 0.f, StrafeSign = 1.f, StrafeSwitch = 0.f, PressGap = 0.f, HoldFor = 0.f;
    int32 CombosLeft = 0;
    bool bGuardDown = false, bAttackDown = false, bAirStep = false;
    FRandomStream Dice;
    // The player's blow she is watching, and how she will meet it (decided once, after her reaction time).
    FName SeenAction;
    float SeenTime = -1.f, SeenFor = 0.f;
    FString Answer;
    bool bAnswered = false;

    void Say(const FString& Line, float Seconds = 2.5f) { Callout = Line; CalloutTime = Seconds; }
    void SetIntent(const FString& Name) { if (Intent != Name) { Intent = Name; IntentTime = 0.f; } }
    void Hold(FName Button, bool bDown);
    void Press(FName Button);
    void Drive(const FVector2D& Stick, int32 Gait);
    void FaceToward(const FVector& Where, float Dt);
    void ReleaseAll();
    void Restore(AWandererCharacter* Who);

    void AdvanceHome(float Dt);
    void AdvanceReady(float Dt);
    void AdvanceFight(float Dt);
    void AdvanceOver(float Dt);
    void AdvanceReturn(float Dt);
    /** Watch the opponent's blow; true while she is answering it (the rest of the brain waits). */
    bool Defend(float Dt, float Distance);
    /** Start one of her attacks, by the level's shares (or the forced one). */
    void Open(float Distance);
    /** Carry on with the attack under way; false when it is over. */
    bool Press_Attack(float Dt, float Distance);
};
