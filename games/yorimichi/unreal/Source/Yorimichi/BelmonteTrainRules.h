#pragma once
#include "CoreMinimal.h"

/**
 * Pure Belmonte train passenger admission, intruder detection, and safe recovery rules.
 * Tested in BelmonteTrainServiceTests.cpp.
 */
namespace BelmonteTrainRules
{
/** The HUD line when a vehicle is refused on the train. */
inline const TCHAR* Refusal() { return TEXT("Not aboard the train"); }

/** Taking out the skateboard, the bike, the horse or the sailboat: never aboard, seated or while stepping through a
 *  door (bTrainAction). Putting one away is always allowed. */
inline bool MayTakeOutVehicle(bool bAboard, bool bTrainAction) { return !bAboard && !bTrainAction; }

/**
 * Admission: the ticket the boarding walk gives (Monter at a station door), the one way to be carried as a passenger.
 * Owned by the host (offline: the game); clients take it from the replicated passenger list.
 *
 * It holds through the door walk and the steps (bHeld), seated (bHeld), standing up again, crossing a gangway or a
 * vestibule outside the rooms (bOnTrain: still inside a room with the gangway margin, or standing on a vehicle of the
 * train), and the train's travel. It ends on the walk down (Revoke), a cancel (a teleport, a respawn, the map's
 * travel: Revoke), or once the rider has been off the train for Grace seconds (walked out of an open door). A pawn
 * replacement carries it to the new pawn (MoveRider); a disconnected player's ticket goes with them (DropVanished).
 */
struct FAdmission
{
    static constexpr float Grace = 1.5f;
    bool bAdmitted = false;
    /** Seconds off the train since the rider was last on it. */
    float Outside = 0.f;

    void Admit() { bAdmitted = true; Outside = 0.f; }
    void Revoke() { bAdmitted = false; Outside = 0.f; }
    /** Each frame. bMayRevoke: the host or offline (a client only follows the host). Returns true when the ticket lapsed
     *  this frame. */
    bool Update(bool bOnTrain, bool bHeld, float Dt, bool bMayRevoke)
    {
        if (!bAdmitted) return false;
        if (bOnTrain || bHeld) { Outside = 0.f; return false; }
        Outside += Dt;
        if (Outside < Grace || !bMayRevoke) return false;
        Revoke();
        return true;
    }
    /** Still carried by the coach it was last in: admitted, and on the train or within the grace. */
    bool Carries() const { return bAdmitted && Outside < Grace; }
};

/** Moving with the coach, from the rider's speed in the coach's frame (cm/s) and the coach's own speed (cm/s): a person
 *  inside a running coach keeps their own small speed in its frame, while a bystander the coach sweeps past (a platform,
 *  a clipped hillside) moves through its frame at the coach's speed. A standing coach tells nothing (false). */
inline bool MovesWithCoach(double RelativeSpeed, double CoachSpeed)
{
    return CoachSpeed > 100. && RelativeSpeed < .5 * CoachSpeed;
}

/**
 * A player inside a coach's interior rooms without the ticket (on a vehicle through an open door, a jump, the
 * paraglider, a dash) is put back outside once the coach runs or is about to leave (bMovingOrDeparting: doors locked).
 * Only someone actually riding it counts (bWithCoach: standing on its floor, or MovesWithCoach): a bystander the coach
 * merely sweeps through stays where they are. A passenger, a seated player or one stepping through a door never.
 */
inline bool MustEject(bool bInsideCoach, bool bAdmitted, bool bBoarding, bool bSeated, bool bWithCoach, bool bMovingOrDeparting)
{
    return bInsideCoach && !bAdmitted && !bBoarding && !bSeated && bWithCoach && bMovingOrDeparting;
}

/**
 * Where an ejected player is set down: candidates in this order, each accepted only after AcceptStand.
 * - Platform: the station platform beside the coach (the platform side, at the player, then the station's arrival
 *   point), when the coach stands within a platform.
 * - DoorSide: beside the coach at the player and at its doors, the nearer side first.
 * - LastSafe: where the player last stood on walkable ground off the train (often the platform they left).
 * - TrainLastSafe: a door-side point recorded earlier while the train ran in the open.
 * - NextStation: the station the train runs to, then the others.
 * In a tunnel or on a viaduct (bEnclosed) the points beside the coach are never used.
 */
enum class ERecovery : uint8 { Platform, DoorSide, LastSafe, TrainLastSafe, NextStation };

inline TArray<ERecovery, TInlineAllocator<5>> RecoveryOrder(bool bAtPlatform, bool bEnclosed)
{
    if (bEnclosed) return {ERecovery::LastSafe, ERecovery::TrainLastSafe, ERecovery::NextStation};
    if (bAtPlatform) return {ERecovery::Platform, ERecovery::DoorSide, ERecovery::LastSafe, ERecovery::TrainLastSafe, ERecovery::NextStation};
    return {ERecovery::DoorSide, ERecovery::LastSafe, ERecovery::TrainLastSafe, ERecovery::NextStation};
}

/** What the world says about one candidate (BelmonteTrainRecovery::Probe). */
struct FStandProbe
{
    /** The first surface met from above: found, part of the train, its normal's z, its height off the expected z (cm). */
    bool bGround = false, bGroundIsTrain = false;
    double GroundNormalZ = 0., GroundOff = 0.;
    /** The standing capsule (a step above that ground) overlaps nothing. */
    bool bClear = false;
    /** The capsule swept down from there lands on a floor: found, part of the train, its normal's z. */
    bool bFloor = false, bFloorIsTrain = false;
    double FloorNormalZ = 0.;
};

/** A destination is safe only on walkable ground that is not the train, near the height expected, with room to stand:
 *  a height trace alone is never enough (a viaduct's deck edge, a tunnel's bore, a wall beside the point). */
inline bool AcceptStand(const FStandProbe& P, double WalkableZ, double MaxOff)
{
    return P.bGround && !P.bGroundIsTrain && P.GroundNormalZ >= WalkableZ && FMath::Abs(P.GroundOff) <= MaxOff &&
        P.bClear && P.bFloor && !P.bFloorIsTrain && P.FloorNormalZ >= WalkableZ;
}

/** The station a train heading Speed (m/s, + up the chainage) at chainage At reaches next; standing, the nearest.
 *  Chainages in any order; INDEX_NONE when there is none. */
inline int32 NextStop(const TArray<double>& Stations, double At, double Speed)
{
    int32 Best = INDEX_NONE;
    for (int32 I = 0; I < Stations.Num(); ++I)
    {
        const double S = Stations[I];
        const bool bAhead = Speed > .1 ? S >= At : Speed < -.1 ? S <= At : true;
        if (!bAhead) continue;
        if (Best == INDEX_NONE || FMath::Abs(S - At) < FMath::Abs(Stations[Best] - At)) Best = I;
    }
    // Past the last stop in that direction (a terminus overrun): the nearest one.
    if (Best == INDEX_NONE && FMath::Abs(Speed) > .1) return NextStop(Stations, At, 0.);
    return Best;
}

/** Pawn replacement: the From rider's entry (ticket, seat, walk, last safe ground) moves to To. An entry To already had
 *  (made the frame it spawned) is released and dropped first, so no lookup finds a ticketless duplicate. Riders have a
 *  `Character` with Get(). Returns the moved entry's index, or INDEX_NONE when From has none. */
template<typename TRider, typename TPtr, typename FRelease>
int32 MoveRider(TArray<TRider>& Riders, TPtr From, TPtr To, FRelease&& Release)
{
    int32 FromIndex = Riders.IndexOfByPredicate([From](const TRider& R) { return R.Character.Get() == From; });
    if (FromIndex == INDEX_NONE || !To || From == To) return INDEX_NONE;
    for (int32 I = Riders.Num() - 1; I >= 0; --I)
        if (I != FromIndex && Riders[I].Character.Get() == To)
        {
            Release(Riders[I]);
            Riders.RemoveAt(I);
            if (I < FromIndex) --FromIndex;
        }
    Riders[FromIndex].Character = To;
    return FromIndex;
}

/** A disconnected (destroyed) player's entry: released (its seat, the door it held open) and dropped with its ticket.
 *  Returns how many were dropped. */
template<typename TRider, typename FRelease>
int32 DropVanished(TArray<TRider>& Riders, FRelease&& Release)
{
    int32 Dropped = 0;
    for (int32 I = Riders.Num() - 1; I >= 0; --I)
        if (!Riders[I].Character.Get()) { Release(Riders[I]); Riders.RemoveAt(I); ++Dropped; }
    return Dropped;
}
}
