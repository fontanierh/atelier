#include "SkateRails.h"

int32 USkateRailSubsystem::Add(FSkateRail Rail)
{
    if (Rail.Points.Num() < 2) return INDEX_NONE;
    Rail.Lengths.SetNum(Rail.Points.Num()); Rail.Lengths[0] = 0.f;
    Rail.Bounds = FBox(ForceInit);
    for (int32 I = 0; I < Rail.Points.Num(); ++I)
    {
        if (I) Rail.Lengths[I] = Rail.Lengths[I - 1] + FVector::Distance(Rail.Points[I], Rail.Points[I - 1]);
        Rail.Bounds += Rail.Points[I];
    }
    Rail.Bounds = Rail.Bounds.ExpandBy(60.f);
    return Rails.Add(MoveTemp(Rail));
}

FVector USkateRailSubsystem::Sample(int32 R, float S, FVector& Tangent) const
{
    const FSkateRail& Rail = Rails[R];
    int32 I = 1;
    while (I < Rail.Points.Num() - 1 && Rail.Lengths[I] < S) ++I;
    const float Span = FMath::Max(Rail.Lengths[I] - Rail.Lengths[I - 1], KINDA_SMALL_NUMBER);
    const float U = FMath::Clamp((S - Rail.Lengths[I - 1]) / Span, 0.f, 1.f);
    Tangent = (Rail.Points[I] - Rail.Points[I - 1]).GetSafeNormal();
    return FMath::Lerp(Rail.Points[I - 1], Rail.Points[I], U);
}
