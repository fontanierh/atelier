#include "AtelierStream.h"
#include "IPixelStreaming2Module.h"
#include "IPixelStreaming2Streamer.h"
#include "Async/Async.h"
#include "Dom/JsonObject.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/MemoryReader.h"

bool FAtelierStream::IsRequested() { return FParse::Param(FCommandLine::Get(), TEXT("AtelierStream")); }

FAtelierStream::~FAtelierStream()
{
    if (auto H = Handler.Pin()) if (Previous) H->RegisterMessageHandler(TEXT("UIInteraction"), Previous);
}

void FAtelierStream::OnAction(const FString& Name, FAction Fn) { Actions.Add(Name, MoveTemp(Fn)); }

double FAtelierStream::SecondsSinceInput() const { return FPlatformTime::Seconds() - LastInput; }

void FAtelierStream::ResetControls(uint32 KeepButtons)
{
    State.Buttons &= KeepButtons; State.Pressed = State.Released = 0;
    State.Move = State.Look = FVector2D::ZeroVector;
}

bool FAtelierStream::Send(const FString& Player, const TSharedRef<FJsonObject>& Message, const FString& Kind)
{
    auto S = Streamer.Pin();
    if (!S || Player.IsEmpty()) return false;
    Message->SetNumberField(GetDefault<UAtelierStreamSettings>()->Protocol, 1);
    if (!Kind.IsEmpty()) Message->SetStringField(TEXT("kind"), Kind);
    FString Text; FJsonSerializer::Serialize(Message, TJsonWriterFactory<>::Create(&Text));
    // One page, not a broadcast: UE 5.8's broadcast holds the participants lock during a synchronous RTC send and
    // deadlocks against incoming data; the unicast snapshots the track and releases that lock first.
    S->SendPlayerMessage(Player, TEXT("Response"), Text);
    return true;
}

void FAtelierStream::Receive(const FString& Source, const FString& Descriptor)
{
    TSharedPtr<FJsonObject> J;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Descriptor), J) || !J.IsValid()) return;
    double Protocol = 0;
    if (!J->TryGetNumberField(GetDefault<UAtelierStreamSettings>()->Protocol, Protocol) || Protocol != 1) return;
    FString Action;
    if (J->TryGetStringField(TEXT("action"), Action))
    {
        if (const FAction* Fn = Actions.Find(Action)) (*Fn)(Source, *J);
        return;
    }
    double X = 0, Y = 0, DX = 0, DY = 0, Mask = 0;
    if (!J->TryGetNumberField(TEXT("x"), X) || !J->TryGetNumberField(TEXT("y"), Y) || !J->TryGetNumberField(TEXT("dx"), DX) ||
        !J->TryGetNumberField(TEXT("dy"), DY) || !J->TryGetNumberField(TEXT("buttons"), Mask)) return;
    if (!FMath::IsFinite(X) || !FMath::IsFinite(Y) || !FMath::IsFinite(DX) || !FMath::IsFinite(DY) || !FMath::IsFinite(Mask) ||
        Mask < 0 || Mask > 65535 || Mask != FMath::FloorToDouble(Mask)) return;
    bool bPaused = false; J->TryGetBoolField(TEXT("paused"), bPaused);
    if (bPaused) X = Y = DX = DY = Mask = 0;
    State.bPaused = bPaused;
    State.Move = FVector2D(FMath::Clamp(X, -1., 1.), FMath::Clamp(Y, -1., 1.)).GetClampedToMaxSize(1.);
    State.Look += FVector2D(FMath::Clamp(DX, -30., 30.), FMath::Clamp(DY, -30., 30.));
    const uint32 Next = uint32(Mask);
    State.Pressed |= Next & ~State.Buttons;
    State.Released |= State.Buttons & ~Next;
    State.Buttons = Next;
    LastInput = FPlatformTime::Seconds(); bHasInput = true; PlayerId = Source;
}

FAtelierTouchControls FAtelierStream::Tick()
{
    if (!Handler.IsValid() && IPixelStreaming2Module::IsAvailable())
    {
        auto& Module = IPixelStreaming2Module::Get();
        auto S = Module.FindStreamer(Module.GetDefaultStreamerID());
        auto H = S.IsValid() ? S->GetInputHandler().Pin() : nullptr;
        if (H)
        {
            Handler = H; Streamer = S; Previous = H->FindMessageHandler(TEXT("UIInteraction"));
            TWeakPtr<FAtelierStream> Weak = AsShared();
            H->RegisterMessageHandler(TEXT("UIInteraction"), [Weak](FString Source, FMemoryReader Ar)
            {
                if (Ar.TotalSize() - Ar.Tell() < 2) return;
                uint16 Length = 0; Ar << Length;
                if (Length > 2048 || Ar.TotalSize() - Ar.Tell() < int64(Length) * sizeof(TCHAR)) return;
                FString Descriptor; Descriptor.GetCharArray().SetNumUninitialized(Length + 1);
                Ar.Serialize(Descriptor.GetCharArray().GetData(), Length * sizeof(TCHAR)); Descriptor.GetCharArray()[Length] = 0;
                AsyncTask(ENamedThreads::GameThread, [Weak, Source, Descriptor]() { if (auto Self = Weak.Pin()) Self->Receive(Source, Descriptor); });
            });
            UE_LOG(LogTemp, Display, TEXT("ATELIER STREAM input ready (protocol %s)"), *GetDefault<UAtelierStreamSettings>()->Protocol);
        }
    }
    FAtelierTouchControls Out = State;
    Out.bActive = bHasInput;
    if (bHasInput && SecondsSinceInput() > GetDefault<UAtelierStreamSettings>()->LeaseSeconds)
    {
        Out.Released |= State.Buttons; Out.Buttons = Out.Pressed = 0; Out.Move = Out.Look = FVector2D::ZeroVector;
        Out.bActive = false; Out.bLeaseExpired = true;
        State = FAtelierTouchControls();
        bHasInput = false;
        UE_LOG(LogTemp, Display, TEXT("ATELIER STREAM input timeout: released controls"));
        return Out;
    }
    State.Look = FVector2D::ZeroVector; State.Pressed = State.Released = 0;
    return Out;
}
