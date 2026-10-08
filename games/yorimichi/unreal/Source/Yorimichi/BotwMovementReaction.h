#pragma once
#include "JapanReactionJournal.h"

/** Frozen movement effects of one resolved contact. No health, cues, counters,
 * actor references or unrelated prediction state can travel in this payload. */
struct FBotwMovementReaction
{
    static constexpr float HitImmunitySeconds = .7f;
    static constexpr int32 WireBytes = 2 + 10 * 4 + 12 * 8;
    enum : uint16
    {
        ClearCharge = 1, ClearLunge = 2, ResetCombo = 4, Down = 8,
        Immunity = 16, Flinch = 32, SetVelocity = 64, Launch = 128,
        BreakGuard = 256, LeaveGlide = 512, LeaveClimb = 1024,
        PerfectDodge = 2048, ClearHop = 4096, HasFlurryPoint = 8192,
        AllFlags = 16383
    };
    uint16 Flags = 0;
    FName Action;
    float Blend = 0.f, SourceStart = 0.f, PlayRate = 1.f;
    FVector Impulse = FVector::ZeroVector, FlinchAxis = FVector::ZeroVector;
    FVector FlurryPoint = FVector::ZeroVector;
    float Invulnerable = 0.f, GuardBroken = 0.f, FlurryTime = 0.f;
    float FlinchAngle = 0.f, FlinchPeak = 0.f, FlinchTwist = 0.f;
    // A climb exit freezes its release direction and no-climb duration too.
    FVector ClimbRelease = FVector::ZeroVector;
    float NoClimb = 0.f;
    bool IsValid() const;
    bool Encode(FJapanReactionValue& Out) const;
    static bool Decode(const FJapanReactionValue& Value, FBotwMovementReaction& Out);
};
