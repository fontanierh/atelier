#pragma once
#include "CoreMinimal.h"

namespace SwordCombat
{
// Real action seconds, shared by local contact and the server's input history.
constexpr float PerfectParrySeconds = .12f;
constexpr float NpcHitImmunitySeconds = .10f;

inline bool CrossesWindow(float Before, float Now, const FVector2f& Window)
{
    return Now >= Window.X && Before <= Window.Y;
}

/** Contact-owned state: never predicted or replayed by movement. */
struct FGuardPressure
{
    float Value = 0.f;
    double Contact = -100.;

    float At(double Now) const
    {
        return FMath::Max(0.f, Value - float(FMath::Max(0., Now - Contact - 1.1)) * .28f);
    }
    bool Block(float Damage, double Now, float HeavyThreshold)
    {
        Value = FMath::Clamp(At(Now) + .14f + FMath::Max(0.f, Damage) * .012f, 0.f, 1.f);
        Contact = Now;
        const bool Broken = Damage >= HeavyThreshold || Value >= 1.f;
        if (Broken) Value = 0.f;
        return Broken;
    }
    void Parry(double Now)
    {
        Value = FMath::Max(0.f, At(Now) - .45f);
        Contact = Now;
    }
};
}
