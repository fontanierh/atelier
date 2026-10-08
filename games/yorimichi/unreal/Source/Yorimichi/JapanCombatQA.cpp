#include "JapanCombatQA.h"
#include "AtelierData.h"
#if !UE_BUILD_SHIPPING
#include "JapanCombatResolver.h"
#include "JapanCharacterMovement.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "AdventureMoveSet.h"
#include "AdventureMoveSetDetail.h"
#include "Components/CapsuleComponent.h"
#include "Engine/TargetPoint.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/CommandLine.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
struct FProbe
{
    TWeakObjectPtr<UWorld> World;
    int32 Phase = 0;
    double Began = 0., Pressed = -1.;
    bool Prepared = false, Planned = false;
};
FProbe Driver;
int32 HostSent[2] = {-1, -1};
struct FFrame { double At, Dt; };
TArray<FFrame> FrameHistory;
TWeakObjectPtr<UWorld> FrameWorld;
struct FCounters
{
    uint32 Overflow = 0, Missing = 0, Fallback = 0, Rejected = 0;
    static FCounters Get(AWandererCharacter* Player)
    {
        auto* Moves = Player->GetMoves();
        auto* Resolver = Player->GetWorld()->GetSubsystem<UJapanCombatResolver>();
        if (!Moves || !Resolver) return {};
        return {Resolver->Overflows, Moves->DefenceMissingSamples(), Moves->DefenceAuthoredFallbacks(), Moves->DefensiveRejectedTimes};
    }
};
FCounters Before[2][5];
TWeakObjectPtr<UWorld> HostWorld;
struct FReport { FString File; TSharedPtr<FJsonObject> Data; double Began; bool Written = false; TWeakObjectPtr<AWandererCharacter> Victim; };
void FrameStats(const TSharedPtr<FJsonObject>& Data, double From, double Through)
{
    double Minimum = 100., Maximum = 0.; int32 Count = 0;
    for (int32 I = 0; I < FrameHistory.Num(); ++I)
    {
        const FFrame& F = FrameHistory[I];
        // Include the frame in which the press occurred, even when Drive ran a
        // fraction of a millisecond after this world's tick was recorded.
        if (F.At <= Through && (F.At >= From || I + 1 == FrameHistory.Num() || FrameHistory[I + 1].At > From))
        { Minimum = FMath::Min(Minimum, F.Dt); Maximum = FMath::Max(Maximum, F.Dt); ++Count; }
    }
    Data->SetNumberField(TEXT("frame_count"), Count);
    Data->SetNumberField(TEXT("frame_min"), Count ? Minimum : 0.);
    Data->SetNumberField(TEXT("frame_max"), Maximum);
}
TArray<FReport> Reports;
struct FReactionProof
{
    TWeakObjectPtr<const UJapanCharacterMovement> Movement;
    uint32 Epoch, Sequence, Forced;
    double At;
    FName Action;
};
TArray<FReactionProof, TInlineAllocator<32>> ReactionProofs;
const TCHAR* CaseNames[] = {TEXT("parry"), TEXT("dodge"), TEXT("guard"), TEXT("destroyed-source"), TEXT("forced-recovery")};

FString Path(const FString& Folder, int32 Person, int32 Phase, const TCHAR* Kind)
{
    return Folder / FString::Printf(TEXT("combat-%s-%d-%s.json"), Person ? TEXT("guest") : TEXT("host"), Phase, Kind);
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

void Drive(AWandererCharacter* Player, const FString& Folder, int32 Person, FString& Error)
{
    // Serialize players so global resolver counters belong to exactly one case.
    if (Person && !Read(Path(Folder, 0, 4, TEXT("confirmed")))) return;
    const double Now = FPlatformTime::Seconds();
    if (Driver.World.Get() != Player->GetWorld())
    { Driver = FProbe(); Driver.World = Player->GetWorld(); Driver.Began = Now; }
    if (Driver.Phase >= UE_ARRAY_COUNT(CaseNames)) return;
    if (Now - Driver.Began > 12.) { Error = TEXT("Combat input/result deadline expired: ") + FString(CaseNames[Driver.Phase]); return; }
    auto* Moves = Player->GetMoves();
    if (!Moves) { Error = TEXT("Combat probe requires the merged move set"); return; }
    if (auto Result = Read(Path(Folder, Person, Driver.Phase, TEXT("result"))))
    {
        if (!Result->GetBoolField(TEXT("passed")))
        { Error = TEXT("Authoritative combat probe failed: ") + FString(CaseNames[Driver.Phase]); return; }
        // Wait for the ordinary replicated health before acknowledging this case.
        const double ConfirmDelay = Now - Result->GetNumberField(TEXT("resolved_at"));
        if (!FMath::IsNearlyEqual(double(Player->GetSword()->GetHealth()), Result->GetNumberField(TEXT("health_after")), .01))
        {
            if (ConfirmDelay > 1.) Error = FString::Printf(TEXT("Replicated combat health did not settle in 1s: actual %.2f, expected %.2f"),
                Player->GetSword()->GetHealth(), Result->GetNumberField(TEXT("health_after")));
            return;
        }
        auto Confirmation = MakeShared<FJsonObject>();
        Confirmation->SetNumberField(TEXT("health"), Player->GetSword()->GetHealth());
        Confirmation->SetNumberField(TEXT("health_confirm_delay_ms"), ConfirmDelay * 1000.);
        FrameStats(Confirmation, Driver.Pressed, Result->GetNumberField(TEXT("contact_at")));
        if (!Write(Path(Folder, Person, Driver.Phase, TEXT("confirmed")), Confirmation))
        { Error = TEXT("Could not save owner combat confirmation"); return; }
        Player->Live_Press(TEXT("jump_release")); Player->Live_Press(TEXT("guard_release"));
        ++Driver.Phase; Driver.Began = Now; Driver.Pressed = -1.; Driver.Prepared = Driver.Planned = false;
        return;
    }
    if (Driver.Planned) return;
    // Let the previous real hit/guard/flurry recovery finish before the next case.
    if (Now - Driver.Began < 2. || Player->IsNetworkActivityPending()) return;
    const bool Guard = Driver.Phase == 0 || Driver.Phase == 2;
    if (!Driver.Prepared)
    {
        if (Player->MovementLocked() || Moves->InFlurry()) return;
        if (!Read(Path(Folder, Person, Driver.Phase, TEXT("armed"))))
        {
            if (!Write(Path(Folder, Person, Driver.Phase, TEXT("arm")), MakeShared<FJsonObject>()))
                Error = TEXT("Could not arm combat counter baseline");
            return;
        }
        Player->Live_Drive(FVector2D::ZeroVector, 1);
        Player->Live_Press(Guard ? TEXT("guard") : TEXT("guard_release"));
        Driver.Prepared = true;
        return;
    }
    if (Driver.Pressed < 0.)
    {
        if (Player->MovementLocked() || (Guard && !Moves->IsGuarding())) return;
        if (Driver.Phase == 0) Player->Live_Press(TEXT("jump"));
        else if (Driver.Phase == 1) Player->Live_Press(TEXT("dodge"));
        Driver.Pressed = Now;
        if (Driver.Phase < 2) return; // Observe the action actually starting in a movement step.
    }
    const FName Action = Player->GetAnimationAction();
    double StrikeAt = Now + .15, WindowEnd = StrikeAt + .5;
    if (Driver.Phase < 2)
    {
        if (Driver.Phase == 0 ? !AdventureMoveSetDetail::IsParry(Action) : !AdventureMoveSetDetail::IsHop(Action)) return;
        const double Started = Now - Player->GetActionTime();
        if (Driver.Phase == 0)
        {
            const FAdventureMove* Move = Moves->Find(Action);
            if (!Move || Move->Guard.IsEmpty()) { Error = TEXT("The live parry has no authored defence window"); return; }
            const FVector2f Window = Move->Guard[0];
            StrikeAt = FMath::Max(Now, Started + (Window.X - Move->Start) / Move->Rate + .015);
            WindowEnd = Started + (Window.Y - Move->Start) / Move->Rate;
        }
        else { StrikeAt = Started + .1; WindowEnd = Started + .25; }
    }
    auto Plan = MakeShared<FJsonObject>();
    Plan->SetStringField(TEXT("case"), CaseNames[Driver.Phase]);
    Plan->SetNumberField(TEXT("strike_at"), StrikeAt);
    Plan->SetNumberField(TEXT("window_end"), WindowEnd);
    Plan->SetNumberField(TEXT("press_at"), Driver.Pressed);
    Plan->SetNumberField(TEXT("observed_action_time"), Player->GetActionTime());
    Plan->SetStringField(TEXT("action"), Action.ToString());
    Plan->SetNumberField(TEXT("frame_dt"), Player->GetWorld()->GetDeltaSeconds());
    Plan->SetNumberField(TEXT("window_remaining_ms"), (WindowEnd - StrikeAt) * 1000.);
    if (!Write(Path(Folder, Person, Driver.Phase, TEXT("plan")), Plan)) Error = TEXT("Could not save combat stimulus plan");
    Driver.Planned = true;
}

void Contact(AWandererCharacter* Victim, int32 Person, int32 Phase, const TSharedPtr<FJsonObject>& Plan,
    const FString& Folder, FString& Error)
{
    UWorld* World = Victim->GetWorld();
    auto* Resolver = World->GetSubsystem<UJapanCombatResolver>();
    const double Now = FPlatformTime::Seconds();
    if (Now > Plan->GetNumberField(TEXT("window_end")))
    { Error = TEXT("Combat stimulus missed its planned window"); return; }
    if (!Resolver || !Victim->GetMoves() || !Victim->GetSword()) { Error = TEXT("Combat resolver missing"); return; }
    const FVector BeforePosition = Victim->GetActorLocation();
    const FVector From = BeforePosition + Victim->GetActorForwardVector() * 150.;
    ATargetPoint* Source = World->SpawnActor<ATargetPoint>(From, FRotator::ZeroRotator);
    if (!Source) { Error = TEXT("Could not create combat stimulus source"); return; }
    Source->SetReplicates(true);
    auto Report = MakeShared<FJsonObject>();
    Report->SetStringField(TEXT("case"), CaseNames[Phase]);
    Report->SetNumberField(TEXT("person"), Person); Report->SetNumberField(TEXT("phase"), Phase);
    Report->SetBoolField(TEXT("local_victim"), Victim->IsLocallyControlled());
    int32 HostFPS = 20; FParse::Value(FCommandLine::Get(), TEXT("networkcombathostfps="), HostFPS);
    Report->SetNumberField(TEXT("host_fps"), HostFPS);
    Report->SetNumberField(TEXT("contact_at"), Now);
    Report->SetNumberField(TEXT("contact_lateness_ms"), (Now - Plan->GetNumberField(TEXT("strike_at"))) * 1000.);
    Report->SetNumberField(TEXT("window_margin_ms"), (Plan->GetNumberField(TEXT("window_end")) - Now) * 1000.);
    FrameStats(Report, Plan->GetNumberField(TEXT("press_at")), Now);
    Report->SetStringField(TEXT("source_scope"), TEXT("TargetPoint stimulus: no attacker Deflected/TakeSwordHit proof"));
    Report->SetStringField(TEXT("case_scope"), Person ? TEXT("remote queued contact") : TEXT("local immediate contact; phases 3-4 are plain hits"));
    Report->SetBoolField(TEXT("recovering_at_contact"), Victim->GetMoves()->DefenceRecovering());
    Report->SetNumberField(TEXT("contact_after_press_ms"), (Now - Plan->GetNumberField(TEXT("press_at"))) * 1000.);
    Report->SetNumberField(TEXT("defence_wait_ms"), Victim->GetMoves()->DefenceWait() * 1000.);
    Report->SetNumberField(TEXT("compensation_cap_ms"), FJapanDefenceClock::MaximumCompensation * 1000.);
    const float BeforeHealth = Victim->GetSword()->GetHealth();
    const uint32 Epoch = Victim->GetActivityEpoch(), Queued = Resolver->Queued, Resolved = Resolver->Resolved,
        Cancelled = Resolver->Cancelled, Flushed = Resolver->Flushed;
    const int32 BeforeParries = Victim->GetMoves()->Parries(), BeforeDodges = Victim->GetMoves()->Dodges();
    const int32 Expected = Phase == 0 ? 1 : Phase == 1 ? 2 : Phase == 2 ? 3 : 0;
    Report->SetNumberField(TEXT("health_before"), BeforeHealth);
    Report->SetNumberField(TEXT("callbacks"), 0);
    Report->SetBoolField(TEXT("pending_gate_passed"), !Person || Phase != 3);
    Report->SetBoolField(TEXT("forced_flush_passed"), !Person || Phase != 4);
    const FCounters Baseline = Before[Person][Phase];
    TWeakObjectPtr<AWandererCharacter> WeakVictim(Victim);
    TWeakObjectPtr<ATargetPoint> WeakSource(Source);
    Resolver->Strike(Source, Victim, 8.f, From,
        [Report, WeakVictim, WeakSource, Resolver, BeforeHealth, BeforeParries, BeforeDodges,
         Expected, Queued, Resolved, Cancelled, Flushed, Baseline](int32 Outcome)
        {
            const double Calls = Report->GetNumberField(TEXT("callbacks")) + 1.;
            Report->SetNumberField(TEXT("callbacks"), Calls);
            AWandererCharacter* Player = WeakVictim.Get();
            if (!Player) return;
            Report->SetNumberField(TEXT("resolved_at"), FPlatformTime::Seconds());
            const float Health = Player->GetSword()->GetHealth();
            Report->SetNumberField(TEXT("health_after"), Health);
            Report->SetNumberField(TEXT("outcome"), Outcome);
            Report->SetNumberField(TEXT("queued"), Resolver->Queued - Queued);
            Report->SetNumberField(TEXT("resolved"), Resolver->Resolved - Resolved);
            Report->SetNumberField(TEXT("cancelled"), Resolver->Cancelled - Cancelled);
            Report->SetNumberField(TEXT("flushed"), Resolver->Flushed - Flushed);
            Report->SetNumberField(TEXT("parries"), Player->GetMoves()->Parries() - BeforeParries);
            Report->SetNumberField(TEXT("dodges"), Player->GetMoves()->Dodges() - BeforeDodges);
            const FCounters After = FCounters::Get(Player);
            Report->SetNumberField(TEXT("overflows"), After.Overflow - Baseline.Overflow);
            Report->SetNumberField(TEXT("missing_samples"), After.Missing - Baseline.Missing);
            Report->SetNumberField(TEXT("authored_fallbacks"), After.Fallback - Baseline.Fallback);
            Report->SetNumberField(TEXT("rejected_defence_times"), After.Rejected - Baseline.Rejected);
            Report->SetBoolField(TEXT("guard_hit"), AdventureMoveSetDetail::IsGuardHit(Player->GetAnimationAction()));
            const auto* Movement = Cast<UJapanCharacterMovement>(Player->GetCharacterMovement());
            const bool ScheduledGuard = Expected == 3 && !Player->IsLocallyControlled() && Movement && Movement->HasScheduledReaction();
            Report->SetBoolField(TEXT("scheduled_guard"), ScheduledGuard);
            Report->SetNumberField(TEXT("reaction_epoch"), Player->GetActivityEpoch());
            Report->SetNumberField(TEXT("reaction_sequence"), ScheduledGuard ? Movement->GetScheduledReactionKnown() : 0);
            const bool HealthOK = FMath::IsNearlyEqual(BeforeHealth - Health, Expected == 0 ? 8.f : 0.f, .01f);
            Report->SetBoolField(TEXT("decision_passed"), Calls == 1. && Outcome == Expected && HealthOK &&
                (Expected != 3 || ((ScheduledGuard || Report->GetBoolField(TEXT("guard_hit"))) && !Report->GetBoolField(TEXT("recovering_at_contact")))) &&
                (Expected != 1 || Player->GetMoves()->Parries() == BeforeParries + 1) &&
                (Expected != 2 || Player->GetMoves()->Dodges() == BeforeDodges + 1));
            // The caller adds synchronous pending/flush evidence before the next Tick writes the result.
            if (WeakSource.IsValid()) WeakSource->Destroy();
        });
    if (Person && Phase == 3)
    {
        const bool Pending = Resolver->HasPending(Victim);
        const bool Unlocked = !Victim->MovementLocked();
        Report->SetBoolField(TEXT("pending_before"), Pending);
        Report->SetBoolField(TEXT("unlocked_before"), Unlocked);
        const uint32 BeforeSkate = Resolver->PendingSkateRefusals, BeforeTravel = Resolver->PendingTravelRefusals;
        Victim->ServerRequestSkate(Epoch);
        Victim->ServerTravelTo(BeforePosition + FVector(500,0,0), 0.f, Epoch);
        Report->SetNumberField(TEXT("pending_skate_refusals"), Resolver->PendingSkateRefusals - BeforeSkate);
        Report->SetNumberField(TEXT("pending_travel_refusals"), Resolver->PendingTravelRefusals - BeforeTravel);
        Report->SetBoolField(TEXT("pending_gate_passed"), Pending && Unlocked && Resolver->HasPending(Victim) &&
            Resolver->PendingSkateRefusals == BeforeSkate + 1 && Resolver->PendingTravelRefusals == BeforeTravel + 1 &&
            Victim->GetActivityEpoch() == Epoch && Victim->GetNetworkActivity() == EJapanActivity::OnFoot &&
            Victim->GetActorLocation().Equals(BeforePosition, .01));
        Source->Destroy();
        Report->SetBoolField(TEXT("source_destroyed_before_resolution"), !IsValid(Source));
    }
    if (Person && Phase == 4)
    {
        const bool Pending = Resolver->HasPending(Victim);
        const bool Travelled = Victim->TravelTo(BeforePosition - FVector(0,0,Victim->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),
            Victim->GetActorRotation().Yaw, TEXT("network combat recovery probe"));
        Report->SetBoolField(TEXT("forced_flush_passed"), Pending && Travelled && !Resolver->HasPending(Victim) &&
            Resolver->Resolved == Resolved + 1 && Resolver->Flushed == Flushed + 1 && Resolver->Cancelled == Cancelled &&
            Victim->GetActivityEpoch() != Epoch);
    }
    Reports.Add({Path(Folder, Person, Phase, TEXT("result")), Report, Now, false, Victim});
}
}

void JapanCombatQA::ReactionApplied(const UJapanCharacterMovement* Movement, uint32 Epoch, uint32 Sequence)
{
    static const bool Enabled = FParse::Param(FCommandLine::Get(), TEXT("networkcombat"));
    const auto* Victim = Movement ? Cast<AWandererCharacter>(Movement->GetOwner()) : nullptr;
    if (!Enabled || !Victim || !Victim->HasAuthority() || Victim->IsLocallyControlled()) return;
    if (ReactionProofs.Num() >= 32) return; // Missing proof fails the bounded fixture below.
    ReactionProofs.Add({Movement, Epoch, Sequence, Movement->GetScheduledReactionStats().Forced,
        FPlatformTime::Seconds(), Victim->GetAnimationAction()});
}

bool JapanCombatQA::Tick(UWorld* World, bool Server, const FString& Folder, FString& Error)
{
    const double FrameNow = FPlatformTime::Seconds();
    if (FrameWorld.Get() != World) { FrameWorld = World; FrameHistory.Reset(); }
    FrameHistory.Add({FrameNow, World->GetDeltaSeconds()});
    while (!FrameHistory.IsEmpty() && FrameNow - FrameHistory[0].At > 3.) FrameHistory.RemoveAt(0, 1, EAllowShrinking::No);
    // Audit callbacks even after the guest has left and PlayerArray has shrunk.
    if (Server) for (const FReport& Report : Reports)
        if (Report.Data->GetNumberField(TEXT("callbacks")) > 1.)
        { Error = TEXT("A combat contact resolved more than once"); return false; }
    const auto* State = World->GetGameState<AJapanGameState>();
    if (!State || State->PlayerArray.Num() != 2) return false;
    AWandererCharacter* Local = nullptr;
    AWandererCharacter* People[2] = {};
    for (TActorIterator<AWandererCharacter> It(World); It; ++It)
        if (!It->IsNpc())
        {
            if (It->IsLocallyControlled()) Local = *It;
            if (Server) People[It->IsLocallyControlled() ? 0 : 1] = *It;
        }
    if (!Local || !Local->IsReady()) return false;
    Drive(Local, Folder, Server ? 0 : 1, Error);
    if (!Error.IsEmpty()) return false;
    if (Server)
    {
        if (HostWorld.Get() != World) { HostWorld = World; HostSent[0] = HostSent[1] = -1; Reports.Reset(); ReactionProofs.Reset(); }
        for (FReport& Report : Reports)
        {
            if (Report.Data->GetNumberField(TEXT("callbacks")) > 1.)
            { Error = TEXT("A combat contact resolved more than once"); return false; }
            if (Report.Written) continue;
            if (!Report.Data->HasField(TEXT("decision_passed")))
            {
                if (FPlatformTime::Seconds() - Report.Began > .5)
                { Error = TEXT("A queued combat contact missed its bounded resolution deadline"); return false; }
                continue;
            }
            bool ReactionOK = true;
            if (Report.Data->GetBoolField(TEXT("scheduled_guard")))
            {
                const uint32 Epoch = uint32(Report.Data->GetNumberField(TEXT("reaction_epoch")));
                const uint32 Sequence = uint32(Report.Data->GetNumberField(TEXT("reaction_sequence")));
                const auto* Movement = Report.Victim.IsValid() ? Cast<UJapanCharacterMovement>(Report.Victim->GetCharacterMovement()) : nullptr;
                const auto* Proof = ReactionProofs.FindByPredicate([&](const FReactionProof& P)
                    { return P.Movement.Get() == Movement && P.Epoch == Epoch && P.Sequence == Sequence; });
                if (!Proof)
                {
                    if (FPlatformTime::Seconds() - Report.Data->GetNumberField(TEXT("resolved_at")) > .5)
                    { Error = TEXT("Scheduled guard missed its bounded apply deadline"); return false; }
                    continue;
                }
                const double Delay = Proof->At - Report.Data->GetNumberField(TEXT("resolved_at"));
                Report.Data->SetStringField(TEXT("reaction_action"), Proof->Action.ToString());
                Report.Data->SetNumberField(TEXT("reaction_apply_delay"), Delay);
                Report.Data->SetNumberField(TEXT("reaction_forced"), Proof->Forced);
                Report.Data->SetBoolField(TEXT("guard_hit"), AdventureMoveSetDetail::IsGuardHit(Proof->Action));
                ReactionOK = Sequence > 0 && Delay >= 0. && Delay <= .5 && Proof->Forced == 0 && Report.Data->GetBoolField(TEXT("guard_hit"));
                ReactionProofs.RemoveAll([&](const FReactionProof& P)
                    { return P.Movement.Get() == Movement && P.Epoch == Epoch && P.Sequence == Sequence; });
            }
            Report.Data->SetBoolField(TEXT("passed"), ReactionOK && Report.Data->GetBoolField(TEXT("decision_passed")) &&
                Report.Data->GetBoolField(TEXT("pending_gate_passed")) && Report.Data->GetBoolField(TEXT("forced_flush_passed")));
            if (!Write(Report.File, Report.Data)) { Error = TEXT("Could not save combat result"); return false; }
            Report.Written = true;
        }
        for (int32 Person = 0; Person < 2; ++Person)
        {
            auto* Victim = People[Person];
            const int32 Phase = HostSent[Person] + 1;
            if (!Victim || !Victim->IsReady() || Phase >= UE_ARRAY_COUNT(CaseNames)) continue;
            const FString Armed = Path(Folder, Person, Phase, TEXT("armed"));
            if (Read(Path(Folder, Person, Phase, TEXT("arm"))) && !Read(Armed))
            {
                if (!Victim->GetMoves() || !World->GetSubsystem<UJapanCombatResolver>())
                { Error = TEXT("Combat baseline requires the live move set and resolver"); return false; }
                Before[Person][Phase] = FCounters::Get(Victim);
                if (!Write(Armed, MakeShared<FJsonObject>())) { Error = TEXT("Could not save combat baseline acknowledgement"); return false; }
            }
            if (auto Plan = Read(Path(Folder, Person, Phase, TEXT("plan"))); Plan && FPlatformTime::Seconds() >= Plan->GetNumberField(TEXT("strike_at")))
            {
                HostSent[Person] = Phase;
                Contact(Victim, Person, Phase, Plan, Folder, Error);
                if (!Error.IsEmpty()) return false;
            }
        }
    }
    if (Driver.Phase < UE_ARRAY_COUNT(CaseNames)) return false;
    for (int32 Person = 0; Person < 2; ++Person)
        for (int32 Phase = 0; Phase < UE_ARRAY_COUNT(CaseNames); ++Phase)
        {
            auto Result = Read(Path(Folder, Person, Phase, TEXT("result")));
            if (!Result || !Read(Path(Folder, Person, Phase, TEXT("confirmed")))) return false;
            if (!Result->GetBoolField(TEXT("passed"))) { Error = TEXT("Combat partner probe failed"); return false; }
        }
    return true;
}

bool JapanCombatQA::Finalize(const FString& Folder, FString& Error)
{
    if (Reports.Num() != 10) { Error = TEXT("Combat teardown lacks ten contacts"); return false; }
    auto Summary = MakeShared<FJsonObject>(); TArray<TSharedPtr<FJsonValue>> Cases;
    for (const FReport& Report : Reports)
    {
        if (!Report.Written || Report.Data->GetNumberField(TEXT("callbacks")) != 1.)
        { Error = TEXT("Combat teardown exactly-once check failed"); return false; }
        Cases.Add(MakeShared<FJsonValueObject>(Report.Data));
    }
    Summary->SetArrayField(TEXT("cases"), Cases);
    return Write(Folder / TEXT("combat-final.json"), Summary);
}
#else
void JapanCombatQA::ReactionApplied(const UJapanCharacterMovement*, uint32, uint32) {}
bool JapanCombatQA::Tick(UWorld*, bool, const FString&, FString&) { return false; }
bool JapanCombatQA::Finalize(const FString&, FString&) { return false; }
#endif
