#pragma once
#include "CoreMinimal.h"

/** Real host time bounds accepted simulation; missing packets never invent client timestamps. */
struct FJapanMoveClock
{
    static constexpr double Timeout = .75;
    static constexpr double InitialSlack = .125;
    double LastRefill = -1., LastAccepted = -1., Credit = InitialSlack;

    void BeginEpoch(double Now)
    {
        *this = FJapanMoveClock();
        // Count real host time from the handoff, including the wait for the
        // owner's first move. A capped first step must not erase that interval.
        Refill(Now);
    }

    void Refill(double Now)
    {
        if (LastRefill >= 0.) Credit = FMath::Min(Timeout, Credit + FMath::Max(0., Now - LastRefill));
        LastRefill = FMath::Max(LastRefill, Now);
    }
    bool Allows(double Now, double Dt)
    {
        if (!FMath::IsFinite(Now) || !FMath::IsFinite(Dt) || Dt <= 0.) return false;
        Refill(Now);
        return Dt <= Credit + 1.e-6;
    }
    void Accepted(double Now, double Dt)
    {
        Refill(Now);
        Credit = FMath::Max(0., Credit - Dt);
        LastAccepted = Now;
    }
    bool Expired(double Now) const { return LastAccepted >= 0. && Now - LastAccepted >= Timeout; }
};
