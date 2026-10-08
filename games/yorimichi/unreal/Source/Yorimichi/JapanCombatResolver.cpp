#include "JapanCombatResolver.h"
#include "JapanNetwork.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "BotwMoveSet.h"
#include "Engine/World.h"

bool UJapanCombatResolver::DoesSupportWorldType(EWorldType::Type Type) const
{
    return Type == EWorldType::Game || Type == EWorldType::PIE;
}

TStatId UJapanCombatResolver::GetStatId() const
{
    RETURN_QUICK_DECLARE_CYCLE_STAT(UJapanCombatResolver, STATGROUP_Tickables);
}

void UJapanCombatResolver::Deinitialize()
{
    // Callbacks belong to the departing world and must not run after its teardown.
    Cancelled += Pending.Num(); Pending.Reset();
    Super::Deinitialize();
}

void UJapanCombatResolver::Strike(AActor* Source, AWandererCharacter* Victim,
    float Damage, const FVector& From, FResult Result)
{
    if (!Source || !Victim || !Victim->HasAuthority() || !Victim->GetSword() ||
        !FMath::IsFinite(Damage) || Damage < 0.f || From.ContainsNaN()) return;
    // Vehicle contacts are immediate and undefended. They never consult foot
    // defence history, and the old mount epoch is invalidated before damage.
    if(JapanNetwork::IsOnline(GetWorld())&&
        (Victim->GetNetworkActivity()==EJapanActivity::Bike||Victim->GetNetworkActivity()==EJapanActivity::Sailboat))
    {
        const bool Alive=Victim->GetSword()->GetHealth()>0.f;
        if (!Alive) { ++Resolved;if(Result)Result(3);return; }
        bool Applied=false; int32 Outcome=3;
        Victim->ExitNetworkVehicle(0,[&]()
        {
            if (Applied) return;
            Applied=true;
            Outcome=Victim->GetMoves()?Victim->GetMoves()->ResolveUnprotectedStrike(Source,Damage,From):
                Victim->GetSword()->IncomingStrike(Source,Damage,From);
        });
        if (Applied) { ++Resolved;if(Result)Result(Outcome);return; }
        // A refused/no-op handoff cannot swallow damage. The ordinary path below
        // still owns the contact; it also handles already-on-foot/pending mounts.
    }
    if (!JapanNetwork::IsOnline(GetWorld()) || !Victim->GetMoves() || Victim->IsNpc() || Victim->IsLocallyControlled())
    {
        const int32 Outcome = Victim->GetSword()->IncomingStrike(Source, Damage, From);
        if (Result) Result(Outcome);
        return;
    }
    UBotwMoveSet* Moves = Victim->GetMoves();
    const double Now = GetWorld()->GetTimeSeconds();
    const double Wait = FMath::Clamp(Moves->DefenceWait(), 0., FJapanDefenceClock::MaximumCompensation);
    int32 VictimCount = 0;
    double Due = Now + Wait;
    for (const FContact& C : Pending)
        if (C.Victim == Victim) { ++VictimCount; Due = FMath::Max(Due, C.Due); }
    // Overflow is a measurable loss of compensation, never a dropped hit or an
    // out-of-order result. Drain this victim's older contacts before the new one.
    if (Pending.Num() >= 128 || VictimCount >= 8)
    {
        ++Overflows;
        Flush(Victim);
        Due = Now;
    }
    FContact Contact;
    Contact.Source = Source; Contact.Victim = Victim; Contact.Epoch = Victim->GetActivityEpoch();
    Contact.Time = Now; Contact.Due = Due; Contact.Damage = Damage; Contact.From = From; Contact.Result = MoveTemp(Result);
    ++Queued;
    if (Due <= Now) { Resolve(MoveTemp(Contact)); RefreshRetention(Victim); }
    else { Pending.Add(MoveTemp(Contact)); RefreshRetention(Victim); }
}

void UJapanCombatResolver::Tick(float Dt)
{
    if (GetWorld()->GetNetMode() == NM_Client) return;
    const double Now = GetWorld()->GetTimeSeconds();
    // Remove before invoking a callback: a reaction may itself cause another contact.
    for (int32 I = 0; I < Pending.Num();)
    {
        const FContact& C = Pending[I];
        AWandererCharacter* Victim = C.Victim.Get();
        if (!Victim || Victim->GetActivityEpoch() != C.Epoch)
        {
            FContact CancelledContact = MoveTemp(Pending[I]); Pending.RemoveAt(I); ++Cancelled;
            if (CancelledContact.Result) CancelledContact.Result(3);
            RefreshRetention(Victim); continue;
        }
        if (C.Due > Now) { ++I; continue; }
        FContact Ready = MoveTemp(Pending[I]); Pending.RemoveAt(I);
        Resolve(MoveTemp(Ready));
        RefreshRetention(Victim);
    }
}

void UJapanCombatResolver::Resolve(FContact&& Contact)
{
    AWandererCharacter* Victim = Contact.Victim.Get();
    AActor* Source = Contact.Source.Get();
    if (!Victim || !Victim->GetSword() || !Victim->GetMoves() ||
        !Victim->Controller || Victim->GetActivityEpoch() != Contact.Epoch ||
        Victim->GetNetworkActivity() != EJapanActivity::OnFoot)
    { ++Cancelled; if (Contact.Result) Contact.Result(3); return; }
    // Contact time is authoritative even if the source was destroyed afterwards.
    // IncomingStrike accepts null Source; its position/damage were already captured.
    // State may have changed while awaiting input. A dead or already down victim
    // stays down; no delayed decision resurrects or rewrites previous health loss.
    const int32 Outcome = Victim->GetSword()->GetHealth() <= 0.f || Victim->GetMoves()->IsDown() ? 3 :
        Victim->GetMoves()->ResolveNetworkStrike(Source, Contact.Damage, Contact.From, Contact.Time);
    ++Resolved;
    if (Contact.Result) Contact.Result(Outcome);
}

void UJapanCombatResolver::RefreshRetention(AWandererCharacter* Victim)
{
    if (!Victim || !Victim->GetMoves()) return;
    double Oldest = TNumericLimits<double>::Max();
    for (const FContact& Contact : Pending)
        if (Contact.Victim == Victim) Oldest = FMath::Min(Oldest, Contact.Time);
    Victim->GetMoves()->RetainDefenceThrough(Oldest);
}

bool UJapanCombatResolver::HasPending(const AWandererCharacter* Victim) const
{
    return Victim && Pending.ContainsByPredicate([&](const FContact& Contact)
        { return Contact.Victim == Victim && Contact.Epoch == Victim->GetActivityEpoch(); });
}

void UJapanCombatResolver::Flush(AWandererCharacter* Victim)
{
    TArray<FContact> Ready;
    for (int32 I = 0; I < Pending.Num();)
        if (Pending[I].Victim == Victim)
        { Ready.Add(MoveTemp(Pending[I])); Pending.RemoveAt(I); }
        else ++I;
    Flushed += Ready.Num();
    for (FContact& Contact : Ready) Resolve(MoveTemp(Contact));
    RefreshRetention(Victim);
}
