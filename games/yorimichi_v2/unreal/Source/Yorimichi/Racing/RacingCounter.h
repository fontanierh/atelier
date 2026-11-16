#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "RacingResults.h"
#include "RacingCounter.generated.h"

class AActor;
class AController;
class AWandererCharacter;
struct FRacingNetRace;
namespace RacingTv { struct FSpot; }

/** One of the player's win bets (of today, or a won ticket of any day still to collect), as the player may see it. */
USTRUCT()
struct FRacingWalletTicket
{
    GENERATED_BODY()
    UPROPERTY() FString Race;
    UPROPERTY() FString Horse;
    UPROPERTY() int32 Stake = 0;
    /** The rules' status ("open", "won", "lost", "refunded"); "open" until the race's winner is home. */
    UPROPERTY() FString Status;
    /** Coins paid back (a win or a refund), 0 while open. */
    UPROPERTY() int32 Payout = 0;
    /** A win whose payout waits at the betting counter (FHRTicket::Unpaid); false while the ticket still shows open. */
    UPROPERTY() bool Unpaid = false;

    bool operator==(const FRacingWalletTicket& O) const
    {
        return Race == O.Race && Horse == O.Horse && Stake == O.Stake && Status == O.Status && Payout == O.Payout && Unpaid == O.Unpaid;
    }
};

/** A player's coins (FHRPlayer::Coins, less the credited payouts not yet seen), coins staked today, today's newest tickets
 *  and the newest winning tickets of any day whose winnings wait to be collected at the counter. */
USTRUCT()
struct FRacingWalletState
{
    GENERATED_BODY()
    /** Tickets the wallet carries at most: stakes have no count limit, the replicated wallet does. */
    static constexpr int32 MaxTickets = 20;
    UPROPERTY() int32 Coins = 0;
    UPROPERTY() int32 DayStaked = 0;
    /** Newest first: at most MaxTickets of today's tickets, and at most MaxTickets unpaid winning tickets of earlier days
     *  (the newest MaxTickets unpaid tickets of any day are carried). */
    UPROPERTY() TArray<FRacingWalletTicket> Tickets;
    /** Today's tickets older than those carried. */
    UPROPERTY() int32 EarlierTickets = 0;
    /** Unpaid winning tickets (shown as won) not carried in Tickets. */
    UPROPERTY() int32 UnpaidMore = 0;
    /** Coins every unpaid winning ticket shown as won waits to pay (summed in int64, held within int32). */
    UPROPERTY() int32 UnpaidCoins = 0;

    /** Unpaid winning tickets shown as won: those carried plus UnpaidMore. */
    int32 UnpaidTickets() const
    {
        int32 N = UnpaidMore;
        for (const FRacingWalletTicket& T : Tickets) N += T.Unpaid ? 1 : 0;
        return N;
    }
    bool operator==(const FRacingWalletState& O) const
    {
        return Coins == O.Coins && DayStaked == O.DayStaked && Tickets == O.Tickets && EarlierTickets == O.EarlierTickets &&
            UnpaidMore == O.UnpaidMore && UnpaidCoins == O.UnpaidCoins;
    }
};

/**
 * The Salon des Paris's betting counter in Belmonte. It stands at V1's central window (SALON_COUNTER, hall-local
 * (-1760, 300)), derived from the Salon's Paris screen spot ('tv_spots' salon_paris in Belmonte's runtime.json, itself
 * built from the SalonHall placement): no data of its own and no hardcoded fallback. Without the spots there is no counter.
 */
namespace RacingCounter
{
    struct FCounter
    {
        /** The player's spot at the window (Belmonte-local cm, on the floor), facing the counter along Yaw. */
        FVector Spot = FVector::ZeroVector;
        float Yaw = 0.f;
    };
    /** The windows span HalfLength either side of the spot; the player stands within Reach in front of it, Behind towards
     *  the counter, Below and Above it (cm). */
    inline constexpr double HalfLength = 380., Reach = 260., Behind = 150., Below = 80., Above = 260.;
    /** The counter from the TV spots: the Paris screen's watch point plus R(WatchYaw)·(-350, -1260, 0), facing
     *  WatchYaw - 90. False when the spots have no salon_paris. */
    YORIMICHI_API bool Parse(TConstArrayView<RacingTv::FSpot> Spots, FCounter& Out);
    /** Whether Location (world cm) stands at Counter in the region at OriginCm. */
    YORIMICHI_API bool InReach(const FVector& Location, const FVector& OriginCm, const FCounter& Counter);
    /** Whether an actor stands at the staged counter, on any machine (the host checks a guest's pawn with it). */
    YORIMICHI_API bool IsAt(const AActor* Actor);
    /** The local player may open the betting window here: on foot, free, with a wallet, at the counter. */
    YORIMICHI_API bool CanUse(const AWandererCharacter* Pawn);
    /** Interact at the counter: opens the betting window; false when the player cannot use it. */
    YORIMICHI_API bool TryOpen(AWandererCharacter* Pawn);
    /** The HUD's prompt at the counter ("Place a win bet", "Collect winnings" when some wait), empty elsewhere. */
    YORIMICHI_API FString Hint(const AWandererCharacter* Pawn);
    YORIMICHI_API bool IsOpen();
    YORIMICHI_API void Close();

    /** The window's stakes for a player with Coins: 1, 5, 10, 25, 50 and 100 below Coins, then All (Coins itself). Empty
     *  without coins. */
    YORIMICHI_API TArray<int32> StakeSteps(int32 Coins);
    /** The stake one step down (Direction < 0) or up from Stake among StakeSteps(Coins), held at the ends; a stake between
     *  steps (coins changed) moves to the next step that way. 0 without coins. */
    YORIMICHI_API int32 StepStake(int32 Stake, int32 Coins, int32 Direction);
    /** Why a press of the bet button cannot ask the host for a bet on runner Runner of Race (the race in focus, Key empty
     *  when none) at world second Now with Stake coins: no race open, betting closed, no coins or no such runner (English).
     *  Empty when the request can go to the host, which still decides. */
    YORIMICHI_API FString BetBlocker(const FRacingNetRace& Race, double Now, int32 Runner, int32 Stake);
}

/**
 * A player's wallet, on each player controller, and the result of the last race they bet on. The host (ARacingService)
 * fills both, replicated to their owner only. The owner
 * asks the host for a bet (ServerPlaceBet) or to collect its winnings (ServerCollect) and hears the answer (ClientBetReply);
 * offline and on the host the same call runs directly. Both requests share one rate limit.
 */
UCLASS(ClassGroup = Racing)
class YORIMICHI_API URacingWallet : public UActorComponent
{
    GENERATED_BODY()
public:
    URacingWallet();
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    static URacingWallet* Of(const AController* Controller);

    const FRacingWalletState& GetWallet() const { return Wallet; }
    /** The result of the last race this player bet on (RacingResults::Build), empty until its winner is home. */
    const FRacingResultState& GetResult() const { return Result; }
    /** The last answer: "Bet placed.", a refusal, or that a request is waiting. */
    const FString& GetReply() const { return Reply; }
    /** Owner: asks the host for a win bet on runner Runner (FRacingNetRace::Runners index) of the race RaceKey. */
    void RequestBet(const FString& RaceKey, int32 Runner, int32 Stake);
    /** Owner: asks the host to pay the winnings waiting on its tickets (it must stand at the counter). */
    void RequestCollect();
    /** Owner: a reply the window decides itself (why a press could not bet), or none: the window clears it when it opens
     *  and when the race in focus changes, so an old answer is never shown for a press that did not reach the host. */
    void SetLocalReply(const FString& Text) { Reply = Text; }
    void ClearReply() { Reply.Reset(); }

    // ------------------------------------------------------------------ host
    void HostSet(const FRacingWalletState& Next) { if (!(Next == Wallet)) Wallet = Next; }
    void HostSetResult(const FRacingResultState& Next) { if (!(Next == Result)) Result = Next; }
    /** At most this many requests a second are looked at, with race keys of at most MaxRaceKeyChars. */
    static constexpr int32 MaxRequestsPerSecond = 5, MaxRaceKeyChars = 32;

    UFUNCTION(Server, Reliable) void ServerPlaceBet(const FString& RaceKey, int32 Runner, int32 Stake);
    UFUNCTION(Server, Reliable) void ServerCollect();
    /** The host's answer to a bet (empty: taken) or a collection (its text). */
    UFUNCTION(Client, Reliable) void ClientBetReply(const FString& Error);

private:
    UPROPERTY(Replicated) FRacingWalletState Wallet;
    UPROPERTY(Replicated) FRacingResultState Result;
    FString Reply;
    double RequestWindow = -1.;
    int32 Requests = 0;
    /** Whether the host looks at one more request this second (MaxRequestsPerSecond, bets and collections together). */
    bool Admit();
    /** The host's handling of a request: rate, key length, then ARacingService::PlaceBet. Empty when taken. */
    FString HostHandle(const FString& RaceKey, int32 Runner, int32 Stake);
    /** The host's handling of a collection: rate, then ARacingService::CollectWinnings. The answer to show. */
    FString HostCollect();
    void ApplyReply(const FString& Error);
};
