#include "JapanEnemyQA.h"
#include "AtelierData.h"
#if !UE_BUILD_SHIPPING
#include "FoxHunter.h"
#include "BotwMoveSet.h"
#include "JapanSession.h"
#include "JapanCombatResolver.h"
#include "JapanEncounters.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/World.h"
#include "Engine/NetDriver.h"
#include "Engine/PackageMapClient.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
bool Enabled()
{
    static const bool Value = FParse::Param(FCommandLine::Get(), TEXT("networkenemy"));
    return Value;
}
FString PlayerId(const AWandererCharacter* Player)
{
    const auto* State = Player ? Player->GetPlayerState<AJapanPlayerState>() : nullptr;
    return State ? State->SessionPlayerId : FString();
}
FString ActorId(const AActor* Actor)
{
    const auto* Driver = Actor ? Actor->GetNetDriver() : nullptr;
    if (!Driver || !Driver->GuidCache) return {};
    const FNetworkGUID Guid = Driver->GuidCache->GetNetGUID(Actor);
    return Guid.IsValid() ? Guid.ToString() : FString();
}
bool Write(const FString& File, const TSharedPtr<FJsonObject>& Data)
{
    FString Text;
    FJsonSerializer::Serialize(Data.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    return FFileHelper::SaveStringToFile(Text, *(File + TEXT(".tmp"))) &&
        IFileManager::Get().Move(*File, *(File + TEXT(".tmp")), true, true);
}
TSharedPtr<FJsonObject> Read(const FString& File)
{
    return AtelierReadJson(File);
}
}

// Friendship exposes read-only hunter telemetry; fixture writes only tick enable,
// seed, passive and the existing next-attack selector. It never writes health,
// position, targets or encounter membership.
struct FJapanEnemyProbe
{
    TWeakObjectPtr<UWorld> World;
    TWeakObjectPtr<AFoxHunter> Hunter;
    FString Error;
    uint32 AiTicks = 0, Sweeps = 0;
    bool Paused = false, Resumed = false, NoticeSeen = false, Complete = false;
    FVector PausedPosition = FVector::ZeroVector;
    float PausedClock = 0.f, PausedStateTime = 0.f;
    double Began = 0., PhaseBegan = 0., NextAttack = 0., LastFile = -1., ClawResolved = -1.;
    bool ActorTickWasEnabled = false, MovementTickWasEnabled = false, StopAttacks = false, AttackHeld = false;
    int32 PhaseHealth = -1;
    uint32 Encounter = 0;
    int32 Frames = 0;
    double FrameMin = 100., FrameMax = 0., LastWorldFrame = -1.;
    uint32 QueuedBefore = 0, ResolvedBefore = 0, OverflowBefore = 0, CancelBefore = 0;
    uint32 MissingBefore = 0, FallbackBefore = 0, RejectedBefore = 0;
    void Baseline()
    {
        Frames = 0; FrameMin = 100.; FrameMax = 0.; LastWorldFrame = -1.;
        const auto* Resolver = World->GetSubsystem<UJapanCombatResolver>();
        QueuedBefore = Resolver->Queued; ResolvedBefore = Resolver->Resolved;
        OverflowBefore = Resolver->Overflows; CancelBefore = Resolver->Cancelled;
        const auto* Moves = Guest.IsValid() ? Guest->GetMoves() : nullptr;
        MissingBefore = Moves ? Moves->DefenceMissingSamples() : 0;
        FallbackBefore = Moves ? Moves->DefenceAuthoredFallbacks() : 0;
        RejectedBefore = Moves ? Moves->DefensiveRejectedTimes : 0;
    }
    TWeakObjectPtr<AWandererCharacter> Host, Guest;
    int32 Phase = 0, SeenPhase = -1, InitialMaximum = 0, PreviousHealth = -1;
    int32 HealthChanges = 0, DeathChanges = 0;
    EFoxState PreviousState = EFoxState::Idle;
    FString Identity;
    uint32 PhaseHitStart = 0;
    FString HostId, GuestId;
    FVector Home = FVector::ZeroVector, Axis = FVector::ForwardVector;
    float GuestHealthBefore = 0.f;
    int32 GuestHealthChanges = 0;
    float LastGuestHealth = -1.f;
    TMap<FString, uint32> Attempts, Candidates;
    TArray<TSharedPtr<FJsonValue>> Hits, Claws, Phases, OwnerEdges, BoundActions;
    struct FAttackEdge { uint32 Epoch; uint16 Edge; };
    TMap<FString, FAttackEdge> PendingAttacks;
    TSet<FString> ConsumedAttacks;
    bool MadePassiveAfterClaw = false;
    TSharedPtr<FJsonObject> Setup = MakeShared<FJsonObject>();

    void Initialize(AFoxHunter* Fox);
    bool Tick(const FString& Folder);
    void Drive(AWandererCharacter* Player);
    void SetPhase(int32 Next);
    void Observe(AFoxHunter* Fox);
    void Notice();
    bool PeerMatches(const TSharedPtr<FJsonObject>& Other) const;
    void Fail(const FString& Why) { if (Error.IsEmpty()) Error = Why; }
    bool Owns(const AActor* Actor) const { return Enabled() && Actor && Actor->GetWorld() == World.Get(); }
    TSharedPtr<FJsonObject> Snapshot(AFoxHunter* Fox)
    {
        auto Data = MakeShared<FJsonObject>();
        Data->SetNumberField(TEXT("phase"), Phase);
        Data->SetStringField(TEXT("net_guid"), ActorId(Fox));
        Data->SetNumberField(TEXT("health"), Fox->Health);
        Data->SetNumberField(TEXT("phase_start_health"), PhaseHealth);
        Data->SetNumberField(TEXT("frame_count"), Frames);
        Data->SetNumberField(TEXT("frame_min"), Frames ? FrameMin : 0.);
        Data->SetNumberField(TEXT("frame_max"), FrameMax);
        Data->SetNumberField(TEXT("maximum_health"), Fox->EncounterHealth);
        Data->SetNumberField(TEXT("encounter"), Fox->NetworkState.Encounter);
        Data->SetNumberField(TEXT("state"), uint8(Fox->State));
        Data->SetNumberField(TEXT("action_serial"), Fox->ActionSerial);
        const auto* Resolver = Fox->GetWorld()->GetSubsystem<UJapanCombatResolver>();
        if (Resolver)
        {
            Data->SetNumberField(TEXT("queued"), Resolver->Queued - QueuedBefore);
            Data->SetNumberField(TEXT("resolved"), Resolver->Resolved - ResolvedBefore);
            Data->SetNumberField(TEXT("overflows"), Resolver->Overflows - OverflowBefore);
            Data->SetNumberField(TEXT("cancelled"), Resolver->Cancelled - CancelBefore);
        }
        if (Guest.IsValid() && Guest->GetMoves())
        {
            Data->SetNumberField(TEXT("missing_samples"), Guest->GetMoves()->DefenceMissingSamples() - MissingBefore);
            Data->SetNumberField(TEXT("authored_fallbacks"), Guest->GetMoves()->DefenceAuthoredFallbacks() - FallbackBefore);
            Data->SetNumberField(TEXT("rejected_defence_times"), Guest->GetMoves()->DefensiveRejectedTimes - RejectedBefore);
        }
        Data->SetNumberField(TEXT("ai_ticks"), AiTicks);
        Data->SetNumberField(TEXT("sweep_calls"), Sweeps);
        Data->SetBoolField(TEXT("simulated_proxy"), Fox->GetLocalRole() == ROLE_SimulatedProxy);
        Data->SetBoolField(TEXT("has_controller"), Fox->GetController() != nullptr);
        Data->SetNumberField(TEXT("health_changes"), HealthChanges);
        Data->SetNumberField(TEXT("deaths"), Fox->Deaths);
        Data->SetNumberField(TEXT("guest_health_changes"), GuestHealthChanges);
        Data->SetStringField(TEXT("host_id"), HostId);
        Data->SetStringField(TEXT("guest_id"), GuestId);
        Data->SetStringField(TEXT("error"), Error);
        Data->SetNumberField(TEXT("at"), FPlatformTime::Seconds());
        Data->SetNumberField(TEXT("death_changes"), DeathChanges);
        for (TActorIterator<AWandererCharacter> It(Fox->GetWorld()); It; ++It)
            if (!It->IsNpc() && It->GetSword())
            {
                const FString Id = PlayerId(*It);
                if (Id == GuestId) Data->SetNumberField(TEXT("guest_health"), It->GetSword()->GetHealth());
                if (It->IsLocallyControlled())
                {
                    Data->SetStringField(TEXT("owner_id"), Id);
                    Data->SetNumberField(TEXT("owner_attempts"), Attempts.FindRef(Id));
                    Data->SetNumberField(TEXT("owner_blade_candidates"), Candidates.FindRef(Id));
                    Data->SetNumberField(TEXT("owner_health"), It->GetSword()->GetHealth());
                    Data->SetArrayField(TEXT("owner_attack_edges"), OwnerEdges);
                }
            }
        Data->SetArrayField(TEXT("bound_attack_actions"), BoundActions);
        Data->SetStringField(TEXT("state_name"), Fox->StateName());
        Data->SetStringField(TEXT("scope"), TEXT("Same-machine FPlatformTime observations; phase4 hunter passive: player damage and death replication, not enemy counterattacks"));
        Data->SetNumberField(TEXT("claw_damage"), AFoxHunter::ClawDamage);
        Data->SetNumberField(TEXT("home_x"), Home.X); Data->SetNumberField(TEXT("home_y"), Home.Y); Data->SetNumberField(TEXT("home_z"), Home.Z);
        Data->SetNumberField(TEXT("axis_x"), Axis.X); Data->SetNumberField(TEXT("axis_y"), Axis.Y);
        return Data;
    }
};
static FJapanEnemyProbe Probe;

void JapanEnemyQA::QueuedAttack(AWandererCharacter* Player, uint32 Epoch, uint16 Edge)
{
    if (!Probe.Owns(Player) || !Player->IsLocallyControlled()) return;
    auto Row = MakeShared<FJsonObject>();
    Row->SetStringField(TEXT("player"), PlayerId(Player)); Row->SetNumberField(TEXT("epoch"), Epoch);
    Row->SetNumberField(TEXT("edge"), Edge); Row->SetNumberField(TEXT("phase"), Probe.Phase);
    Probe.OwnerEdges.Add(MakeShared<FJsonValueObject>(Row));
}
void JapanEnemyQA::AcceptedAttack(AWandererCharacter* Player, uint32 Epoch, uint16 Edge)
{
    if (!Probe.Owns(Player) || !Player->HasAuthority()) return;
    Probe.PendingAttacks.Add(PlayerId(Player), {Epoch, Edge});
}
void JapanEnemyQA::StartedCut(AWandererCharacter* Player, bool BufferedPress)
{
    if (!Probe.Owns(Player) || !Player->HasAuthority()) return;
    const FString Id = PlayerId(Player);
    FJapanEnemyProbe::FAttackEdge Pending;
    if (!Probe.PendingAttacks.RemoveAndCopyValue(Id, Pending) || !BufferedPress || Pending.Epoch != Player->GetActivityEpoch()) return;
    const FString Key = FString::Printf(TEXT("%s:%u:%u"), *Id, Pending.Epoch, Pending.Edge);
    if (Probe.ConsumedAttacks.Contains(Key)) { Probe.Fail(TEXT("An accepted attack edge started two cuts")); return; }
    Probe.ConsumedAttacks.Add(Key);
    auto Row = MakeShared<FJsonObject>();
    Row->SetStringField(TEXT("player"), Id); Row->SetNumberField(TEXT("epoch"), Pending.Epoch);
    Row->SetNumberField(TEXT("edge"), Pending.Edge); Row->SetNumberField(TEXT("action"), Player->GetActionSerial());
    Row->SetNumberField(TEXT("phase"), Probe.Phase);
    Probe.BoundActions.Add(MakeShared<FJsonValueObject>(Row));
}
void JapanEnemyQA::BeginHunter(AFoxHunter* Fox)
{
    if (!Enabled() || !Fox || Fox->GetNetMode() == NM_Standalone) return;
    if (Probe.World.Get() != Fox->GetWorld()) { Probe = FJapanEnemyProbe(); Probe.World = Fox->GetWorld(); }
    if (Probe.Hunter.IsValid()) { Probe.Fail(TEXT("Shared-enemy route spawned more than one hunter")); return; }
    Probe.Hunter = Fox;
    Probe.Initialize(Fox);
}
void JapanEnemyQA::AuthorityTick(AFoxHunter* Fox)
{
    if (Probe.Owns(Fox)) ++Probe.AiTicks;
}
void JapanEnemyQA::Sweep(AFoxHunter* Fox)
{
    if (Probe.Owns(Fox)) ++Probe.Sweeps;
}
void JapanEnemyQA::BladeCandidate(AWandererCharacter* Player, AActor* Victim)
{
    if (Probe.Owns(Player) && Victim == Probe.Hunter.Get()) ++Probe.Candidates.FindOrAdd(PlayerId(Player));
}
void JapanEnemyQA::SwordDamage(AFoxHunter* Fox, AActor* Attacker, int32 Power, int32 Before, int32 After)
{
    if (!Probe.Owns(Fox)) return;
    const auto* Player = Cast<AWandererCharacter>(Attacker);
    auto Row = MakeShared<FJsonObject>();
    Row->SetNumberField(TEXT("phase"), Probe.Phase);
    Row->SetStringField(TEXT("player_id"), PlayerId(Player));
    Row->SetNumberField(TEXT("player_action"), Player ? Player->GetActionSerial() : 0);
    Row->SetNumberField(TEXT("player_epoch"), Player ? Player->GetActivityEpoch() : 0);
    for (const auto& Value : Probe.BoundActions)
    {
        const auto Bound = Value->AsObject();
        if (Player && Bound->GetStringField(TEXT("player")) == PlayerId(Player) &&
            Bound->GetNumberField(TEXT("epoch")) == Player->GetActivityEpoch() &&
            Bound->GetNumberField(TEXT("action")) == Player->GetActionSerial()) Row->SetObjectField(TEXT("input"), Bound);
    }
    if (!Row->HasField(TEXT("input"))) Probe.Fail(TEXT("Credited sword action has no accepted owner-input edge"));
    Row->SetStringField(TEXT("enemy_guid"), ActorId(Fox));
    Row->SetNumberField(TEXT("power"), Power);
    Row->SetNumberField(TEXT("before"), Before); Row->SetNumberField(TEXT("after"), After);
    Row->SetNumberField(TEXT("at"), Fox->GetWorld()->GetTimeSeconds());
    const AWandererCharacter* Other = PlayerId(Player) == Probe.GuestId ? Probe.Host.Get() : Probe.Guest.Get();
    Row->SetNumberField(TEXT("other_distance"), Other ? FVector::Dist2D(Other->GetActorLocation(), Fox->GetActorLocation()) : -1.);
    Row->SetNumberField(TEXT("other_speed"), Other ? Other->GetVelocity().Size2D() : -1.);
    if ((Probe.Phase == 1 || Probe.Phase == 2) && (!Other ||
        Row->GetNumberField(TEXT("other_distance")) < 350. || Row->GetNumberField(TEXT("other_speed")) > 5.))
        Probe.Fail(TEXT("Inactive player was not idle and outside blade range at the credited hit"));
    Probe.Hits.Add(MakeShared<FJsonValueObject>(Row));
    if (!Player || !Fox->HasAuthority() || Power <= 0 || Before - After != FMath::Min(Power, Before))
        Probe.Fail(TEXT("Hunter damage was not one attributed authoritative health decrement"));
}
uint32 JapanEnemyQA::Contact(AFoxHunter* Fox, AWandererCharacter* Victim, float Damage)
{
    if (!Probe.Owns(Fox)) return 0;
    auto Row = MakeShared<FJsonObject>();
    Row->SetNumberField(TEXT("serial"), Fox->GetActionSerial());
    Row->SetStringField(TEXT("victim"), PlayerId(Victim));
    Row->SetNumberField(TEXT("damage"), Damage);
    Row->SetNumberField(TEXT("encounter"), Fox->GetWorld()->GetSubsystem<UJapanEncounters>()->Identity(Fox));
    Row->SetNumberField(TEXT("host_distance"), Probe.Host.IsValid() ? FVector::Dist2D(Probe.Host->GetActorLocation(), Fox->GetActorLocation()) : -1.);
    Row->SetNumberField(TEXT("callbacks"), 0);
    Row->SetNumberField(TEXT("at"), Fox->GetWorld()->GetTimeSeconds());
    Row->SetNumberField(TEXT("health_before"), Victim && Victim->GetSword() ? Victim->GetSword()->GetHealth() : -1.f);
    Probe.Claws.Add(MakeShared<FJsonValueObject>(Row));
    if (Probe.Phase != 3 || Probe.Claws.Num() != 1 || PlayerId(Victim) != Probe.GuestId)
        Probe.Fail(TEXT("Unexpected hunter contact phase, count or victim"));
    return Probe.Claws.Num();
}
void JapanEnemyQA::Resolved(uint32 Contact, int32 Outcome)
{
    if (!Enabled() || !Contact || Contact > uint32(Probe.Claws.Num())) return;
    auto Row = Probe.Claws[Contact - 1]->AsObject();
    const int32 Calls = int32(Row->GetNumberField(TEXT("callbacks"))) + 1;
    Row->SetNumberField(TEXT("callbacks"), Calls); Row->SetNumberField(TEXT("outcome"), Outcome);
    if (Probe.Guest.IsValid()) Row->SetNumberField(TEXT("health_after"), Probe.Guest->GetSword()->GetHealth());
    Probe.ClawResolved = FPlatformTime::Seconds();
    if (Calls != 1) Probe.Fail(TEXT("A hunter contact resolved more than once"));
}

void FJapanEnemyProbe::Initialize(AFoxHunter* Fox)
{
    Began = PhaseBegan = FPlatformTime::Seconds();
    Home = Fox->GetActorLocation(); Axis = Fox->GetActorForwardVector();
    InitialMaximum = Fox->EncounterHealth;
    if (!Fox->HasAuthority()) return;
    ActorTickWasEnabled = Fox->IsActorTickEnabled();
    MovementTickWasEnabled = Fox->GetCharacterMovement()->IsComponentTickEnabled();
    Fox->SetActorTickEnabled(false); // Before the first authority AI decision.
    Fox->SetSeed(731); Fox->SetPassive(true);
    Setup->SetNumberField(TEXT("initial_maximum"), InitialMaximum);
    Setup->SetBoolField(TEXT("actor_tick_was_enabled"), ActorTickWasEnabled);
    Setup->SetBoolField(TEXT("movement_tick_was_enabled"), MovementTickWasEnabled);
}

void FJapanEnemyProbe::Notice()
{
    if (NoticeSeen) return;
    auto* Fox = Hunter.Get();
    if (!Fox || !Host.IsValid() || !Guest.IsValid()) { Fail(TEXT("Hunter noticed before both players were ready")); return; }
    NoticeSeen = true;
    const double A = FVector::Dist2D(Fox->GetActorLocation(), Host->GetActorLocation());
    const double B = FVector::Dist2D(Fox->GetActorLocation(), Guest->GetActorLocation());
    Setup->SetNumberField(TEXT("host_notice_distance"), A);
    Setup->SetNumberField(TEXT("guest_notice_distance"), B);
    Setup->SetStringField(TEXT("host_id"), HostId); Setup->SetStringField(TEXT("guest_id"), GuestId);
    Setup->SetNumberField(TEXT("frozen_maximum"), Fox->EncounterHealth);
    Setup->SetNumberField(TEXT("notice_ai_ticks"), AiTicks);
    Setup->SetNumberField(TEXT("movement_mode_at_notice"), uint8(Fox->GetCharacterMovement()->MovementMode));
    Encounter = Fox->GetWorld()->GetSubsystem<UJapanEncounters>()->Identity(Fox);
    if (!Resumed || A >= AFoxHunter::NoticeRadius || B >= AFoxHunter::NoticeRadius ||
        InitialMaximum != 6 || Fox->EncounterHealth != 9 || !Encounter || !Fox->GetCharacterMovement()->IsMovingOnGround())
        Fail(TEXT("Initial two-player encounter membership or grounding was not proven"));
}
void JapanEnemyQA::Noticed(AFoxHunter* Fox) { if (Probe.Owns(Fox)) Probe.Notice(); }

void FJapanEnemyProbe::Observe(AFoxHunter* Fox)
{
    if (PreviousHealth >= 0 && PreviousHealth != Fox->Health) ++HealthChanges;
    if (PreviousState != EFoxState::Dead && Fox->State == EFoxState::Dead) ++DeathChanges;
    PreviousHealth = Fox->Health; PreviousState = Fox->State;
    if (Guest.IsValid() && Guest->GetSword())
    {
        const float Health = Guest->GetSword()->GetHealth();
        if (LastGuestHealth >= 0.f && !FMath::IsNearlyEqual(LastGuestHealth, Health, .01f)) ++GuestHealthChanges;
        LastGuestHealth = Health;
    }
    if (Identity.IsEmpty()) Identity = ActorId(Fox);
    else if (Identity != ActorId(Fox)) Fail(TEXT("Shared hunter identity changed"));
    if (!Fox->HasAuthority() && (Fox->GetLocalRole() != ROLE_SimulatedProxy || Fox->GetController() || AiTicks || Sweeps))
        Fail(TEXT("Guest hunter ran local authority or collision logic"));
    if (Phase > 0 && Fox->EncounterHealth != 9) Fail(TEXT("Encounter difficulty changed after engagement"));
}

void FJapanEnemyProbe::SetPhase(int32 Next)
{
    Baseline();
    Phase = Next; PhaseBegan = FPlatformTime::Seconds(); PhaseHitStart = Hits.Num();
    PhaseHealth = Hunter->Health; StopAttacks = false; NextAttack = 0.;
    if (Phase == 3)
    {
        GuestHealthBefore = Guest->GetSword()->GetHealth();
        Hunter->ForceNextAttack(TEXT("AttackR_A")); Hunter->SetPassive(false);
    }
}

void FJapanEnemyProbe::Drive(AWandererCharacter* Player)
{
    auto* Fox = Hunter.Get();
    auto* Moves = Player ? Player->GetMoves() : nullptr;
    if (!Fox || !Moves || !Player->Controller || !Player->IsLocallyControlled()) return;
    const bool IsGuest = PlayerId(Player) == GuestId;
    const double Now = FPlatformTime::Seconds();
    const FVector Here = Player->GetActorLocation(), There = Fox->GetActorLocation();
    const double Distance = FVector::Dist2D(Here, There);
    FVector Goal = There;
    const bool Attacker = Phase == 1 ? IsGuest : Phase == 2 ? !IsGuest : Phase == 4 ? IsGuest : false;
    if (Phase == 0)
    {
        const FVector Side(-Axis.Y, Axis.X, 0.f);
        Goal = Home + Axis * (IsGuest ? 500.f : 650.f) + Side * (IsGuest ? 140.f : -140.f);
    }
    else if (!Attacker && !(Phase == 3 && IsGuest))
    {
        FVector Away = (Here - There).GetSafeNormal2D();
        if (Away.IsNearlyZero()) Away = Axis;
        Goal = Distance < 550. ? There + Away * 650.f : Here;
    }
    FVector To = Goal - Here; To.Z = 0.;
    const bool Close = Phase == 0 ? To.Size() < 25. : (Attacker || (Phase == 3 && IsGuest)) ? Distance < 100. : To.IsNearlyZero();
    const FRotator Facing = (Close && Phase > 0 ? There - Here : To).Rotation();
    Player->Controller->SetControlRotation(FRotator(0, Facing.Yaw, 0));
    Player->Live_Drive(Close || Complete ? FVector2D::ZeroVector : FVector2D(0, 1), Phase == 0 ? 1 : 2);
    if (SeenPhase != Phase)
    {
        Player->Live_Press(TEXT("attack_release")); Player->Live_Press(TEXT("guard_release")); Player->Live_Press(TEXT("jump_release"));
        AttackHeld = false; SeenPhase = Phase; NextAttack = Now + .25;
    }
    if (!Attacker || StopAttacks || Complete)
    { if (AttackHeld) { Player->Live_Press(TEXT("attack_release")); AttackHeld = false; } return; }
    if (!Moves->IsArmed())
    {
        if (!Player->MovementLocked() && Now >= NextAttack) { Player->Live_Press(TEXT("weapon")); NextAttack = Now + .75; }
        return;
    }
    const auto* Other = IsGuest ? Host.Get() : Guest.Get();
    const bool OtherClear = Other && FVector::Dist2D(Other->GetActorLocation(), There) > 350. && Other->GetVelocity().Size2D() < 5.f;
    if (Close && OtherClear && !Player->MovementLocked() && !Moves->IsBusy() && Now >= NextAttack)
    {
        Player->Live_Press(TEXT("attack")); AttackHeld = true; ++Attempts.FindOrAdd(PlayerId(Player));
        NextAttack = Now + 1.;
    }
    else if (AttackHeld) { Player->Live_Press(TEXT("attack_release")); AttackHeld = false; }
    // One successful replicated health decrement stops the serialized hit phase.
    if ((Phase == 1 || Phase == 2) && PhaseHealth >= 0 && Fox->Health < PhaseHealth) StopAttacks = true;
}

bool FJapanEnemyProbe::PeerMatches(const TSharedPtr<FJsonObject>& Other) const
{
    if (!Other || !Other->GetStringField(TEXT("error")).IsEmpty()) return false;
    const auto* Fox = Hunter.Get();
    return Other->GetNumberField(TEXT("phase")) == Phase && Other->GetStringField(TEXT("net_guid")) == Identity &&
        Other->GetNumberField(TEXT("health")) == Fox->Health && Other->GetNumberField(TEXT("maximum_health")) == Fox->EncounterHealth &&
        Other->GetNumberField(TEXT("action_serial")) == Fox->ActionSerial &&
        Other->GetBoolField(TEXT("simulated_proxy")) && !Other->GetBoolField(TEXT("has_controller")) &&
        Other->GetNumberField(TEXT("ai_ticks")) == 0 && Other->GetNumberField(TEXT("sweep_calls")) == 0 &&
        FPlatformTime::Seconds() - Other->GetNumberField(TEXT("at")) < 1.;
}

bool FJapanEnemyProbe::Tick(const FString& Folder)
{
    auto* Fox = Hunter.Get();
    if (!Fox || !Fox->IsReady()) return false;
    const bool Server = Fox->HasAuthority();
    const double Now = FPlatformTime::Seconds();
    if (Now - Began > 90.) Fail(FString::Printf(TEXT("Shared-enemy deadline: phase %d, state %s, health %d, hits %d, claws %d"),
        Phase, *Fox->StateName(), Fox->Health, Hits.Num(), Claws.Num()));
    if (Server && !Paused && !Resumed)
    {
        auto* Movement = Fox->GetCharacterMovement();
        if (!Movement->IsMovingOnGround() || Fox->GetVelocity().Size() >= .1f) return false;
        Setup->SetNumberField(TEXT("settle_displacement_cm"), FVector::Distance(Home, Fox->GetActorLocation()));
        Setup->SetNumberField(TEXT("paused_movement_mode"), uint8(Movement->MovementMode));
        Paused = true; PausedPosition = Fox->GetActorLocation(); PausedClock = Fox->Clock; PausedStateTime = Fox->StateTime;
        Movement->SetComponentTickEnabled(false);
    }
    int32 Count = 0;
    for (TActorIterator<AWandererCharacter> It(Fox->GetWorld()); It; ++It)
    {
        if (It->IsNpc()) continue;
        const auto* State = It->GetPlayerState<AJapanPlayerState>();
        if (!State || !State->bWorldReady || !It->IsReady()) return false;
        ++Count;
        if (Server ? It->IsLocallyControlled() : !It->IsLocallyControlled()) { Host = *It; HostId = PlayerId(*It); }
        else { Guest = *It; GuestId = PlayerId(*It); }
    }
    if (Count != 2 || !Host.IsValid() || !Guest.IsValid() || HostId.IsEmpty() || GuestId.IsEmpty()) return false;
    if (Server && ClawResolved > 0. && !MadePassiveAfterClaw)
    {
        Fox->SetPassive(true); MadePassiveAfterClaw = true;
    }
    if (!Server)
    {
        auto Control = Read(Folder / TEXT("enemy-control.json"));
        if (!Control) return false;
        Home = FVector(Control->GetNumberField(TEXT("home_x")), Control->GetNumberField(TEXT("home_y")), Control->GetNumberField(TEXT("home_z")));
        Axis = FVector(Control->GetNumberField(TEXT("axis_x")), Control->GetNumberField(TEXT("axis_y")), 0.);
        const int32 Next = int32(Control->GetNumberField(TEXT("phase")));
        if (Next != Phase) { Baseline(); Phase = Next; PhaseHealth = Fox->Health; StopAttacks = false; }
        Complete = Control->GetBoolField(TEXT("complete"));
    }
    if (LastWorldFrame != Fox->GetWorld()->GetTimeSeconds())
    {
        LastWorldFrame = Fox->GetWorld()->GetTimeSeconds(); ++Frames;
        const double Dt = Fox->GetWorld()->GetDeltaSeconds();
        FrameMin = FMath::Min(FrameMin, Dt); FrameMax = FMath::Max(FrameMax, Dt);
    }
    Observe(Fox);
    if (Server && Paused && !Resumed)
    {
        if (Fox->Clock != PausedClock || Fox->StateTime != PausedStateTime || !Fox->GetActorLocation().Equals(PausedPosition, .001))
            Fail(TEXT("Hunter advanced during the asserted setup pause"));
        if (FVector::Dist2D(Host->GetActorLocation(), PausedPosition) < 700. &&
            FVector::Dist2D(Guest->GetActorLocation(), PausedPosition) < 700. && Read(Folder / TEXT("enemy-observed.json")))
        {
            Setup->SetBoolField(TEXT("pause_unchanged"), Error.IsEmpty());
            Setup->SetNumberField(TEXT("paused_ai_ticks"), AiTicks);
            Resumed = true;
            Fox->GetCharacterMovement()->SetComponentTickEnabled(MovementTickWasEnabled);
            Fox->SetActorTickEnabled(ActorTickWasEnabled);
            Setup->SetNumberField(TEXT("resume_count"), 1);
        }
    }
    if (Server && Phase == 0 && NoticeSeen && Error.IsEmpty() && PeerMatches(Read(Folder / TEXT("enemy-observed.json")))) SetPhase(1);
    Drive(Server ? Host.Get() : Guest.Get());
    if (Now - LastFile < .05) return Complete;
    LastFile = Now;
    auto State = Snapshot(Fox);
    State->SetBoolField(TEXT("complete"), Complete);
    if (!Write(Folder / (Server ? TEXT("enemy-control.json") : TEXT("enemy-observed.json")), State)) Fail(TEXT("Could not write shared-enemy observation"));
    if (!Server) return Complete;
    auto Peer = Read(Folder / TEXT("enemy-observed.json"));
    if (Peer && !Peer->GetStringField(TEXT("error")).IsEmpty()) Fail(TEXT("Guest observation failed: ") + Peer->GetStringField(TEXT("error")));
    if ((Phase == 1 || Phase == 2) && Hits.Num() > int32(PhaseHitStart) && PeerMatches(Peer))
    {
        const FString Expected = Phase == 1 ? GuestId : HostId;
        for (int32 I = PhaseHitStart; I < Hits.Num(); ++I)
            if (Hits[I]->AsObject()->GetStringField(TEXT("player_id")) != Expected) Fail(TEXT("Inactive player received hit credit"));
        if (Fox->Health <= 0) Fail(TEXT("Hunter died before both players and the claw were observed"));
        if (Host->GetMoves()->IsBusy() || Guest->GetMoves()->IsBusy()) return false;
        State->SetObjectField(TEXT("guest_observation"), Peer); Phases.Add(MakeShared<FJsonValueObject>(State));
        SetPhase(Phase + 1);
    }
    else if (Phase == 3 && ClawResolved > 0. && Now - ClawResolved > 1. && Fox->State != EFoxState::Attack && PeerMatches(Peer))
    {
        const auto Claw = Claws.Num() == 1 ? Claws[0]->AsObject() : nullptr;
        const double Health = Guest->GetSword()->GetHealth();
        if (!Claw || Claw->GetNumberField(TEXT("callbacks")) != 1 || Claw->GetNumberField(TEXT("outcome")) != 0 ||
            !FMath::IsNearlyEqual(double(GuestHealthBefore) - Health, double(AFoxHunter::ClawDamage), .01) ||
            Peer->GetNumberField(TEXT("guest_health_changes")) != 1 || GuestHealthChanges != 1 ||
            !FMath::IsNearlyEqual(Peer->GetNumberField(TEXT("guest_health")), Health, .01))
            Fail(TEXT("Claw was not exactly one undefended replicated health decrement"));
        State->SetObjectField(TEXT("guest_observation"), Peer); Phases.Add(MakeShared<FJsonValueObject>(State));
        SetPhase(4);
    }
    else if (Phase == 4 && Fox->State == EFoxState::Dead && PeerMatches(Peer))
    {
        if (Fox->Health != 0 || Fox->Deaths != 1 || Peer->GetNumberField(TEXT("death_changes")) != 1)
            Fail(TEXT("The two peers did not observe one shared hunter death"));
        State->SetObjectField(TEXT("guest_observation"), Peer); Phases.Add(MakeShared<FJsonValueObject>(State));
        Complete = Error.IsEmpty(); SetPhase(5);
        auto Result = Snapshot(Fox); Result->SetBoolField(TEXT("passed"), Complete);
        Result->SetObjectField(TEXT("setup"), Setup); Result->SetArrayField(TEXT("hits"), Hits);
        Result->SetArrayField(TEXT("claws"), Claws); Result->SetArrayField(TEXT("phases"), Phases);
        if (!Write(Folder / TEXT("enemy-result.json"), Result)) Fail(TEXT("Could not write shared-enemy result"));
    }
    return Complete;
}

bool JapanEnemyQA::Tick(UWorld* World, bool Server, const FString& Folder, FString& Error)
{
    if (!Enabled()) { Error = TEXT("Shared-enemy flag missing"); return false; }
    int32 Count = 0;
    for (TActorIterator<AFoxHunter> It(World); It; ++It) ++Count;
    if (Count > 1) Probe.Fail(TEXT("Expected exactly one shared hunter"));
    if (!Count || Probe.World.Get() != World) return false;
    if (Probe.Hunter->HasAuthority() != Server) Probe.Fail(TEXT("Shared-enemy authority role mismatch"));
    const bool Done = Probe.Tick(Folder);
    Error = Probe.Error;
    if (!Error.IsEmpty()) Write(Folder / TEXT("enemy-failed.json"), Probe.Snapshot(Probe.Hunter.Get()));
    return Done;
}

bool JapanEnemyQA::Finalize(const FString& Folder, FString& Error)
{
    Error = Probe.Error;
    if (!Probe.Complete || Probe.Claws.Num() != 1 || Probe.Claws[0]->AsObject()->GetNumberField(TEXT("callbacks")) != 1)
        Error = TEXT("Shared-enemy lifecycle ended without exactly-once completion");
    auto Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("passed"), Error.IsEmpty()); Result->SetStringField(TEXT("error"), Error);
    Result->SetArrayField(TEXT("claws"), Probe.Claws);
    return Write(Folder / TEXT("enemy-final.json"), Result) && Error.IsEmpty();
}

#else
void JapanEnemyQA::QueuedAttack(AWandererCharacter*, uint32, uint16) {}
void JapanEnemyQA::AcceptedAttack(AWandererCharacter*, uint32, uint16) {}
void JapanEnemyQA::StartedCut(AWandererCharacter*, bool) {}
void JapanEnemyQA::BeginHunter(AFoxHunter*) {}
void JapanEnemyQA::AuthorityTick(AFoxHunter*) {}
void JapanEnemyQA::Sweep(AFoxHunter*) {}
void JapanEnemyQA::Noticed(AFoxHunter*) {}
void JapanEnemyQA::SwordDamage(AFoxHunter*, AActor*, int32, int32, int32) {}
void JapanEnemyQA::BladeCandidate(AWandererCharacter*, AActor*) {}
uint32 JapanEnemyQA::Contact(AFoxHunter*, AWandererCharacter*, float) { return 0; }
void JapanEnemyQA::Resolved(uint32, int32) {}
bool JapanEnemyQA::Tick(UWorld*, bool, const FString&, FString& Error)
{ Error = TEXT("Shared-enemy QA is disabled in Shipping builds"); return false; }
bool JapanEnemyQA::Finalize(const FString&, FString& Error)
{ Error = TEXT("Shared-enemy QA is disabled in Shipping builds"); return false; }
#endif
