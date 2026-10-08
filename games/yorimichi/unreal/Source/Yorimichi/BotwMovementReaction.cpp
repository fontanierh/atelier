#include "BotwMovementReaction.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

namespace BotwReactionCodec
{
void Vector(FArchive& Ar, FVector& Value) { Ar << Value.X << Value.Y << Value.Z; }
void Fields(FArchive& Ar, FBotwMovementReaction& Value)
{
    Ar << Value.Flags << Value.Blend << Value.SourceStart << Value.PlayRate;
    Vector(Ar, Value.Impulse); Vector(Ar, Value.FlinchAxis); Vector(Ar, Value.FlurryPoint);
    Ar << Value.Invulnerable << Value.GuardBroken << Value.FlurryTime;
    Ar << Value.FlinchAngle << Value.FlinchPeak << Value.FlinchTwist;
    Vector(Ar, Value.ClimbRelease); Ar << Value.NoClimb;
}
}

bool FBotwMovementReaction::IsValid() const
{
    return !(Flags & ~AllFlags) && !((Flags & SetVelocity) && (Flags & Launch)) &&
        !((Flags & LeaveGlide) && (Flags & LeaveClimb)) &&
        !Impulse.ContainsNaN() && !FlinchAxis.ContainsNaN() && !FlurryPoint.ContainsNaN() && !ClimbRelease.ContainsNaN() &&
        FMath::IsFinite(Blend) && Blend >= 0.f && FMath::IsFinite(SourceStart) && SourceStart >= 0.f &&
        FMath::IsFinite(PlayRate) && PlayRate > 0.f &&
        FMath::IsFinite(Invulnerable) && Invulnerable >= 0.f && FMath::IsFinite(GuardBroken) && GuardBroken >= 0.f &&
        FMath::IsFinite(FlurryTime) && FlurryTime >= 0.f && FMath::IsFinite(NoClimb) && NoClimb >= 0.f &&
        FMath::IsFinite(FlinchAngle) && FMath::IsFinite(FlinchPeak) && FlinchPeak >= 0.f && FMath::IsFinite(FlinchTwist) &&
        Impulse.GetAbsMax() <= 10000. && ClimbRelease.GetAbsMax() <= 10000. && FlurryPoint.GetAbsMax() <= 1.e9 &&
        FlinchAxis.SizeSquared() <= 1.001 && Blend <= 10.f && SourceStart <= 3600.f && PlayRate <= 100.f &&
        Invulnerable <= 60.f && GuardBroken <= 60.f && FlurryTime <= 60.f && NoClimb <= 60.f &&
        FMath::Abs(FlinchAngle) <= 360.f && FlinchPeak <= 10.f && FMath::Abs(FlinchTwist) <= 1.f;
}

bool FBotwMovementReaction::Encode(FJapanReactionValue& Out) const
{
    Out = FJapanReactionValue();
    if (!IsValid()) return false;
    FBotwMovementReaction Copy = *this;
    FMemoryWriter Writer(Out.Bytes, true);
    BotwReactionCodec::Fields(Writer, Copy);
    Out.Action = Action;
    return !Writer.IsError() && Out.Bytes.Num() == WireBytes && Out.IsValid();
}

bool FBotwMovementReaction::Decode(const FJapanReactionValue& Value, FBotwMovementReaction& Out)
{
    Out = FBotwMovementReaction();
    if (!Value.IsValid() || Value.Bytes.Num() != WireBytes) return false;
    FBotwMovementReaction Decoded;
    FMemoryReader Reader(Value.Bytes, true);
    BotwReactionCodec::Fields(Reader, Decoded);
    if (Reader.IsError() || Reader.Tell() != Reader.TotalSize() || !Decoded.IsValid()) return false;
    Decoded.Action = Value.Action;
    Out = Decoded;
    return true;
}
