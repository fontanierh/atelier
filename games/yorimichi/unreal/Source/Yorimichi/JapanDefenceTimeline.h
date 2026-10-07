#pragma once
#include "CoreMinimal.h"

/** Historical, server-computed eligibility. No client sends any of these booleans. */
struct FJapanDefenceSample
{
    double Time = 0.;
    uint16 ThroughEdge = 0;
    bool bCanParry = false, bCanDodge = false, bGuardHeld = false;
    bool bJumpDodge = false;
    bool bArmed = false, bGround = false, bRecovering = false, bGuardBroken = false;
    FVector Location = FVector::ZeroVector, Forward = FVector::ForwardVector;
};

enum class EJapanDefence : uint8 { None, Guard, Parry, Dodge, PerfectDodge, Recovering };

/** A bounded adjudication history, separate from the live move set. Times are mapped by
 *  the host from accepted movement samples; clip intervals have already been converted
 *  to world seconds using (clip time - source start) / play rate. */
class FJapanDefenceTimeline
{
public:
    static constexpr double MaximumHistory = .5;
    static constexpr double MaximumSampleGap = .05;
    struct FWindow
    {
        uint16 Edge = 0;
        double Press = 0., Start = 0., End = 0., PerfectEnd = 0.;
        EJapanDefence Kind = EJapanDefence::None;
        bool bConsumed = false;
        uint32 ActionSerial = 0;
        double LiveStart = 0., SelfCutoff = TNumericLimits<double>::Max();
    };
    void Reset() { Samples.Reset(); Windows.Reset(); Holds.Reset(); Reactions.Reset(); AuthoredFallbacks = HoldOverflows = MissingSamples = 0; OldestPending = TNumericLimits<double>::Max(); }
    uint32 AuthoredFallbacks = 0, HoldOverflows = 0, MissingSamples = 0;
    void RetainThrough(double Contact) { OldestPending = Contact; }
    double LatestTime() const { return Samples.IsEmpty() ? -1. : Samples.Last().Time; }
    /** Bind only the action actually started by this original edge, never a later action.
     * A historically eligible edge can have no live action; that uses authored timings. */
    void BindAction(uint16 Edge, uint32 Serial, double LiveStart);
    /** Call for a landing or natural end, never for external damage or knockback. */
    void SelfCutoff(uint32 Serial, double LiveTime);
    /** A later input's cancellation already has an original host-mapped time. */
    void CancelByInput(uint32 Serial, double OriginalTime);
    void Record(const FJapanDefenceSample& Sample);
    /** Earlier contacts adjudicated in order are real world changes, at contact time.
     * Unlike a projected late live animation, these can invalidate later defence. */
    void Reaction(double Contact, double RecoverySeconds, double GuardBrokenSeconds);
    const FJapanDefenceSample* At(double Time) const;
    bool GuardHeld(double Time, const FJapanDefenceSample& Sample) const;
    void Hold(uint16 Edge, double Time, bool bHeld);
    bool Add(uint16 Edge, double Press, EJapanDefence Kind, double StartAfterPress,
        double EndAfterPress, double PerfectAfterPress = 0.); // zero means no perfect-dodge window
    EJapanDefence Resolve(double Contact, const FVector& From, float GuardCosine, uint16& UsedEdge);
private:
    struct FReaction { double Time, RecoveryEnd, GuardEnd; };
    TArray<FReaction, TInlineAllocator<32>> Reactions;
    double OldestPending = TNumericLimits<double>::Max();
    struct FHold { uint16 Edge; double Time; bool bHeld; };
    TArray<FJapanDefenceSample, TInlineAllocator<128>> Samples;
    TArray<FWindow, TInlineAllocator<32>> Windows;
    TArray<FHold, TInlineAllocator<64>> Holds;
};
