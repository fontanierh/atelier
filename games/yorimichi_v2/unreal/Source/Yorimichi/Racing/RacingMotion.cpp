#include "RacingMotion.h"

namespace RacingMotion
{
    double Distance(const FPlan& Plan, double T, double* Speed)
    {
        double V = 0.;
        double D = 0.;
        if (T < 0.)
        {
            // Walking to the start over the parade's first minute, then lined up there for the last LineupSeconds.
            const double Walk = ParadeSeconds - LineupSeconds;
            const double Into = FMath::Clamp(T + ParadeSeconds, 0., Walk);
            D = -ParadeDistance + ParadeDistance * Into / Walk;
            V = (Into > 0. && Into < Walk) ? ParadeDistance / Walk : 0.;
        }
        else if (!Plan.IsRun() || Plan.Distance <= 0.)
        {
            D = 0.;
        }
        else if (T < Plan.FinishTime())
        {
            // Monotone cubic Hermite (Fritsch-Carlson) through (0, 0) and the stage ends; the start is standing (speed 0).
            double Tk[5] = {0.}, Dk[5] = {0.};
            for (int32 I = 0; I < 4; ++I) { Tk[I + 1] = Plan.Splits[I]; Dk[I + 1] = Plan.Distance * StageEnd[I]; }
            double Slope[4], M[5];
            for (int32 I = 0; I < 4; ++I) Slope[I] = (Dk[I + 1] - Dk[I]) / FMath::Max(Tk[I + 1] - Tk[I], 1e-3);
            M[0] = 0.;
            for (int32 I = 1; I < 4; ++I) M[I] = (Slope[I - 1] * Slope[I] <= 0.) ? 0. : (Slope[I - 1] + Slope[I]) * .5;
            M[4] = Slope[3];
            for (int32 I = 0; I < 4; ++I)
            {
                // Keep each piece monotone: the tangents stay within three times the secant.
                const double A = M[I] / FMath::Max(Slope[I], 1e-6), B = M[I + 1] / FMath::Max(Slope[I], 1e-6);
                const double H = A * A + B * B;
                if (H > 9.) { const double Tau = 3. / FMath::Sqrt(H); M[I] = Tau * A * Slope[I]; M[I + 1] = Tau * B * Slope[I]; }
            }
            int32 K = 0;
            while (K < 3 && T >= Tk[K + 1]) ++K;
            const double H = FMath::Max(Tk[K + 1] - Tk[K], 1e-3);
            const double U = FMath::Clamp((T - Tk[K]) / H, 0., 1.);
            const double U2 = U * U, U3 = U2 * U;
            D = (2. * U3 - 3. * U2 + 1.) * Dk[K] + (U3 - 2. * U2 + U) * H * M[K] + (-2. * U3 + 3. * U2) * Dk[K + 1] + (U3 - U2) * H * M[K + 1];
            V = ((6. * U2 - 6. * U) * Dk[K] + (3. * U2 - 4. * U + 1.) * H * M[K] + (-6. * U2 + 6. * U) * Dk[K + 1] + (3. * U2 - 2. * U) * H * M[K + 1]) / H;
        }
        else
        {
            // Past the post at the last stage's speed, easing to a trot.
            const double Last = Plan.FinishTime() - Plan.Splits[2];
            const double V0 = FMath::Max(Plan.Distance * (StageEnd[3] - StageEnd[2]) / FMath::Max(Last, 1e-3), CoolDown);
            const double Since = T - Plan.FinishTime();
            const double Ease = (V0 - CoolDown) / PullUp;
            if (Since < Ease) { V = V0 - PullUp * Since; D = Plan.Distance + V0 * Since - .5 * PullUp * Since * Since; }
            else { V = CoolDown; D = Plan.Distance + V0 * Ease - .5 * PullUp * Ease * Ease + CoolDown * (Since - Ease); }
        }
        if (Speed) *Speed = FMath::Max(V, 0.);
        return D;
    }
}
