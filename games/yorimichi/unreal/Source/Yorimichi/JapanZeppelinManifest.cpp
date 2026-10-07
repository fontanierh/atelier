#include "JapanZeppelinManifest.h"

namespace
{
void AdvanceZeppelinRevision(uint32& Revision) { if (++Revision == 0) ++Revision; }
bool ZeppelinPlayerValid(const FString& Player) { return !Player.IsEmpty() && Player.Len() <= 128; }
}

bool FJapanZeppelinManifest::Initialize(int32 Stations, int32 InitialDock, int32 Capacity)
{
    if (StationCount || Stations < 2 || Stations > 64 || InitialDock < 0 || InitialDock >= Stations ||
        Capacity < 1 || Capacity > MaximumPassengers) return false;
    StationCount = Stations; Dock = InitialDock; Destination = (Dock + 1) % Stations; PassengerCapacity = Capacity;
    return true;
}

bool FJapanZeppelinManifest::AdvanceTime(double Now)
{
    if (!StationCount || !FMath::IsFinite(Now) || Now < LastTime) return false;
    LastTime = Now; return true;
}

const FJapanZeppelinPassenger* FJapanZeppelinManifest::Find(const FString& Player) const
{
    return Passengers.FindByPredicate([&](const FJapanZeppelinPassenger& P) { return P.Player == Player; });
}
FJapanZeppelinPassenger* FJapanZeppelinManifest::FindMutable(const FString& Player)
{
    return Passengers.FindByPredicate([&](const FJapanZeppelinPassenger& P) { return P.Player == Player; });
}

EJapanZeppelinReply FJapanZeppelinManifest::Eligible(uint32 Epoch, const FJapanZeppelinAdmission& Host)
{
    if (!Epoch || Epoch != Host.Epoch) return EJapanZeppelinReply::Stale;
    if (Host.bPendingContact) return EJapanZeppelinReply::PendingContact;
    if (Host.bEncounterHeld) return EJapanZeppelinReply::Encounter;
    if (!Host.bReady || !Host.bOnFoot || !Host.bGrounded || !Host.bNearStation ||
        Host.bMenuOpen || Host.bMovementLocked) return EJapanZeppelinReply::Unavailable;
    return EJapanZeppelinReply::Accepted;
}

EJapanZeppelinReply FJapanZeppelinManifest::Board(const FString& Player, uint32 Epoch, uint32 Trip,
    double Now, const FJapanZeppelinAdmission& Host, TFunctionRef<uint32(int32 Slot)> EnterProtected)
{
    if (!AdvanceTime(Now) || !ZeppelinPlayerValid(Player)) return EJapanZeppelinReply::Invalid;
    if (const auto* Existing = Find(Player))
        return Epoch == Existing->RequestEpoch && Host.Epoch == Existing->Epoch ?
            EJapanZeppelinReply::Duplicate : EJapanZeppelinReply::Stale;
    if (Trip != TripRevision) return EJapanZeppelinReply::Stale;
    const auto Eligibility = Eligible(Epoch, Host);
    if (Eligibility != EJapanZeppelinReply::Accepted) return Eligibility;
    if (Host.Station != Dock) return EJapanZeppelinReply::Unavailable;
    if (Phase != EJapanZeppelinPhase::Docked && Phase != EJapanZeppelinPhase::Boarding)
        return EJapanZeppelinReply::BoardingClosed;
    if (Phase == EJapanZeppelinPhase::Boarding && Now >= BoardingDeadline) return EJapanZeppelinReply::BoardingClosed;
    if (Passengers.Num() >= PassengerCapacity) return EJapanZeppelinReply::Full;
    int32 Slot = 0;
    while (Passengers.ContainsByPredicate([&](const FJapanZeppelinPassenger& P) { return P.Slot == Slot; })) ++Slot;
    // The adapter rechecks live pending contacts and encounter ownership here.
    // A failed handoff must leave both the pawn and manifest unchanged.
    const uint32 ProtectedEpoch = EnterProtected(Slot);
    if (!ProtectedEpoch || ProtectedEpoch == Epoch) return EJapanZeppelinReply::Unsafe;
    FJapanZeppelinPassenger P; P.Player = Player; P.RequestEpoch = Epoch; P.Epoch = ProtectedEpoch; P.Slot = Slot;
    Passengers.Add(MoveTemp(P));
    Calls.RemoveAll([&](const FJapanZeppelinCall& C) { return C.Player == Player; });
    if (Phase == EJapanZeppelinPhase::Docked)
    { Phase = EJapanZeppelinPhase::Boarding; BoardingDeadline = Now + BoardingSeconds; }
    RosterChanged(Now);
    return EJapanZeppelinReply::Accepted;
}

bool FJapanZeppelinManifest::ReachedSlot(const FString& Player, uint32 Epoch, double Now)
{
    if (!AdvanceTime(Now) || Phase != EJapanZeppelinPhase::Boarding || Now >= BoardingDeadline) return false;
    auto* P = FindMutable(Player); if (!P || P->Epoch != Epoch) return false;
    P->bAtSlot = true;
    if (Controller.IsEmpty()) ElectController(Now);
    return true;
}

int32 FJapanZeppelinManifest::ExpireBoarding(double Now,
    TFunctionRef<bool(const FJapanZeppelinPassenger&)> SafeRelease)
{
    if (!AdvanceTime(Now) || Phase != EJapanZeppelinPhase::Boarding || Now < BoardingDeadline) return 0;
    int32 Released = 0;
    for (int32 I = 0; I < Passengers.Num();)
    {
        if (!Passengers[I].bAtSlot && SafeRelease(Passengers[I]))
        { Passengers.RemoveAt(I); ++Released; }
        else ++I;
    }
    if (Released) RosterChanged(Now);
    if (Passengers.IsEmpty()) { Phase = EJapanZeppelinPhase::Docked; BoardingDeadline = 0.; }
    return Released;
}

bool FJapanZeppelinManifest::Depart(double Now, bool bGangwayClear)
{
    if (!AdvanceTime(Now) || Phase != EJapanZeppelinPhase::Boarding || Now < BoardingDeadline ||
        !bGangwayClear || Passengers.IsEmpty()) return false;
    for (const auto& P : Passengers) if (!P.bAtSlot) return false;
    Phase = EJapanZeppelinPhase::Flying; BoardingDeadline = 0.; NewTrip(); return true;
}

bool FJapanZeppelinManifest::Arrive(double Now)
{
    if (!AdvanceTime(Now) || Phase != EJapanZeppelinPhase::Flying) return false;
    Dock = Destination; ActiveCall = FJapanZeppelinCall();
    Phase = EJapanZeppelinPhase::Disembarking; NewTrip(); return true;
}

bool FJapanZeppelinManifest::FinishDisembarking(double Now, int32 NextDestination)
{
    if (!AdvanceTime(Now) || Phase != EJapanZeppelinPhase::Disembarking || !Passengers.IsEmpty() ||
        !StationValid(NextDestination) || NextDestination == Dock) return false;
    Destination = NextDestination; Phase = EJapanZeppelinPhase::Docked; NewTrip(); return true;
}

bool FJapanZeppelinManifest::Remove(const FString& Player, uint32 Epoch, double Now)
{
    if (!AdvanceTime(Now)) return false;
    const int32 I = Passengers.IndexOfByPredicate([&](const FJapanZeppelinPassenger& P)
        { return P.Player == Player && P.Epoch == Epoch; });
    if (I == INDEX_NONE) return false;
    Passengers.RemoveAt(I); RosterChanged(Now);
    if (Passengers.IsEmpty() && Phase == EJapanZeppelinPhase::Boarding)
    { Phase = EJapanZeppelinPhase::Docked; BoardingDeadline = 0.; }
    return true;
}

bool FJapanZeppelinManifest::Release(const FString& Player, uint32 Epoch, double Now,
    TFunctionRef<bool(const FJapanZeppelinPassenger&)> SafeRelease)
{
    if (!AdvanceTime(Now)) return false;
    const auto* P = Find(Player);
    if (!P || P->Epoch != Epoch || !SafeRelease(*P)) return false;
    return Remove(Player, Epoch, Now);
}

void FJapanZeppelinManifest::Disconnect(const FString& Player, double Now)
{
    if (!AdvanceTime(Now)) return;
    if (const auto* P = Find(Player)) Remove(Player, P->Epoch, Now);
    Calls.RemoveAll([&](const FJapanZeppelinCall& C) { return C.Player == Player; });
    if (ActiveCall.Player == Player) ActiveCall = FJapanZeppelinCall();
}

void FJapanZeppelinManifest::ClearVotes() { for (auto& P : Passengers) P.SkipUntil = 0.; }
void FJapanZeppelinManifest::NewTrip() { AdvanceZeppelinRevision(TripRevision); ClearVotes(); }
void FJapanZeppelinManifest::SetController(const FString& Player, double Now)
{
    Controller = Player; LastControl = Now; AdvanceZeppelinRevision(LeaseRevision);
}
void FJapanZeppelinManifest::ElectController(double Now)
{
    for (const auto& P : Passengers)
        if (P.bAtSlot) { SetController(P.Player, Now); return; }
    if (!Passengers.IsEmpty()) { SetController(Passengers[0].Player, Now); return; }
    SetController(FString(), Now);
}
void FJapanZeppelinManifest::RosterChanged(double Now)
{
    AdvanceZeppelinRevision(RosterRevision); ClearVotes();
    if (!Find(Controller)) ElectController(Now);
}

EJapanZeppelinReply FJapanZeppelinManifest::RequestControl(const FString& Player, uint32 Epoch,
    uint32 Trip, double Now)
{
    if (!AdvanceTime(Now)) return EJapanZeppelinReply::Invalid;
    if (Trip != TripRevision) return EJapanZeppelinReply::Stale;
    const auto* P = Find(Player);
    if (!P || P->Epoch != Epoch || !P->bAtSlot) return EJapanZeppelinReply::NotPassenger;
    if (Controller == Player) return EJapanZeppelinReply::Duplicate;
    if (!Controller.IsEmpty() && Now - LastControl < LeaseSeconds) return EJapanZeppelinReply::NotController;
    SetController(Player, Now); return EJapanZeppelinReply::Accepted;
}

EJapanZeppelinReply FJapanZeppelinManifest::Control(const FString& Player, uint32 Epoch,
    uint32 Trip, uint32 Lease) const
{
    if (Trip != TripRevision || Lease != LeaseRevision) return EJapanZeppelinReply::Stale;
    const auto* P = Find(Player);
    if (!P || P->Epoch != Epoch || !P->bAtSlot) return EJapanZeppelinReply::NotPassenger;
    return Controller == Player ? EJapanZeppelinReply::Accepted : EJapanZeppelinReply::NotController;
}

EJapanZeppelinReply FJapanZeppelinManifest::SelectDestination(const FString& Player, uint32 Epoch,
    uint32 Trip, uint32 Lease, int32 Station, double Now)
{
    if (!AdvanceTime(Now) || !StationValid(Station) || Station == Dock) return EJapanZeppelinReply::Invalid;
    const auto Allowed = Control(Player, Epoch, Trip, Lease);
    if (Allowed != EJapanZeppelinReply::Accepted) return Allowed;
    if (Phase != EJapanZeppelinPhase::Boarding) return EJapanZeppelinReply::Unavailable;
    if (Station == Destination) return EJapanZeppelinReply::Duplicate;
    Destination = Station; LastControl = Now; NewTrip(); return EJapanZeppelinReply::Accepted;
}

EJapanZeppelinReply FJapanZeppelinManifest::SelectSpeed(const FString& Player, uint32 Epoch,
    uint32 Trip, uint32 Lease, int32 SpeedIndex, double Now)
{
    if (!AdvanceTime(Now) || SpeedIndex < 0 || SpeedIndex >= 6) return EJapanZeppelinReply::Invalid;
    const auto Allowed = Control(Player, Epoch, Trip, Lease);
    if (Allowed != EJapanZeppelinReply::Accepted) return Allowed;
    if (Phase != EJapanZeppelinPhase::Flying) return EJapanZeppelinReply::Unavailable;
    if (Speed == SpeedIndex) return EJapanZeppelinReply::Duplicate;
    Speed = SpeedIndex; LastControl = Now; return EJapanZeppelinReply::Accepted;
}

EJapanZeppelinReply FJapanZeppelinManifest::VoteSkip(const FString& Player, uint32 Epoch,
    uint32 Trip, uint32 Roster, bool bVote, double Now)
{
    if (!AdvanceTime(Now)) return EJapanZeppelinReply::Invalid;
    if (Trip != TripRevision || Roster != RosterRevision) return EJapanZeppelinReply::Stale;
    auto* P = FindMutable(Player);
    if (!P || P->Epoch != Epoch) return EJapanZeppelinReply::NotPassenger;
    if (Phase != EJapanZeppelinPhase::Flying) return EJapanZeppelinReply::Unavailable;
    P->SkipUntil = bVote ? Now + VoteSeconds : 0.; return EJapanZeppelinReply::Accepted;
}

bool FJapanZeppelinManifest::WantsSkip(double Now) const
{
    if (!FMath::IsFinite(Now) || Now < LastTime || Phase != EJapanZeppelinPhase::Flying || Passengers.IsEmpty()) return false;
    for (const auto& P : Passengers) if (P.SkipUntil <= Now) return false;
    return true;
}

EJapanZeppelinReply FJapanZeppelinManifest::Call(const FString& Player, uint32 Epoch, uint32 Trip,
    int32 Station, double Now, const FJapanZeppelinAdmission& Host)
{
    if (!AdvanceTime(Now) || !ZeppelinPlayerValid(Player) || !StationValid(Station)) return EJapanZeppelinReply::Invalid;
    const auto Eligibility = Eligible(Epoch, Host);
    if (Eligibility != EJapanZeppelinReply::Accepted) return Eligibility;
    if (Host.Station != Station) return EJapanZeppelinReply::Unavailable;
    if (Find(Player)) return EJapanZeppelinReply::Unavailable;
    if (ActiveCall.Player == Player)
        return ActiveCall.Epoch == Epoch && ActiveCall.Station == Station ?
            EJapanZeppelinReply::Duplicate : EJapanZeppelinReply::Stale;
    if (const auto* Old = Calls.FindByPredicate([&](const FJapanZeppelinCall& C) { return C.Player == Player; }))
        return Old->Epoch == Epoch && Old->Station == Station ? EJapanZeppelinReply::Duplicate : EJapanZeppelinReply::Stale;
    if (Trip != TripRevision) return EJapanZeppelinReply::Stale;
    if (Calls.Num() + (ActiveCall.Player.IsEmpty() ? 0 : 1) >= MaximumCalls) return EJapanZeppelinReply::Full;
    FJapanZeppelinCall C; C.Player = Player; C.Epoch = Epoch; C.Station = Station; Calls.Add(MoveTemp(C));
    return EJapanZeppelinReply::Accepted;
}

bool FJapanZeppelinManifest::CancelCall(const FString& Player, uint32 Epoch, double Now)
{
    if (!AdvanceTime(Now)) return false;
    bool Removed = Calls.RemoveAll([&](const FJapanZeppelinCall& C)
        { return C.Player == Player && C.Epoch == Epoch; }) > 0;
    if (ActiveCall.Player == Player && ActiveCall.Epoch == Epoch)
    { ActiveCall = FJapanZeppelinCall(); Removed = true; }
    return Removed;
}

bool FJapanZeppelinManifest::DispatchCall(double Now, bool bGangwayClear)
{
    if (!AdvanceTime(Now) || Phase != EJapanZeppelinPhase::Docked || !Passengers.IsEmpty() || !bGangwayClear) return false;
    while (!Calls.IsEmpty())
    {
        ActiveCall = MoveTemp(Calls[0]); Calls.RemoveAt(0);
        const int32 Station = ActiveCall.Station;
        if (Station == Dock) { ActiveCall = FJapanZeppelinCall(); continue; }
        Destination = Station; Phase = EJapanZeppelinPhase::Flying; NewTrip(); return true;
    }
    return false;
}
