#pragma once
#include "CoreMinimal.h"
#include "HRTypes.h"
#include "RacingResults.generated.h"

class ARacingService;
class AWandererCharacter;

/** One ticket on the race just run, as the results panel shows it: never a player id. */
USTRUCT()
struct FRacingResultTicket
{
    GENERATED_BODY()
    /** The ticket is the viewer's own. */
    UPROPERTY() bool bMine = false;
    /** Another player's display name (from their PlayerState), empty on the viewer's own tickets. */
    UPROPERTY() FString Player;
    UPROPERTY() FString Horse;
    UPROPERTY() int32 Stake = 0;
    /** The rules' settled status: "won", "lost" or "refunded". */
    UPROPERTY() FString Status;
    UPROPERTY() int32 Payout = 0;

    bool operator==(const FRacingResultTicket& O) const
    {
        return bMine == O.bMine && Player == O.Player && Horse == O.Horse && Stake == O.Stake && Status == O.Status && Payout == O.Payout;
    }
};

/**
 * The result of the last race a player bet on, for the results panel: built on the host only once the race's winner is
 * home, and only while it is recent (Window), else empty. Its own tickets come first, then the other players' grouped by
 * player; it carries at most MaxTickets of them and counts the rest.
 */
USTRUCT()
struct FRacingResultState
{
    GENERATED_BODY()
    /** Tickets the result carries at most (the viewer's own first). */
    static constexpr int32 MaxTickets = 32;
    /** World seconds after the winner is home that the result is offered; later, it is dropped (races are ~17 min apart). */
    static constexpr double Window = 300.;
    /** Display names are cut to this many characters. */
    static constexpr int32 MaxNameChars = 24;

    /** The rules' race key, empty when there is no result to show. */
    UPROPERTY() FString Key;
    UPROPERTY() int32 Day = 0;
    /** The race's number in the day's card (1 the first), its English name and distance. */
    UPROPERTY() int32 Number = 0;
    UPROPERTY() FString Race;
    UPROPERTY() int32 Distance = 0;
    /** World second the winner was home. */
    UPROPERTY() double Home = 0.;
    /** The winner: its number on the card (FRacingNetRace::Runners order, 1 the first), name, stable and odds in tenths. */
    UPROPERTY() int32 WinnerNumber = 0;
    UPROPERTY() FString Winner;
    UPROPERTY() FString WinnerStable;
    UPROPERTY() int32 WinnerOddsTenths = 0;
    UPROPERTY() TArray<FRacingResultTicket> Tickets;
    /** Tickets on the race beyond those carried. */
    UPROPERTY() int32 MoreTickets = 0;
    /** How many other players bet on the race. */
    UPROPERTY() int32 OtherPlayers = 0;

    bool IsEmpty() const { return Key.IsEmpty(); }
    bool operator==(const FRacingResultState& O) const
    {
        return Key == O.Key && Day == O.Day && Number == O.Number && Race == O.Race && Distance == O.Distance && Home == O.Home &&
            WinnerNumber == O.WinnerNumber && Winner == O.Winner && WinnerStable == O.WinnerStable && WinnerOddsTenths == O.WinnerOddsTenths &&
            Tickets == O.Tickets && MoreTickets == O.MoreTickets && OtherPlayers == O.OtherPlayers;
    }
};

/**
 * The results panel: when the winner of a race is home, every player who holds a ticket on it gets the race's result, their
 * tickets' outcomes and, on request, everyone else's tickets by display name. The host builds each player's FRacingResultState
 * (Build) and replicates it to that player only, on their URacingWallet; each machine shows its local player's once.
 */
namespace RacingResults
{
    /** PlayerId's result at world second Now: the latest race of today it bet on whose winner has been home for less than
     *  FRacingResultState::Window. Empty before the winner is home, so nothing about the race's tickets leaves the host
     *  early. Names maps player ids to display names; a player without one is "Another player", never their id. */
    YORIMICHI_API FRacingResultState Build(const FHRWorldState& S, const FString& PlayerId, double Now, const TMap<FString, FString>& Names);

    /** Whether a result is still worth showing at world second Now: not empty and its winner home less than Window ago. */
    YORIMICHI_API bool IsFresh(const FRacingResultState& Result, double Now);
    /** Whether the player is free for the panel: on foot, on the ground (not jumping, falling or swimming) and out of any menu, vehicle, seat, train, travel or cutscene. */
    YORIMICHI_API bool IsFree(const AWandererCharacter* Pawn);

    /** Each frame on every machine: shows the local player's new result once they are free, or drops it once stale. */
    YORIMICHI_API void Tick(const ARacingService* Service);
    YORIMICHI_API bool IsOpen();
    YORIMICHI_API void Close();
    /** Closes the panel and forgets which results this machine has shown: a new world in the same run starts afresh. */
    YORIMICHI_API void Reset();
}
