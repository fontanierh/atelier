#pragma once
#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "IPixelStreaming2InputHandler.h"
#include "AtelierStream.generated.h"

class FJsonObject;
class IPixelStreaming2Streamer;

/** Set in the game's DefaultGame.ini under [/Script/AtelierStream.AtelierStreamSettings]. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Atelier Stream"))
class ATELIERSTREAM_API UAtelierStreamSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    /** The key every message carries, {"<Protocol>": 1, ...}; the pages use the same name (game.toml [stream] protocol). */
    UPROPERTY(Config, EditAnywhere, Category = "Stream") FString Protocol = TEXT("atelier");
    /** Touch controls are let go when their messages stop for this long (a phone locked, a tab hidden, a lost link). */
    UPROPERTY(Config, EditAnywhere, Category = "Stream") float LeaseSeconds = .6f;
};

/** Controls a touch page sent: a stick, a camera drag and a mask of buttons whose bits the game defines. */
struct FAtelierTouchControls
{
    FVector2D Move = FVector2D::ZeroVector;   // -1..1 each, y forward
    FVector2D Look = FVector2D::ZeroVector;   // drag since the last read (the page's scaled pixels)
    uint32 Buttons = 0;                       // held now
    uint32 Pressed = 0;                       // went down since the last read
    uint32 Released = 0;                      // went up since the last read (every held one when the lease runs out)
    bool bPaused = false;                     // the page is not playing (a menu or a dialog is open)
    bool bActive = false;                     // messages are arriving: the touch page drives the game
    bool bLeaseExpired = false;               // they just stopped: everything was let go this frame
};

/**
 * The game's end of the stream's message channel (Pixel Streaming 2 UI-interaction messages, JSON). Exists when the game
 * runs with -AtelierStream (`atelier stream <game> start`). Messages with an "action" go to the handler the game
 * registered for that name; the others are touch controls {x, y, dx, dy, buttons, paused}, held under a lease so a phone
 * that goes quiet cannot leave a button pressed. A page that sends nothing (the plain player, whose keyboard, mouse or
 * controller reach the game as its own input) leaves the game's input alone.
 */
class ATELIERSTREAM_API FAtelierStream : public TSharedFromThis<FAtelierStream>
{
public:
    /** The game was started for streaming. */
    static bool IsRequested();
    ~FAtelierStream();

    using FAction = TFunction<void(const FString& Player, const FJsonObject& Message)>;
    void OnAction(const FString& Name, FAction Handler);
    /** Every frame: connects to the streamer once it exists, runs the lease, and returns the controls since the last call. */
    FAtelierTouchControls Tick();
    /** Forget the movement and held buttons without reporting them released (after a teleport); KeepButtons stay held. */
    void ResetControls(uint32 KeepButtons = 0);
    /** A message to one page: the protocol key, and Kind when given, are added. */
    bool Send(const FString& Player, const TSharedRef<FJsonObject>& Message, const FString& Kind = FString());
    /** The page whose touch controls arrived last. */
    const FString& GetPlayer() const { return PlayerId; }
    double SecondsSinceInput() const;
    /** Touch controls are arriving (within the lease). */
    bool IsTouchActive() const { return bHasInput; }

private:
    void Receive(const FString& Source, const FString& Descriptor);
    TMap<FString, FAction> Actions;
    TWeakPtr<IPixelStreaming2InputHandler> Handler;
    TWeakPtr<IPixelStreaming2Streamer> Streamer;
    IPixelStreaming2InputHandler::MessageHandlerFn Previous;
    FString PlayerId;
    FAtelierTouchControls State;
    double LastInput = -100.;
    bool bHasInput = false;
};
