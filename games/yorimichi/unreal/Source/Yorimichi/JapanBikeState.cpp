#include "JapanBikeState.h"
namespace
{
const FName Clips[] = { NAME_None, TEXT("BikeMount"), TEXT("BikeRide"), TEXT("BikeDismount"),
    TEXT("BikeKickstand"), TEXT("BikeCrash"), TEXT("BikeHop"), TEXT("BikeSkid"), TEXT("BikeFootDown"),
    TEXT("BikeBell"), TEXT("BikeWave") };
int32 ClipIndex(FName Name)
{
    for (int32 I = 0; I < UE_ARRAY_COUNT(Clips); ++I) if (Clips[I] == Name) return I;
    return INDEX_NONE;
}
bool BikeStateRange(float V, float Lo, float Hi) { return FMath::IsFinite(V) && V >= Lo && V <= Hi; }
}
bool FJapanBikeState::IsValid() const
{
    return State <= 5 && ClipIndex(Clip) != INDEX_NONE && ClipIndex(Resume) != INDEX_NONE &&
        (State == 0 ? Clip.IsNone() : !Clip.IsNone()) && (!Terminal || State == 4 || State == 5) &&
        BikeStateRange(Yaw, -180.f, 180.f) && BikeStateRange(ClipTime, 0.f, 60.f) && BikeStateRange(Speed, -1000.f, 2400.1f) && BikeStateRange(Steering, -1.01f, 1.01f) &&
        BikeStateRange(StillTime, 0.f, 10.f) && BikeStateRange(AppliedYaw, -720.f, 720.f) && BikeStateRange(Crank, -720.f, 720.f) &&
        BikeStateRange(Coast, 0.f, 10.f) && BikeStateRange(Recoil, 0.f, 185.f) &&
        BikeStateRange(Drift, -60.f, 60.f) && BikeStateRange(Wheelie, 0.f, 60.f) && BikeStateRange(WheelieRate, -2000.f, 2000.f) &&
        BikeStateRange(Rise, -2000.f, 2000.f) && BikeStateRange(Air, 0.f, 60.f) && BikeStateRange(AirFall, 0.f, 10000.f);
}
bool FJapanBikeState::SerializeCheckpoint(FArchive& Ar)
{
    uint8 ClipId = uint8(ClipIndex(Clip)), ResumeId = uint8(ClipIndex(Resume));
    uint8 Flags = (Sprint ? 1 : 0) | (Terminal ? 2 : 0) | (Pedalling ? 4 : 0);
    if (Ar.IsSaving() && !IsValid()) { Ar.SetError(); return false; }
    Ar << State << ClipId << ResumeId << Flags << Serial << Yaw << ClipTime << Speed << Steering << StillTime
        << AppliedYaw << Crank << Coast << Recoil << Drift << Wheelie << WheelieRate << Rise << Air << AirFall;
    if (Ar.IsLoading())
    {
        if (ClipId >= UE_ARRAY_COUNT(Clips) || ResumeId >= UE_ARRAY_COUNT(Clips) || Flags > 7)
        { Ar.SetError(); return false; }
        Clip = Clips[ClipId]; Resume = Clips[ResumeId]; Sprint = (Flags & 1) != 0; Terminal = (Flags & 2) != 0; Pedalling = (Flags & 4) != 0;
    }
    if (!IsValid()) Ar.SetError();
    return !Ar.IsError();
}
