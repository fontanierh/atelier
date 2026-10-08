#pragma once
// Helpers shared by the BotwMoveSet*.cpp files (one move set, split by section).
#include "BotwMoveSet.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Dom/JsonObject.h"

namespace BotwMoveSetDetail
{
    // The paraglider's two handle tubes (right, left) in its own frame (cm): the straight stretch at the bottom of each of
    // its U-shaped handles, measured on SK_LinkGlider's vertices.
    inline const FVector GliderHandles[2][2] = { { FVector(-24.8, -14.2, 1.2), FVector(-30.5, 2.8, 1.1) },
                                                 { FVector(25.4, -14.2, 1.6), FVector(30.1, 2.9, 1.0) } };
    // Each handle tube's cross-section along that stretch (cm, its own frame): an even oval, the major radius along the
    // glider's up axis and the minor across it, from the posed tube's vertices in game (#7633: the fingers wrap its
    // surface, not its axis; rings at the stretch's ends take in the U's bends and read up to 20% larger).
    inline const FVector2D GliderHandleRadii[2] = { FVector2D(3.30, 2.80), FVector2D(3.30, 2.80) };
    // The sword's grip (LinkSword.glb's vertex rings), in lengths of its handle (its origin to the pommel's end; the origin
    // lies inside the grip, the guard's face beyond it): the stretch a hand closes round, from where the pommel flares to
    // the guard's face, and its oval at either end and at its waist, the major radius across the blade's width and the
    // minor across its thickness (#7735: the old stretch stopped 4.5 cm short of the guard, a finger there unmodelled).
    inline const float SwordGripSpan[2] = { .709f, -.231f };
    inline const FVector2D SwordGripRadii[3] = { FVector2D(.125, .090), FVector2D(.126, .076), FVector2D(.113, .070) };
    inline const float SwordGripWaist = .523f;   // the waist's ring (.217), of the way from the first end to the second
    inline bool In(FName Name, std::initializer_list<const TCHAR*> Names)
    {
        for (const TCHAR* N : Names) if (Name == FName(N)) return true;
        return false;
    }
    inline bool Prefixed(FName Name, std::initializer_list<const TCHAR*> Prefixes)
    {
        if (Name.IsNone()) return false;
        const FString S = Name.ToString();
        for (const TCHAR* P : Prefixes) if (S.StartsWith(P, ESearchCase::CaseSensitive)) return true;
        return false;
    }
    /** Blade work: the clip itself moves the arms, so the carry layers stay off. */
    inline bool IsSwordAction(FName N)
    {
        return Prefixed(N, { TEXT("Cut"), TEXT("Charge"), TEXT("Rush"), TEXT("Plunge"), TEXT("JumpCut"), TEXT("Guard"), TEXT("Parry"),
            TEXT("DashCut"), TEXT("Sneakstrike"), TEXT("Flurry"), TEXT("DrawSword"), TEXT("SheatheSword"), TEXT("SwordParry"),
            TEXT("SwordGuard") });
    }
    inline bool IsAttack(FName N)
    {
        return Prefixed(N, { TEXT("Cut"), TEXT("Rush"), TEXT("Plunge"), TEXT("JumpCut"), TEXT("DashCut"), TEXT("Sneakstrike"), TEXT("Flurry") }) ||
            N == FName(TEXT("ChargeSpin"));
    }
    /** A record's {location, rotation (x, y, z, w), scale} into Out; Out is left alone when Key is absent. */
    inline void ReadTransform(const TSharedPtr<FJsonObject>& O, const TCHAR* Key, FTransform& Out)
    {
        const TSharedPtr<FJsonObject>* T = nullptr;
        if (!O->TryGetObjectField(Key, T)) return;
        const TArray<TSharedPtr<FJsonValue>>* L = nullptr; const TArray<TSharedPtr<FJsonValue>>* R = nullptr;
        if ((*T)->TryGetArrayField(TEXT("location"), L) && L->Num() == 3)
            Out.SetLocation(FVector((*L)[0]->AsNumber(), (*L)[1]->AsNumber(), (*L)[2]->AsNumber()));
        if ((*T)->TryGetArrayField(TEXT("rotation"), R) && R->Num() == 4)
            Out.SetRotation(FQuat((*R)[0]->AsNumber(), (*R)[1]->AsNumber(), (*R)[2]->AsNumber(), (*R)[3]->AsNumber()).GetNormalized());
        double Scale = 1.;
        if ((*T)->TryGetNumberField(TEXT("scale"), Scale)) Out.SetScale3D(FVector(Scale));
    }
    /** The rest of a blocked move, along the surface it hit (the movement component keeps its own slide protected). */
    inline void Slide(UCharacterMovementComponent* Movement, const FVector& Delta, const FQuat& Rotation, FHitResult& Hit)
    {
        const FVector Along = FVector::VectorPlaneProject(Delta * (1.f - Hit.Time), Hit.Normal);
        if (!Along.IsNearlyZero()) Movement->SafeMoveUpdatedComponent(Along, Rotation, true, Hit);
    }
    inline bool IsHop(FName N) { return In(N, { TEXT("HopL"), TEXT("HopR"), TEXT("BackFlip") }); }
    inline bool IsDoubleJump(FName N) { return In(N, { TEXT("DoubleJump"), TEXT("DoubleJumpTuck") }); }
    inline bool IsParry(FName N) { return In(N, { TEXT("Parry"), TEXT("SwordParry") }); }
    inline bool IsGuardHit(FName N) { return In(N, { TEXT("GuardHit"), TEXT("SwordGuardHit") }); }
    inline bool IsLockLoop(FName N) { return Prefixed(N, { TEXT("Lock") }); }
    inline bool IsClimbMove(FName N) { return In(N, { TEXT("ClimbU"), TEXT("ClimbD"), TEXT("ClimbL"), TEXT("ClimbR"), TEXT("ClimbUL"), TEXT("ClimbUR"), TEXT("ClimbDL"), TEXT("ClimbDR") }); }
    /** Actions the stick does not steer until their cancel point (or their idle point, or their end). */
    inline bool IsLocking(FName N)
    {
        return IsAttack(N) || IsHop(N) || Prefixed(N, { TEXT("HopLand"), TEXT("BackFlipLand"), TEXT("HardLand"), TEXT("Charge"), TEXT("Hit"),
            TEXT("Knock"), TEXT("Guard"), TEXT("Parry"), TEXT("SwordParry"), TEXT("SwordGuard"), TEXT("Swim"), TEXT("Climb"), TEXT("Glide") });
    }
    inline float Smooth(float U) { U = FMath::Clamp(U, 0.f, 1.f); return U * U * (3.f - 2.f * U); }
    inline const TCHAR* const CutNames[] = { TEXT("CutS1"), TEXT("CutS2"), TEXT("CutS3"), TEXT("CutSF") };
    inline const TCHAR* const RushNames[] = { TEXT("Flurry"), TEXT("Rush1"), TEXT("Rush2"), TEXT("Rush3"), TEXT("Rush4"), TEXT("Rush5"), TEXT("RushFinish") };
    inline constexpr int32 RushCount = UE_ARRAY_COUNT(RushNames);

    /** A looping clip's path continues cycle after cycle (SourceTime is unwrapped: it keeps growing while the clip loops). */
    inline FVector4f Travelled(const FBotwMove& M, float SourceTime)
    {
        if (!M.bLoop || M.Length <= 0.f) return M.PathAt(SourceTime);
        const float Cycles = FMath::FloorToFloat(SourceTime / M.Length);
        return M.PathAt(M.Length) * Cycles + M.PathAt(SourceTime - Cycles * M.Length);
    }
}
