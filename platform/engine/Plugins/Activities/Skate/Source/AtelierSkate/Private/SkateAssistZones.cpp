#include "SkateAssistZones.h"

bool FSkateAssistZone::Contains(const FVector& At) const
{
    const FVector Local = FRotator(0., YawDeg, 0.).UnrotateVector(At - Centre);
    return FMath::Abs(Local.X) <= HalfExtent.X && FMath::Abs(Local.Y) <= HalfExtent.Y && FMath::Abs(Local.Z) <= HalfExtent.Z;
}

void USkateAssistSubsystem::Add(FSkateAssistZone Zone)
{
    if (Zone.HalfExtent.GetMin() <= 0. || !FMath::IsFinite(Zone.VertAssistMax)) return;
    Zone.VertAssistMax = FMath::Clamp(Zone.VertAssistMax, 0.f, 1.f);
    Zones.Add(MoveTemp(Zone));
}

void USkateAssistSubsystem::Remove(const UObject* Owner)
{
    Zones.RemoveAll([Owner](const FSkateAssistZone& Zone) { return Zone.Owner.Get() == Owner; });
}

float USkateAssistSubsystem::VertAssistLimit(std::initializer_list<FVector> At) const
{
    float Limit = 1.f;
    for (const FSkateAssistZone& Zone : Zones)
    {
        if (Zone.VertAssistMax >= Limit || (!Zone.Owner.IsExplicitlyNull() && !Zone.Owner.IsValid())) continue;
        for (const FVector& P : At) if (Zone.Contains(P)) { Limit = Zone.VertAssistMax; break; }
    }
    return Limit;
}
