#pragma once
#include "CoreMinimal.h"

/** Per-recipient caps leave 80 KiB/s of the 256 KiB/s connection for gameplay replication.
 * Reserve every chunk before sending a pose; budget exhaustion drops whole frames. */
struct FJapanSkateBudget
{
    static constexpr double PoseRate = 144. * 1024., BodyRate = 32. * 1024.;
    double PoseTokens = PoseRate * .1, BodyTokens = BodyRate * .1, Last = -1.;
    void Refill(double Now)
    {
        if (!FMath::IsFinite(Now)) return;
        if (Last >= 0.)
        {
            const double Dt = FMath::Clamp(Now - Last, 0., 1./60.);
            PoseTokens = FMath::Min(PoseRate * .1, PoseTokens + PoseRate * Dt);
            BodyTokens = FMath::Min(BodyRate * .1, BodyTokens + BodyRate * Dt);
        }
        Last = Now;
    }
    bool Spend(double Now, int32 Bytes, bool bBodies)
    {
        if (!FMath::IsFinite(Now) || Bytes <= 0) return false;
        Refill(Now);
        double& Tokens = bBodies ? BodyTokens : PoseTokens;
        if (Tokens < Bytes) return false;
        Tokens -= Bytes;
        return true;
    }
};
