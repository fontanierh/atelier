#include "JapanEncounters.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "Engine/World.h"
#include "EngineUtils.h"

bool UJapanEncounters::Eligible(const AWandererCharacter* Player)
{
    const auto* State = Player ? Player->GetPlayerState<AJapanPlayerState>() : nullptr;
    return IsValid(Player) && !Player->IsNpc() && Player->GetController() && Player->IsReady() && State && State->bWorldReady &&
        Player->GetNetworkActivity() == EJapanActivity::OnFoot &&
        (!Player->GetSword() || (!Player->GetSword()->IsDown() && Player->GetSword()->GetHealth() > 0.f));
}

void UJapanEncounters::Prune()
{
    const double Now = GetWorld()->GetTimeSeconds();
    for (auto It = Encounters.CreateIterator(); It; ++It)
        if (!It.Key().IsValid() || Now - It.Value().Updated > 2.) It.RemoveCurrent();
}

int32 UJapanEncounters::Engage(AActor* Enemy, float Range, int32 BaseHealth)
{
    if (!Enemy || !Enemy->HasAuthority()) return BaseHealth;
    Prune();
    auto& Entry = Encounters.FindOrAdd(Enemy);
    if (!Entry.Id)
    {
        Entry.Id = ++NextIdentity; if (!Entry.Id) Entry.Id = ++NextIdentity;
        Entry.Origin = Enemy->GetActorLocation();
    }
    Refresh(Enemy, Range);
    // Freeze difficulty before the first damage. Late arrivals never heal or rescale an active enemy.
    if (!Entry.FrozenHealth) Entry.FrozenHealth = BaseHealth + FMath::DivideAndRoundUp(BaseHealth, 2) * FMath::Clamp(Entry.Members.Num() - 1, 0, 7);
    return Entry.FrozenHealth;
}

void UJapanEncounters::Refresh(AActor* Enemy, float Range)
{
    auto* Entry = Encounters.Find(Enemy);
    if (!Entry || !Enemy || !Enemy->HasAuthority()) return;
    const double Now = GetWorld()->GetTimeSeconds();
    const float Decay = FMath::Exp(-float(FMath::Max(0., Now - Entry->Updated)) / 8.f);
    for (auto& Pair : Entry->Members) Pair.Value.Threat *= Decay;
    Entry->Updated = Now;
    const auto Within = [&](const AWandererCharacter* Player)
    {
        return Eligible(Player) && FVector::DistSquared2D(Enemy->GetActorLocation(), Player->GetActorLocation()) <= FMath::Square(Range) &&
            FVector::DistSquared2D(Entry->Origin, Player->GetActorLocation()) <= FMath::Square(5000.f);
    };
    for (auto It = Entry->Members.CreateIterator(); It; ++It) if (!Within(It.Key().Get())) It.RemoveCurrent();
    for (TActorIterator<AWandererCharacter> It(GetWorld()); It; ++It)
        if (Within(*It)) Entry->Members.FindOrAdd(*It);
    if (!Within(Entry->Attacking.Get())) { Entry->Attacking.Reset(); Entry->AttackUntil = 0.; }
}

void UJapanEncounters::End(AActor* Enemy) { Encounters.Remove(Enemy); }
void UJapanEncounters::AddThreat(AActor* Enemy, AWandererCharacter* Player, float Amount)
{
    if (auto* Entry = Encounters.Find(Enemy); Entry && Eligible(Player))
        if (FMember* Member = Entry->Members.Find(Player))
        {
            Member->Threat = FMath::Clamp(Member->Threat + FMath::Max(0.f, Amount) / 4.f, 0.f, 1.f);
            Member->bCommitted = true;
        }
}
AWandererCharacter* UJapanEncounters::Select(AActor* Enemy, AWandererCharacter* Current) const
{
    const auto* Entry = Encounters.Find(Enemy);
    if (!Entry) return nullptr;
    AWandererCharacter* Best = nullptr;
    double Score = -TNumericLimits<double>::Max();
    for (const auto& Pair : Entry->Members)
    {
        auto* Player = Pair.Key.Get();
        if (!Eligible(Player)) continue;
        int32 Others = 0;
        const double Now = GetWorld()->GetTimeSeconds();
        for (const auto& Encounter : Encounters)
            if (Encounter.Key.Get() != Enemy && Encounter.Value.Attacking == Player && Encounter.Value.AttackUntil > Now &&
                Now - Encounter.Value.Updated <= 2.) ++Others;
        // Prefer an available target; if everyone is occupied, keep waiting rather than end the encounter.
        const double Candidate = Pair.Value.Threat * 600. - FVector::Dist2D(Enemy->GetActorLocation(), Player->GetActorLocation()) +
            (Player == Current ? 200. : 0.) - (Others >= 2 ? 10000. : 0.);
        if (Candidate > Score) { Best = Player; Score = Candidate; }
    }
    return Best;
}
bool UJapanEncounters::ReserveAttack(AActor* Enemy, AWandererCharacter* Player, float Seconds)
{
    Prune();
    auto* Entry = Encounters.Find(Enemy);
    if (!Entry || !Eligible(Player) || !Entry->Members.Contains(Player)) return false;
    const double Now = GetWorld()->GetTimeSeconds();
    int32 Others = 0;
    for (const auto& Pair : Encounters)
        if (Pair.Key.Get() != Enemy && Pair.Value.Attacking == Player && Pair.Value.AttackUntil > Now) ++Others;
    if (Others >= 2) return false;
    Entry->Attacking = Player; Entry->AttackUntil = Now + FMath::Clamp(Seconds, .1f, 5.f);
    Entry->Members.FindChecked(Player).bCommitted = true;
    return true;
}
void UJapanEncounters::ReleaseAttack(AActor* Enemy)
{
    if (auto* Entry = Encounters.Find(Enemy)) { Entry->Attacking.Reset(); Entry->AttackUntil = 0.; }
}
bool UJapanEncounters::HoldsPlayer(AWandererCharacter* Player) const
{
    if (!Eligible(Player)) return false;
    const double Now = GetWorld()->GetTimeSeconds();
    for (const auto& Pair : Encounters)
        if (Pair.Key.IsValid() && Now - Pair.Value.Updated <= 2.)
            if (const FMember* Member = Pair.Value.Members.Find(Player); Member && Member->bCommitted) return true;
    return false;
}
uint32 UJapanEncounters::Identity(AActor* Enemy) const
{
    const auto* Entry = Encounters.Find(Enemy);
    return Entry ? Entry->Id : 0;
}

int32 UJapanEncounters::FrozenHealth(AActor* Enemy, int32 Fallback) const
{
    const auto* Entry = Encounters.Find(Enemy);
    return Entry && Entry->FrozenHealth > 0 ? Entry->FrozenHealth : Fallback;
}
