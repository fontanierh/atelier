#pragma once
#include "CoreMinimal.h"

enum class EJapanZeppelinPhase : uint8 { Docked, Boarding, Flying, Disembarking };
enum class EJapanZeppelinReply : uint8
{
    Accepted, Duplicate, Invalid, Stale, Unavailable, PendingContact, Encounter,
    Full, BoardingClosed, NotPassenger, NotController, Unsafe
};

/** Host observations, never deserialized from a request. Geometry and combat stay in the actor adapter. */
struct FJapanZeppelinAdmission
{
    uint32 Epoch = 0;
    int32 Station = INDEX_NONE;
    bool bReady = false, bOnFoot = false, bGrounded = false, bNearStation = false;
    bool bMenuOpen = false, bMovementLocked = false, bPendingContact = false, bEncounterHeld = false;
};

struct FJapanZeppelinPassenger
{
    FString Player;
    uint32 RequestEpoch = 0, Epoch = 0;
    int32 Slot = INDEX_NONE;
    bool bAtSlot = false;
    double SkipUntil = 0.;
};

struct FJapanZeppelinCall
{
    FString Player;
    uint32 Epoch = 0;
    int32 Station = INDEX_NONE;
};

/** Bounded server state. No world, network, camera or movement side effects.
 * The game-thread adapter must recheck combat and enter the protected activity
 * atomically in EnterProtected; it returns the new epoch, or zero without changing
 * the pawn. SafeRelease changes the pawn to foot only after validating its exit.
 * Neither callback may yield or re-enter this manifest. Removing one passenger
 * never changes a flying ship's route. Client replicas must not run this class.
 */
class FJapanZeppelinManifest
{
public:
    static constexpr int32 MaximumPassengers = 8, MaximumCalls = 8;
    static constexpr double BoardingSeconds = 8., VoteSeconds = 10., LeaseSeconds = 30.;
    bool Initialize(int32 Stations, int32 InitialDock, int32 Capacity = MaximumPassengers);
    EJapanZeppelinReply Board(const FString& Player, uint32 Epoch, uint32 Trip, double Now,
        const FJapanZeppelinAdmission& Host, TFunctionRef<uint32(int32 Slot)> EnterProtected);
    bool ReachedSlot(const FString& Player, uint32 Epoch, double Now);
    /** An unsafe expiry stays protected at the dock; departure remains blocked. */
    int32 ExpireBoarding(double Now, TFunctionRef<bool(const FJapanZeppelinPassenger&)> SafeRelease);
    bool Depart(double Now, bool bGangwayClear);
    bool Arrive(double Now);
    bool FinishDisembarking(double Now, int32 NextDestination);
    bool Release(const FString& Player, uint32 Epoch, double Now,
        TFunctionRef<bool(const FJapanZeppelinPassenger&)> SafeRelease);
    void Disconnect(const FString& Player, double Now);
    EJapanZeppelinReply RequestControl(const FString& Player, uint32 Epoch, uint32 Trip, double Now);
    EJapanZeppelinReply SelectDestination(const FString& Player, uint32 Epoch, uint32 Trip,
        uint32 Lease, int32 Station, double Now);
    EJapanZeppelinReply SelectSpeed(const FString& Player, uint32 Epoch, uint32 Trip,
        uint32 Lease, int32 SpeedIndex, double Now);
    EJapanZeppelinReply VoteSkip(const FString& Player, uint32 Epoch, uint32 Trip, uint32 Roster, bool bVote, double Now);
    bool WantsSkip(double Now) const;
    EJapanZeppelinReply Call(const FString& Player, uint32 Epoch, uint32 Trip, int32 Station,
        double Now, const FJapanZeppelinAdmission& Host);
    bool CancelCall(const FString& Player, uint32 Epoch, double Now);
    /** Only an empty, clear dock may dispatch a call. Already-at-dock calls are consumed too. */
    bool DispatchCall(double Now, bool bGangwayClear);

    const TArray<FJapanZeppelinPassenger>& GetPassengers() const { return Passengers; }
    const TArray<FJapanZeppelinCall>& GetCalls() const { return Calls; }
    const FJapanZeppelinCall& GetActiveCall() const { return ActiveCall; }
    const FJapanZeppelinPassenger* Find(const FString& Player) const;
    EJapanZeppelinPhase GetPhase() const { return Phase; }
    uint32 GetTrip() const { return TripRevision; }
    uint32 GetRoster() const { return RosterRevision; }
    uint32 GetLease() const { return LeaseRevision; }
    const FString& GetController() const { return Controller; }
    int32 GetDock() const { return Dock; }
    int32 GetDestination() const { return Destination; }
    int32 GetSpeedIndex() const { return Speed; }
    double GetBoardingDeadline() const { return BoardingDeadline; }
private:
    TArray<FJapanZeppelinPassenger> Passengers;
    TArray<FJapanZeppelinCall> Calls;
    FJapanZeppelinCall ActiveCall;
    FString Controller;
    EJapanZeppelinPhase Phase = EJapanZeppelinPhase::Docked;
    int32 StationCount = 0, PassengerCapacity = 0, Dock = 0, Destination = 1, Speed = 2;
    uint32 TripRevision = 1, RosterRevision = 1, LeaseRevision = 1;
    double LastTime = 0., BoardingDeadline = 0., LastControl = 0.;
    bool AdvanceTime(double Now);
    bool Remove(const FString& Player, uint32 Epoch, double Now);
    bool StationValid(int32 Station) const { return Station >= 0 && Station < StationCount; }
    static EJapanZeppelinReply Eligible(uint32 Epoch, const FJapanZeppelinAdmission& Host);
    EJapanZeppelinReply Control(const FString& Player, uint32 Epoch, uint32 Trip, uint32 Lease) const;
    FJapanZeppelinPassenger* FindMutable(const FString& Player);
    void RosterChanged(double Now);
    void NewTrip();
    void ClearVotes();
    void ElectController(double Now);
    void SetController(const FString& Player, double Now);
};
