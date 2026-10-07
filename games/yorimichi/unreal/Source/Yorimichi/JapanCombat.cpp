#include "JapanCombat.h"
#include "JapanCombatResolver.h"
#include "JapanEncounters.h"
#include "JapanNetwork.h"
#include "JapanCharacterMovement.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "YorimichiCombatFX.h"
#include "GameFramework/PlayerController.h"
#include "EngineUtils.h"
#include "Engine/World.h"

namespace
{
bool PredictedCue(EJapanCombatCue Kind)
{
    return Kind == EJapanCombatCue::Swing || Kind == EJapanCombatCue::Draw || Kind == EJapanCombatCue::ChargeReady;
}
}

AWandererCharacter* JapanCombat::FindPlayer(const AActor* Seeker, AWandererCharacter* Current, float Range)
{
    if (!Seeker) return nullptr;
    const auto Eligible = [&](const AWandererCharacter* Player)
    {
        if (!IsValid(Player) || Player->IsNpc() || !Player->IsReady() || !Player->GetController() ||
            (Player->GetSword() && Player->GetSword()->IsDown())) return false;
        if (JapanNetwork::IsOnline(Seeker->GetWorld()))
        {
            const auto* State = Player->GetPlayerState<AJapanPlayerState>();
            if (!State || !State->bWorldReady || !UJapanEncounters::Eligible(Player)) return false;
        }
        return FVector::DistSquared2D(Seeker->GetActorLocation(), Player->GetActorLocation()) < FMath::Square(Range);
    };
    if (Eligible(Current)) return Current;
    AWandererCharacter* Best = nullptr;
    double Distance = FMath::Square(Range);
    for (TActorIterator<AWandererCharacter> It(Seeker->GetWorld()); It; ++It)
        if (Eligible(*It))
        {
            const double Candidate = FVector::DistSquared2D(Seeker->GetActorLocation(), It->GetActorLocation());
            if (Candidate < Distance) { Best = *It; Distance = Candidate; }
        }
    return Best;
}

bool JapanCombat::Publish(const UObject* Context, EJapanCombatCue Kind, const FVector& At, const FVector& Direction,
    float Amount, AActor* Actor, AActor* Other, bool bDown, FName Sound)
{
    UWorld* World = Context ? Context->GetWorld() : nullptr;
    if (!JapanNetwork::IsOnline(World)) return false;
    const auto* Player = Cast<AWandererCharacter>(Actor);
    const auto* Movement = Player ? Cast<UJapanCharacterMovement>(Player->GetCharacterMovement()) : nullptr;
    if (Movement && Movement->IsReplaying()) return true;
    const bool LocalPrediction = PredictedCue(Kind) && Player && Player->IsLocallyControlled();
    if (World->GetNetMode() == NM_Client) return !LocalPrediction;
    if (auto* State = World->GetGameState<AJapanGameState>())
    {
        FJapanCombatEvent Event;
        Event.Kind = Kind; Event.At = At; Event.Direction = Direction; Event.Amount = Amount;
        Event.Actor = Actor; Event.Other = Other; Event.bDown = bDown; Event.Sound = Sound;
        State->PublishCombat(Event);
    }
    return !LocalPrediction;
}

bool JapanCombat::DurableOwnerCue(EJapanCombatCue Kind)
{
    return Kind == EJapanCombatCue::Hurt || Kind == EJapanCombatCue::GuardBreak;
}

void JapanCombat::Present(const UObject* Context, const FJapanCombatEvent& Event, bool bOwnerConfirmed)
{
    UWorld* World = Context ? Context->GetWorld() : nullptr;
    if (!World || World->GetNetMode() == NM_DedicatedServer) return;
    if (DurableOwnerCue(Event.Kind) && !bOwnerConfirmed)
        if (const auto* Victim = Cast<APawn>(Event.Actor); Victim && Victim->IsLocallyControlled()) return;
    if (PredictedCue(Event.Kind))
        if (const auto* Player = Cast<APawn>(Event.Actor); Player && Player->IsLocallyControlled()) return;
    bool Nearby = false;
    for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
        if (const auto* PC = It->Get(); PC && PC->IsLocalController() && PC->GetPawn())
            Nearby |= FVector::DistSquared(PC->GetPawn()->GetActorLocation(), Event.At) < FMath::Square(2500.);
    if (!Nearby) return;
    auto* FX = AYorimichiCombatFX::Get(Context);
    if (!FX) return;
    switch (Event.Kind)
    {
    case EJapanCombatCue::Hit: FX->SwordHit(Event.At, Event.Direction, FMath::Clamp(FMath::RoundToInt(Event.Amount), 1, 3), Event.Actor, Event.Other); break;
    case EJapanCombatCue::Parry:
        FX->Parry(Event.At, Event.Actor, Event.Other);
        if (Event.Amount > .5f)
        {
            FX->Burst(Event.At, Event.Direction, 26, 1700.f, FLinearColor(1.f,.7f,.3f)*9.f, .3f, 2.6f);
            AAtelierFX::FParticle& Ring = FX->Spawn(AAtelierFX::ESprite::Ring, Event.At);
            Ring.Size0 = 12.f; Ring.Size1 = 200.f; Ring.Life = .24f; Ring.Color = FLinearColor(1.f,.82f,.5f)*3.f;
            FX->Play(TEXT("hit_heavy"), Event.At, .45f, .06f);
        }
        break;
    case EJapanCombatCue::Hurt: FX->PlayerHurt(Event.At, Event.Direction, Event.Amount, Event.Actor, Event.Other, Event.bDown); break;
    case EJapanCombatCue::Dodge: FX->Flash(Event.At, 110.f, FLinearColor(.6f,.82f,1.f)*3.f, .2f); FX->Play(TEXT("charge_ready"), Event.At, .8f, .02f); break;
    case EJapanCombatCue::Swing: FX->SwordSwing(Event.At, FMath::Clamp(FMath::RoundToInt(Event.Amount), 1, 3)); break;
    case EJapanCombatCue::Draw: FX->Play(Event.Amount > .5f ? TEXT("sword_draw") : TEXT("sword_sheathe"), Event.At, .8f); break;
    case EJapanCombatCue::ChargeReady: FX->ChargeReady(Event.At); break;
    case EJapanCombatCue::Dash: FX->Dust(Event.At, 1.f, Event.Direction); FX->Play(TEXT("dash"), Event.At, .8f, .06f); break;
    case EJapanCombatCue::Guard:
        FX->Burst(Event.At, Event.Direction, 14, 700.f, FLinearColor(1.f,.85f,.55f)*4.f, .25f, 3.f);
        FX->Play(TEXT("parry"), Event.At, .6f, .06f); FX->Shake(.2f); break;
    case EJapanCombatCue::GuardBreak:
        FX->Burst(Event.At, Event.Direction, 26, 1100.f, FLinearColor(1.f,.8f,.45f)*7.f, .3f, 3.f);
        FX->Flash(Event.At, 70.f, FLinearColor(1.f,.8f,.5f)*3.f, .12f);
        FX->Play(TEXT("hit_heavy"), Event.At, .8f, .05f); FX->Shake(.6f); break;
    case EJapanCombatCue::Sound: FX->Play(Event.Sound, Event.At, Event.Amount, .06f); break;
    }
}

void JapanCombat::Strike(AActor* Source, AWandererCharacter* Victim, float Damage,
    const FVector& From, TFunction<void(int32)> Result)
{
    if (!Victim || !Victim->GetWorld() || !Victim->GetSword()) return;
    if (auto* Resolver = Victim->GetWorld()->GetSubsystem<UJapanCombatResolver>())
        Resolver->Strike(Source, Victim, Damage, From, MoveTemp(Result));
    else
    {
        const int32 Outcome = Victim->GetSword()->IncomingStrike(Source, Damage, From);
        if (Result) Result(Outcome);
    }
}
