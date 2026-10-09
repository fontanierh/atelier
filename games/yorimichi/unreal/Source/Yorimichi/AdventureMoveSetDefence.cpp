#include "AdventureMoveSet.h"
#include "AdventureMoveSetDetail.h"
#include "JapanNetwork.h"
#include "JapanCharacterMovement.h"
#include "WandererCharacter.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/NetConnection.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"

using namespace AdventureMoveSetDetail;

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

void UAdventureMoveSet::ResetDefence()
{
    DefenceTimeline.Reset(); DefenceClock.Reset(); DefenceOverride.Reset();
    DefenceActionSerial = 0; DefenceInputTime = DefenceLastPress = -1.;
    bExternalDefenceChange = bHopInvulnerability = bDefenceMapped = false;
    bDefenceGetUpPending = false; DefenceGetUpUntil = -1.;
    ReactionActionEdge.Reset(); ReactionAttackEdge.Reset(); ReactionGuardEdge.Reset();
}

double UAdventureMoveSet::DefenceWait() const
{
    return Character && !Character->IsLocallyControlled() ? DefenceClock.Wait : 0.;
}

bool UAdventureMoveSet::MapDefenceMove(float Timestamp, float Dt)
{
    if (!Character || !Character->HasAuthority() || Character->IsNpc()) return false;
    const auto* Controller = Cast<APlayerController>(Character->Controller);
    const UNetConnection* Conn = Controller ? Controller->GetNetConnection() : nullptr;
    double Mapped = 0.;
    bDefenceMapped = DefenceClock.MapAccepted(Timestamp, Character->GetWorld()->GetTimeSeconds(),
        Conn ? Conn->RawPingInSeconds : 0., Conn ? Conn->GetAverageJitterInMS() * .001 : 0., Mapped, Dt,
        Character->GetWorld()->GetDeltaSeconds());
    if (TraceNetworkDefence())
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence move ts=%.6f dt=%.6f host_dt=%.6f now=%.6f rtt=%.6f avg_rtt=%.6f jitter=%.6f mapped=%.6f one_way=%.6f spread=%.6f wait=%.6f valid=%d"),
            Timestamp, Dt, Character->GetWorld()->GetDeltaSeconds(), Character->GetWorld()->GetTimeSeconds(),
            Conn ? Conn->RawPingInSeconds : 0., Conn ? Conn->AvgLag : 0.,
            Conn ? Conn->GetAverageJitterInMS() * .001 : 0., Mapped, DefenceClock.OneWay, DefenceClock.ArrivalSpread, DefenceClock.Wait, bDefenceMapped);
    return bDefenceMapped;
}

bool UAdventureMoveSet::GetUpProtectedAt(double SampleTime)
{
    // First post-step sample: at most one admitted sub-step later than get-up.
    // Unlike Invulnerable this deadline cannot be rewritten by an ACK payload.
    if (bDefenceGetUpPending)
    { DefenceGetUpUntil = SampleTime + 1.; bDefenceGetUpPending = false; }
    return SampleTime < DefenceGetUpUntil;
}

void UAdventureMoveSet::RecordDefence(uint16 ThroughEdge, double BeforeStep, bool bAcceptedMove)
{
    if (!Character || !Character->HasAuthority() || Character->IsNpc() || !JapanNetwork::IsOnline(Character->GetWorld())) return;
    // A forced server tick has no fresh accepted input timestamp. It may simulate
    // movement, but must never rewrite old eligibility at the previous mapping.
    const bool bRemote = !Character->IsLocallyControlled();
    if (bRemote && (!bAcceptedMove || !bDefenceMapped)) return;
    const FAdventureMove* Action = Current();
    FJapanDefenceSample S;
    S.Time = Character->GetWorld()->GetTimeSeconds(); S.ThroughEdge = ThroughEdge;
    S.bGround = Mode == EAdventureMoveMode::Ground; S.bArmed = bArmed;
    const auto* Movement = Cast<UJapanCharacterMovement>(Character->GetCharacterMovement());
    S.bGuardHeld = bGuardHeld && (!bRemote || !Movement || Movement->ReactionEdgeEligible(ReactionGuardEdge, true));
    S.bGuardBroken = !bRemote && GuardBroken > 0.f; // Remote breaks are contact-time timeline entries.
    const FName Parry = !HasShield() && Has(TEXT("SwordParry")) ? FName(TEXT("SwordParry")) : FName(TEXT("Parry"));
    S.bCanParry = S.bGround && !bDown && Has(Parry) &&
        (!Busy() || (Action && IsGuardHit(Action->Name) && SourceTime() >= Action->Input));
    S.bCanDodge = CanDodge(); S.bJumpDodge = bLocked && !bArmed;
    const double SampleTime = bRemote ? DefenceClock.LastMapped - BeforeStep : S.Time;
    const bool GetUpProtection = GetUpProtectedAt(SampleTime);
    // Remote hit/flurry immunity is resolved at contact, not when ACK motion
    // starts. Heavy down state remains physical; get-up has its own fixed end.
    S.bRecovering = bDown || (bRemote ? GetUpProtection :
        (InFlurry() || (Invulnerable > 0.f && !bHopInvulnerability)));
    S.Location = Character->GetActorLocation(); S.Forward = Character->GetActorForwardVector();
    if (bRemote) DefenceTimeline.RecordMapped(S, DefenceClock.LastMapped, BeforeStep);
    else DefenceTimeline.Record(S);
    if (TraceNetworkDefence() && !Character->IsLocallyControlled())
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence sample time=%.6f mapped=%.6f ts=%.6f through=%u ground=%d armed=%d can_parry=%d can_dodge=%d held=%d broken=%d recovering=%d busy=%d action=%s source_time=%.6f serial=%u"),
            DefenceTimeline.LatestTime(), DefenceClock.LastMapped, DefenceClock.LastTimestamp, ThroughEdge,
            S.bGround, S.bArmed, S.bCanParry, S.bCanDodge, S.bGuardHeld, S.bGuardBroken,
            S.bRecovering, Busy(), *CurrentName().ToString(), SourceTime(), Character->GetActionSerial());
}

void UAdventureMoveSet::EndDefenceAction()
{
    if (!DefenceActionSerial || !Character) return;
    if (!bExternalDefenceChange && Character->GetActionSerial() == DefenceActionSerial)
    {
        if (DefenceInputTime >= 0.) DefenceTimeline.CancelByInput(DefenceActionSerial, DefenceInputTime);
        else DefenceTimeline.SelfCutoff(DefenceActionSerial, DefenceActionStart + Character->GetActionTime());
    }
    DefenceActionSerial = 0;
}

bool UAdventureMoveSet::PressNetwork(FName Button, uint16 Edge, uint16 AgeMilliseconds)
{
    if (!Character || !Character->HasAuthority() || Character->IsNpc() || Character->IsLocallyControlled())
        return Button == TEXT("drop_holds") ? (DropHolds(), true) : Press(Button);
    const double Now = Character->GetWorld()->GetTimeSeconds();
    double Original = Now - AgeMilliseconds * .001;
    const bool TimeValid = bDefenceMapped && DefenceClock.OriginalPress(AgeMilliseconds, Now, Original);
    const bool Ordered = Original >= DefenceLastPress;
    auto* Movement = Cast<UJapanCharacterMovement>(Character->GetCharacterMovement());
    const bool Eligible = !Movement || Movement->ReactionEdgeEligible(Edge);
    if (!Eligible && (Button == TEXT("guard") || Button == TEXT("dodge") || Button == TEXT("jump")))
        Movement->RecordSuppressedDefenceInput();
    const bool Valid = TimeValid && Ordered;
    if (Button == TEXT("attack")) ReactionAttackEdge = Edge;
    if (Button == TEXT("guard")) ReactionGuardEdge = Edge;
    if (TraceNetworkDefence())
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence edge=%u button=%s ts=%.6f age_ms=%u now=%.6f mapped=%.6f press=%.6f press_source=%s prior=%.6f oldest=%.6f map_valid=%d time_valid=%d ordered=%d valid=%d one_way=%.6f spread=%.6f step=%.6f slow_host=%.6f"),
            Edge, *Button.ToString(), DefenceClock.LastTimestamp, AgeMilliseconds, Now, DefenceClock.LastMapped,
            Original, bDefenceMapped ? TEXT("mapped") : TEXT("raw_now_minus_age"), DefenceLastPress,
            Now - DefenceClock.MaximumRewind, bDefenceMapped, TimeValid, Ordered, Valid,
            DefenceClock.OneWay, DefenceClock.ArrivalSpread, DefenceClock.AcceptedStep, DefenceClock.SlowHost);
    if (!Valid)
    {
        ++DefenceRejectedTimes;
        if (Button == TEXT("guard") || Button == TEXT("guard_release") || Button == TEXT("drop_holds") ||
            Button == TEXT("jump") || Button == TEXT("dodge")) ++DefensiveRejectedTimes;
        Original = -1.;
    }
    else DefenceLastPress = Original;
    bool Added = false;
    // Eligibility alone is masked. Press below still runs with the exact input
    // so authority physics stays in the owner's predicted lineage.
    if (Valid)
    {
        if (Button == TEXT("guard")) DefenceTimeline.Hold(Edge, Original, Eligible);
        if (Button == TEXT("guard_release") || Button == TEXT("drop_holds")) DefenceTimeline.Hold(Edge, Original, false);
    }
    if (Valid && Eligible)
    {
        const auto* Sample = DefenceTimeline.At(Original);
        if (TraceNetworkDefence())
            UE_LOG(LogTemp, Display, TEXT("NETWORK defence eligibility edge=%u button=%s press=%.6f sample=%.6f through=%u ground=%d armed=%d can_parry=%d can_dodge=%d jump_dodge=%d held=%d broken=%d recovering=%d"),
                Edge, *Button.ToString(), Original, Sample ? Sample->Time : -1., Sample ? Sample->ThroughEdge : 0,
                Sample && Sample->bGround, Sample && Sample->bArmed, Sample && Sample->bCanParry,
                Sample && Sample->bCanDodge, Sample && Sample->bJumpDodge, Sample && DefenceTimeline.GuardHeld(Original, *Sample),
                Sample && Sample->bGuardBroken, Sample && Sample->bRecovering);
        if (Sample && Button == TEXT("jump") && Sample->bCanParry && Sample->bArmed && DefenceTimeline.GuardHeld(Original, *Sample))
        {
            const FName Name = !HasShield() && Has(TEXT("SwordParry")) ? FName(TEXT("SwordParry")) : FName(TEXT("Parry"));
            if (const FAdventureMove* M = Find(Name))
            {
                if (TraceNetworkDefence())
                    UE_LOG(LogTemp, Display, TEXT("NETWORK defence authored edge=%u action=%s intervals=%d"), Edge, *Name.ToString(), M->Guard.Num());
                for (const FVector2f& W : M->Guard)
                {
                    const double Start = FMath::Max(0., double(W.X - M->Start) / M->Rate), End = double(W.Y - M->Start) / M->Rate;
                    const bool IntervalAdded = DefenceTimeline.Add(Edge, Original, EJapanDefence::Parry, Start, End);
                    Added |= IntervalAdded;
                    if (TraceNetworkDefence())
                        UE_LOG(LogTemp, Display, TEXT("NETWORK defence interval edge=%u start=%.6f end=%.6f added=%d"),
                            Edge, Original + Start, Original + End, IntervalAdded);
                }
            }
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
    if (TraceNetworkDefence())
    {
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence added edge=%u button=%s added=%d handled=%d action=%s serial_before=%u serial_after=%u bound_serial=%u"),
            Edge, *Button.ToString(), Added, Result, *CurrentName().ToString(), Previous,
            Character->GetActionSerial(), DefenceActionSerial);
        DefenceTimeline.Trace(Original, TEXT("press"));
    }
    return Result;
}

int32 UAdventureMoveSet::ResolveNetworkStrike(AActor* Source, float Damage, const FVector& From, double Contact)
{
    const float Cosine = FMath::Cos(FMath::DegreesToRadians(GetParam(TEXT("GuardableAngle"), 120.f) * .5f));
    uint16 Edge = 0;
    const EJapanDefence Decision = DefenceTimeline.Resolve(Contact, From, Cosine, Edge);
    if (TraceNetworkDefence())
    {
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence resolve now=%.6f contact=%.6f decision=%u edge=%u latest_sample=%.6f"),
            Character->GetWorld()->GetTimeSeconds(), Contact, uint32(Decision), Edge, DefenceTimeline.LatestTime());
        const auto* Sample = DefenceTimeline.At(Contact);
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence contact_sample contact=%.6f sample=%.6f through=%u ground=%d armed=%d held=%d broken=%d recovering=%d"),
            Contact, Sample ? Sample->Time : -1., Sample ? Sample->ThroughEdge : 0,
            Sample && Sample->bGround, Sample && Sample->bArmed,
            Sample && DefenceTimeline.GuardHeld(Contact, *Sample), Sample && Sample->bGuardBroken, Sample && Sample->bRecovering);
        DefenceTimeline.Trace(Contact, TEXT("contact"));
    }
    TGuardValue<TOptional<EJapanDefence>> Override(DefenceOverride, TOptional<EJapanDefence>(Decision));
    TGuardValue<float> RecoveryScope(ResolvedRecoverySeconds, 0.f);
    TGuardValue<float> BrokenScope(ResolvedGuardBrokenSeconds, 0.f);
    const int32 Outcome = IncomingStrike(Source, Damage, From);
    DefenceTimeline.Reaction(Contact, ResolvedRecoverySeconds, ResolvedGuardBrokenSeconds);
    return Outcome;
}

int32 UAdventureMoveSet::ResolveUnprotectedStrike(AActor* Source, float Damage, const FVector& From)
{
    TGuardValue<TOptional<EJapanDefence>> Override(DefenceOverride,TOptional<EJapanDefence>(EJapanDefence::None));
    TGuardValue<float> RecoveryScope(ResolvedRecoverySeconds, 0.f);
    TGuardValue<float> BrokenScope(ResolvedGuardBrokenSeconds, 0.f);
    const int32 Outcome = IncomingStrike(Source,Damage,From);
    if (Character && Character->HasAuthority() && JapanNetwork::IsOnline(Character->GetWorld()))
        DefenceTimeline.Reaction(Character->GetWorld()->GetTimeSeconds(), ResolvedRecoverySeconds, ResolvedGuardBrokenSeconds);
    return Outcome;
}
