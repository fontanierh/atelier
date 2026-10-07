#include "BotwMoveSet.h"
#include "BotwMoveSetDetail.h"
#include "JapanNetwork.h"
#include "WandererCharacter.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/NetConnection.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"

using namespace BotwMoveSetDetail;

namespace
{
bool TraceNetworkDefence()
{
#if !UE_BUILD_SHIPPING
    static const bool Enabled = FParse::Param(FCommandLine::Get(), TEXT("networkcombat"));
    return Enabled;
#else
    return false;
#endif
}
}

void UBotwMoveSet::ResetDefence()
{
    DefenceTimeline.Reset(); DefenceClock.Reset(); DefenceOverride.Reset();
    DefenceActionSerial = 0; DefenceInputTime = DefenceLastPress = -1.;
    bExternalDefenceChange = bHopInvulnerability = bDefenceMapped = false;
}

double UBotwMoveSet::DefenceWait() const
{
    return Character && !Character->IsLocallyControlled() ? DefenceClock.Wait : 0.;
}

void UBotwMoveSet::MapDefenceMove(float Timestamp, float Dt)
{
    if (!Character || !Character->HasAuthority() || Character->IsNpc()) return;
    const auto* Controller = Cast<APlayerController>(Character->Controller);
    const UNetConnection* Conn = Controller ? Controller->GetNetConnection() : nullptr;
    double Mapped = 0.;
    bDefenceMapped = DefenceClock.MapAccepted(Timestamp, Character->GetWorld()->GetTimeSeconds(),
        Conn ? Conn->RawPingInSeconds : 0., Conn ? Conn->GetAverageJitterInMS() * .001 : 0., Mapped, Dt);
    if (TraceNetworkDefence())
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence move ts=%.6f dt=%.6f host_dt=%.6f now=%.6f rtt=%.6f avg_rtt=%.6f jitter=%.6f mapped=%.6f one_way=%.6f wait=%.6f valid=%d"),
            Timestamp, Dt, Character->GetWorld()->GetDeltaSeconds(), Character->GetWorld()->GetTimeSeconds(),
            Conn ? Conn->RawPingInSeconds : 0., Conn ? Conn->AvgLag : 0.,
            Conn ? Conn->GetAverageJitterInMS() * .001 : 0., Mapped, DefenceClock.OneWay, DefenceClock.Wait, bDefenceMapped);
}

void UBotwMoveSet::RecordDefence(uint16 ThroughEdge)
{
    if (!Character || !Character->HasAuthority() || Character->IsNpc() || !JapanNetwork::IsOnline(Character->GetWorld())) return;
    const FBotwMove* Action = Current();
    FJapanDefenceSample S;
    S.Time = Character->GetWorld()->GetTimeSeconds(); S.ThroughEdge = ThroughEdge;
    S.bGround = Mode == EBotwMoveMode::Ground; S.bArmed = bArmed;
    S.bGuardHeld = bGuardHeld; S.bGuardBroken = GuardBroken > 0.f;
    const FName Parry = !HasShield() && Has(TEXT("SwordParry")) ? FName(TEXT("SwordParry")) : FName(TEXT("Parry"));
    S.bCanParry = S.bGround && !bDown && Has(Parry) &&
        (!Busy() || (Action && IsGuardHit(Action->Name) && SourceTime() >= Action->Input));
    S.bCanDodge = CanDodge(); S.bJumpDodge = bLocked && !bArmed;
    // A late live hop must not add a second invulnerability interval after its
    // original timeline window. Damage/flurry/down recovery remains world state.
    S.bRecovering = bDown || InFlurry() || (Invulnerable > 0.f && !bHopInvulnerability);
    S.Location = Character->GetActorLocation(); S.Forward = Character->GetActorForwardVector();
    DefenceTimeline.Record(S);
}

void UBotwMoveSet::EndDefenceAction()
{
    if (!DefenceActionSerial || !Character) return;
    if (!bExternalDefenceChange && Character->GetActionSerial() == DefenceActionSerial)
    {
        if (DefenceInputTime >= 0.) DefenceTimeline.CancelByInput(DefenceActionSerial, DefenceInputTime);
        else DefenceTimeline.SelfCutoff(DefenceActionSerial, DefenceActionStart + Character->GetActionTime());
    }
    DefenceActionSerial = 0;
}

bool UBotwMoveSet::PressNetwork(FName Button, uint16 Edge, uint16 AgeMilliseconds)
{
    if (!Character || !Character->HasAuthority() || Character->IsNpc() || Character->IsLocallyControlled())
        return Button == TEXT("drop_holds") ? (DropHolds(), true) : Press(Button);
    const double Now = Character->GetWorld()->GetTimeSeconds();
    double Original = Now - AgeMilliseconds * .001;
    const bool TimeValid = bDefenceMapped && DefenceClock.OriginalPress(AgeMilliseconds, Now, Original);
    const bool Ordered = Original >= DefenceLastPress;
    const bool Valid = TimeValid && Ordered;
    if (TraceNetworkDefence())
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence edge=%u button=%s ts=%.6f age_ms=%u now=%.6f mapped=%.6f press=%.6f press_source=%s prior=%.6f oldest=%.6f map_valid=%d time_valid=%d ordered=%d valid=%d"),
            Edge, *Button.ToString(), DefenceClock.LastTimestamp, AgeMilliseconds, Now, DefenceClock.LastMapped,
            Original, bDefenceMapped ? TEXT("mapped") : TEXT("raw_now_minus_age"), DefenceLastPress,
            Now - DefenceClock.MaximumRewind, bDefenceMapped, TimeValid, Ordered, Valid);
    if (!Valid)
    {
        ++DefenceRejectedTimes;
        if (Button == TEXT("guard") || Button == TEXT("guard_release") || Button == TEXT("drop_holds") ||
            Button == TEXT("jump") || Button == TEXT("dodge")) ++DefensiveRejectedTimes;
        Original = -1.;
    }
    else DefenceLastPress = Original;
    bool Added = false;
    if (Valid)
    {
        if (Button == TEXT("guard")) DefenceTimeline.Hold(Edge, Original, true);
        if (Button == TEXT("guard_release") || Button == TEXT("drop_holds")) DefenceTimeline.Hold(Edge, Original, false);
        const auto* Sample = DefenceTimeline.At(Original);
        if (Sample && Button == TEXT("jump") && Sample->bCanParry && Sample->bArmed && DefenceTimeline.GuardHeld(Original, *Sample))
        {
            const FName Name = !HasShield() && Has(TEXT("SwordParry")) ? FName(TEXT("SwordParry")) : FName(TEXT("Parry"));
            if (const FBotwMove* M = Find(Name))
                for (const FVector2f& W : M->Guard)
                    Added |= DefenceTimeline.Add(Edge, Original, EJapanDefence::Parry,
                        FMath::Max(0., double(W.X - M->Start) / M->Rate), double(W.Y - M->Start) / M->Rate);
        }
        else if (Sample && (Button == TEXT("dodge") || (Button == TEXT("jump") && Sample->bJumpDodge)))
        {
            const FVector Local = Character->GetActorRotation().UnrotateVector(Wish());
            const bool Side = FMath::Abs(Local.Y) > .3f && FMath::Abs(Local.Y) >= FMath::Abs(Local.X) && Has(TEXT("HopL")) && Has(TEXT("HopR"));
            const float Height = (Side ? GetParam(TEXT("PlayerSideStep.Height"), .8f) : GetParam(TEXT("PlayerBackJump.BJHeight"), 1.11f)) * 100.f * Scale();
            const float G = Gravity(), Flight = 2.f * FMath::Sqrt(2.f * G * Height) / FMath::Max(G, 1.f);
            Added = DefenceTimeline.Add(Edge, Original, EJapanDefence::Dodge, 0.,
                FMath::Min(GetParam(TEXT("PlayerSideStep.NoDamageTime"), 40.f) / 30.f, Flight + .1f), .25);
        }
    }
    const uint32 Previous = Character->GetActionSerial();
    TGuardValue<double> OriginalInput(DefenceInputTime, Original);
    const bool Result = Button == TEXT("drop_holds") ? (DropHolds(), true) : Press(Button);
    if (Added && Previous != Character->GetActionSerial() && (IsHop(CurrentName()) || IsParry(CurrentName())))
    {
        DefenceActionSerial = Character->GetActionSerial(); DefenceActionStart = Now;
        DefenceTimeline.BindAction(Edge, DefenceActionSerial, Now);
    }
    return Result;
}

int32 UBotwMoveSet::ResolveNetworkStrike(AActor* Source, float Damage, const FVector& From, double Contact)
{
    const float Cosine = FMath::Cos(FMath::DegreesToRadians(GetParam(TEXT("GuardableAngle"), 120.f) * .5f));
    uint16 Edge = 0;
    const EJapanDefence Decision = DefenceTimeline.Resolve(Contact, From, Cosine, Edge);
    TGuardValue<TOptional<EJapanDefence>> Override(DefenceOverride, TOptional<EJapanDefence>(Decision));
    const float PriorGuardBroken = GuardBroken;
    const int32 Outcome = IncomingStrike(Source, Damage, From);
    const double Recovery = Outcome == 0 || InFlurry() ? Invulnerable : 0.;
    DefenceTimeline.Reaction(Contact, Recovery, GuardBroken > PriorGuardBroken ? GuardBroken : 0.);
    return Outcome;
}
