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

int32 USkateRailSubsystem::FindNear(const FVector& P, float MaxFlat, float MinAbove, float MaxAbove, float& OutS, FVector& OutPoint, FVector& OutTangent) const
{
    int32 Best = INDEX_NONE; float BestFlat = MaxFlat;
    for (int32 R = 0; R < Rails.Num(); ++R)
    {
        const FSkateRail& Rail = Rails[R];
        if (!Rail.Bounds.IsInsideOrOn(P)) continue;
        for (int32 I = 1; I < Rail.Points.Num(); ++I)
        {
            const FVector A = Rail.Points[I - 1], B = Rail.Points[I];
            // Nearest in plan: grinds are captured by where the truck is over the rail, then by height.
            const FVector2D A2(A), AB(B - A), AP = FVector2D(P) - A2;
            const float Len2 = AB.SizeSquared();
            const float U = Len2 > KINDA_SMALL_NUMBER ? FMath::Clamp(FVector2D::DotProduct(AP, AB) / Len2, 0.f, 1.f) : 0.f;
            const FVector Q = FMath::Lerp(A, B, U);
            const float Flat = FVector2D::Distance(FVector2D(P), FVector2D(Q));
            const float Above = P.Z - Q.Z;
            if (Flat < BestFlat && Above >= MinAbove && Above <= MaxAbove)
            {
                BestFlat = Flat; Best = R; OutPoint = Q;
                OutS = FMath::Lerp(Rail.Lengths[I - 1], Rail.Lengths[I], U);
                OutTangent = (B - A).GetSafeNormal();
            }
        }
    }
    return Best;
}
