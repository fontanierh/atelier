#pragma once
#include "CoreMinimal.h"
#include "IPixelStreaming2InputHandler.h"
class AWandererCharacter;
class IPixelStreaming2Streamer;

// Only created by -phonestreaming. Input is leased: a suspended/disconnected
// browser cannot leave movement or a jump held indefinitely.
class FJapanStreamingInput : public TSharedFromThis<FJapanStreamingInput>
{
public:
    explicit FJapanStreamingInput(AWandererCharacter* InRider) : Rider(InRider) {}
    ~FJapanStreamingInput();
    void Tick(float Dt);
private:
    void SendSettings(const FString& Source);
    void SendMap(const FString& Source);
    void Receive(const FString& Source, const FString& Descriptor);
    TWeakObjectPtr<AWandererCharacter> Rider;
    TWeakPtr<IPixelStreaming2InputHandler> Handler;
    TWeakPtr<IPixelStreaming2Streamer> Streamer;
    IPixelStreaming2InputHandler::MessageHandlerFn Previous;
    FString PlayerId;
    FVector2D Move=FVector2D::ZeroVector, Look=FVector2D::ZeroVector;
    double LastInput=-100., LastStatus=0.;
    uint32 Buttons=0, PendingPress=0;
    bool bHasInput=false, bJumpRelease=false;
};
