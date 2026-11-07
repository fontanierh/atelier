#include "JapanHorseState.h"
// Named, not anonymous: a unity build would otherwise put these names in every later file's scope.
namespace JapanHorseWire
{
// EHorseRole's order (HorseComponent.cpp's HorseRide::Roles): the rider's clip names, a fixed wire vocabulary.
const FName RoleNames[] = { TEXT("HorseIdle"), TEXT("HorseIdleLook"), TEXT("HorseIdleGraze"), TEXT("HorseIdleShake"),
    TEXT("HorseIdleFlehmen"), TEXT("HorseIdleAffection"), TEXT("HorseWalk"), TEXT("HorseTrot"), TEXT("HorseCanter"),
    TEXT("HorseGallop"), TEXT("HorseSprint"), TEXT("HorseMount"), TEXT("HorseDismount") };
static_assert(UE_ARRAY_COUNT(RoleNames) == FJapanHorseState::RoleCount, "one name per EHorseRole");
bool HorseStateRange(float V, float Lo, float Hi) { return FMath::IsFinite(V) && V >= Lo && V <= Hi; }
}  // namespace JapanHorseWire
FName FJapanHorseState::RoleName(uint8 Index) { return Index < RoleCount ? JapanHorseWire::RoleNames[Index] : FName(); }
bool FJapanHorseState::IsValid() const
{
    using JapanHorseWire::HorseStateRange;
    // Mounting and dismounting play their own clip; riding plays an idle or a gait; stowed rests at Idle.
    const bool RoleFits = Phase == 0 ? Role == 0 : Phase == 1 ? Role == MountRole : Phase == 2 ? Role <= SprintRole : Role == DismountRole;
    return Phase <= 3 && Role < RoleCount && ForcedIdle < IdleRoles && RoleFits && (!Terminal || Phase == 3) &&
        HorseStateRange(Yaw, -180.f, 180.f) && HorseStateRange(Speed, 0.f, 1480.1f) && HorseStateRange(Steering, -1.01f, 1.01f) &&
        HorseStateRange(PhaseTime, 0.f, 10.f) && HorseStateRange(GaitPhase, 0.f, 1.f) && HorseStateRange(IdleTimer, 0.f, 60.f) &&
        HorseStateRange(IdleCooldown, 0.f, 12.1f);
}
bool FJapanHorseState::SerializeCheckpoint(FArchive& Ar)
{
    uint8 Flags = (Sprint ? 1 : 0) | (Terminal ? 2 : 0) | (ReinIn ? 4 : 0);
    if (Ar.IsSaving() && !IsValid()) { Ar.SetError(); return false; }
    Ar << Phase << Role << ForcedIdle << Flags << Serial << Yaw << Speed << Steering << PhaseTime << GaitPhase << IdleTimer << IdleCooldown;
    if (Ar.IsLoading())
    {
        if (Ar.IsError() || Phase > 3 || Role >= RoleCount || ForcedIdle >= IdleRoles || Flags > 7) { Ar.SetError(); return false; }
        Sprint = (Flags & 1) != 0; Terminal = (Flags & 2) != 0; ReinIn = (Flags & 4) != 0;
    }
    if (!IsValid()) Ar.SetError();
    return !Ar.IsError();
}
