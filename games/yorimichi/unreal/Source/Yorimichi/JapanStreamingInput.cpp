#include "JapanStreamingInput.h"
#include "WandererCharacter.h"
#include "SkateboardComponent.h"
#include "SailboatComponent.h"
#include "JapanPreferences.h"
#include "JapanMap.h"
#include "JapanCharacterMovement.h"
#include "JapanWorld.h"
#include "ZeppelinService.h"
#include "IPixelStreaming2Module.h"
#include "IPixelStreaming2Streamer.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"
#include "Async/Async.h"
#include "HAL/PlatformTime.h"
#include "GameFramework/CharacterMovementComponent.h"

FJapanStreamingInput::~FJapanStreamingInput()
{
    if (auto H=Handler.Pin()) if (Previous) H->RegisterMessageHandler(TEXT("UIInteraction"),Previous);
}

void FJapanStreamingInput::SendSettings(const FString& Source)
{
    auto* C=Rider.Get(); auto S=Streamer.Pin();
    if (!C || !C->GetPreferences() || !S) return;
    auto Json=MakeShared<FJsonObject>();
    Json->SetNumberField(TEXT("yorimichi"),1); Json->SetStringField(TEXT("kind"),TEXT("settings"));
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (const auto& V : C->GetPreferences()->GetValues())
    {
        auto Row=MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("key"),V.Key); Row->SetStringField(TEXT("label"),V.Label);
        Row->SetNumberField(TEXT("value"),V.Value); Row->SetNumberField(TEXT("min"),V.Minimum); Row->SetNumberField(TEXT("max"),V.Maximum);
        Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Json->SetArrayField(TEXT("values"),Rows);
    FString Text; FJsonSerializer::Serialize(Json,TJsonWriterFactory<>::Create(&Text));
    S->SendPlayerMessage(Source,TEXT("Response"),Text);
}

void FJapanStreamingInput::SendMap(const FString& Source)
{
    auto* C=Rider.Get(); auto S=Streamer.Pin();
    if (!C || !C->GetMap() || !S) return;
    const UJapanMap* M=C->GetMap();
    auto Json=MakeShared<FJsonObject>();
    Json->SetNumberField(TEXT("yorimichi"),1); Json->SetStringField(TEXT("kind"),TEXT("map"));
    Json->SetBoolField(TEXT("loaded"),M->IsLoaded());
    Json->SetStringField(TEXT("image"),TEXT("/map/map.jpg"));
    const FBox2D& B=M->GetBounds();
    TArray<TSharedPtr<FJsonValue>> Bounds; for (double V : {B.Min.X,B.Min.Y,B.Max.X,B.Max.Y}) Bounds.Add(MakeShared<FJsonValueNumber>(V));
    Json->SetArrayField(TEXT("bounds"),Bounds);
    auto AddProjection=[&](const TCHAR* Key,const TArray<FVector2D>& Knots)
    {
        TArray<TSharedPtr<FJsonValue>> Rows;
        for(const auto& K:Knots)
        {TArray<TSharedPtr<FJsonValue>> Pair;Pair.Add(MakeShared<FJsonValueNumber>(K.X));Pair.Add(MakeShared<FJsonValueNumber>(K.Y));Rows.Add(MakeShared<FJsonValueArray>(Pair));}
        Json->SetArrayField(Key,Rows);
    };
    AddProjection(TEXT("projection_x"),M->GetProjectionX());AddProjection(TEXT("projection_y"),M->GetProjectionY());
    TArray<TSharedPtr<FJsonValue>> Zones;
    for (const auto& Z : M->GetZones())
    {
        auto Row=MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("key"),Z.Key); Row->SetStringField(TEXT("name"),Z.Name); Row->SetStringField(TEXT("hint"),Z.Hint);
        Row->SetNumberField(TEXT("x"),Z.Location.X/100.0); Row->SetNumberField(TEXT("y"),-Z.Location.Y/100.0);   // Blender metres, north up
        Zones.Add(MakeShared<FJsonValueObject>(Row));
    }
    Json->SetArrayField(TEXT("zones"),Zones);
    FString Text; FJsonSerializer::Serialize(Json,TJsonWriterFactory<>::Create(&Text));
    S->SendPlayerMessage(Source,TEXT("Response"),Text);
}

void FJapanStreamingInput::Receive(const FString& Source, const FString& Descriptor)
{
    TSharedPtr<FJsonObject> J;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Descriptor),J) || !J.IsValid()) return;
    double Protocol=0;
    if (!J->TryGetNumberField(TEXT("yorimichi"),Protocol) || Protocol!=1) return;
    FString Action;
    if (J->TryGetStringField(TEXT("action"),Action))
    {
        auto* C=Rider.Get(); if (!C || !C->GetPreferences()) return;
        if (Action==TEXT("settings")) SendSettings(Source);
        else if (Action==TEXT("map")) SendMap(Source);
        else if (Action==TEXT("teleport"))
        {
            FString Zone; bool bOk=false;
            if (J->TryGetStringField(TEXT("zone"),Zone) && Zone.Len()<=32 && C->GetMap() && !C->IsCinematic()) bOk=C->GetMap()->TeleportToZone(Zone);
            if (bOk) { Move=Look=FVector2D::ZeroVector; Buttons=PendingPress=0; bJumpRelease=true; }
            UE_LOG(LogTemp,Display,TEXT("PHONE STREAM teleport %s: %s"),*Zone,bOk ? TEXT("ok") : TEXT("unknown zone"));
            if (auto S=Streamer.Pin()) S->SendPlayerMessage(Source,TEXT("Response"),FString::Printf(TEXT("{\"yorimichi\":1,\"kind\":\"teleport\",\"zone\":\"%s\",\"ok\":%s}"),*Zone.ReplaceCharWithEscapedChar(),bOk ? TEXT("true") : TEXT("false")));
        }
        else if (Action==TEXT("flightSpeed"))
        {
            double Delta=0;
            if (J->TryGetNumberField(TEXT("delta"),Delta) && FMath::IsFinite(Delta) && C->GetZeppelin() && C->IsZeppelinPassenger())
                C->GetZeppelin()->AdjustFlightSpeed(Delta<0?-1:1);
        }
        else if (Action==TEXT("setSetting"))
        {
            FString Key; double Number=0;
            if (J->TryGetStringField(TEXT("key"),Key) && J->TryGetNumberField(TEXT("value"),Number) && FMath::IsFinite(Number))
                if (C->GetPreferences()->SetValue(Key,Number)) SendSettings(Source);
        }
        return;
    }
    double Version=0, X=0, Y=0, DX=0, DY=0, Mask=0;
    if (!J->TryGetNumberField(TEXT("yorimichi"),Version) || Version!=1 ||
        !J->TryGetNumberField(TEXT("x"),X) || !J->TryGetNumberField(TEXT("y"),Y) ||
        !J->TryGetNumberField(TEXT("dx"),DX) || !J->TryGetNumberField(TEXT("dy"),DY) ||
        !J->TryGetNumberField(TEXT("buttons"),Mask)) return;
    if (!FMath::IsFinite(X)||!FMath::IsFinite(Y)||!FMath::IsFinite(DX)||!FMath::IsFinite(DY)||!FMath::IsFinite(Mask)||Mask<0||Mask>511||Mask!=FMath::FloorToDouble(Mask)) return;
    bool bPaused=false;J->TryGetBoolField(TEXT("paused"),bPaused);
    if(bPaused){X=Y=DX=DY=Mask=0;if(auto* C=Rider.Get())C->Sailboat->EmergencyStop();}
    Move=FVector2D(FMath::Clamp(X,-1.,1.),FMath::Clamp(Y,-1.,1.)).GetClampedToMaxSize(1.);
    Look+=FVector2D(FMath::Clamp(DX,-30.,30.),FMath::Clamp(DY,-30.,30.));
    const uint32 Next=uint32(Mask);
    PendingPress|=Next&~Buttons;
    bJumpRelease|=(Buttons&1)&&!(Next&1);
    Buttons=Next;LastInput=FPlatformTime::Seconds();bHasInput=true;PlayerId=Source;
}

void FJapanStreamingInput::Tick(float Dt)
{
    AWandererCharacter* C=Rider.Get();if(!C)return;
    if (!Handler.IsValid() && IPixelStreaming2Module::IsAvailable())
    {
        auto& Module=IPixelStreaming2Module::Get();
        auto S=Module.FindStreamer(Module.GetDefaultStreamerID());
        auto H=S.IsValid()?S->GetInputHandler().Pin():nullptr;
        if(H)
        {
            Handler=H;Streamer=S;Previous=H->FindMessageHandler(TEXT("UIInteraction"));
            TWeakPtr<FJapanStreamingInput> Weak=AsShared();
            H->RegisterMessageHandler(TEXT("UIInteraction"),[Weak](FString Source,FMemoryReader Ar)
            {
                if(Ar.TotalSize()-Ar.Tell()<2)return;
                uint16 Length=0;Ar<<Length;
                if(Length>2048 || Ar.TotalSize()-Ar.Tell()<int64(Length)*sizeof(TCHAR))return;
                FString Descriptor;Descriptor.GetCharArray().SetNumUninitialized(Length+1);
                Ar.Serialize(Descriptor.GetCharArray().GetData(),Length*sizeof(TCHAR));Descriptor.GetCharArray()[Length]=0;
                AsyncTask(ENamedThreads::GameThread,[Weak,Source,Descriptor](){if(auto Self=Weak.Pin())Self->Receive(Source,Descriptor);});
            });
            UE_LOG(LogTemp,Display,TEXT("PHONE STREAM input ready"));
        }
    }
    const double Now=FPlatformTime::Seconds();
    const bool bExpired=Now-LastInput>.6;
    if(bHasInput && bExpired)
    {
        Move=FVector2D::ZeroVector;Look=FVector2D::ZeroVector;Buttons=PendingPress=0;bJumpRelease=true;
        // On a lost connection, brake the board rather than coasting out of view.
        C->GetCharacterMovement()->StopMovementImmediately();C->Sailboat->EmergencyStop();bHasInput=false;
        UE_LOG(LogTemp,Display,TEXT("PHONE STREAM input timeout: released controls"));
    }
    const bool bBrake=bExpired && LastInput>0 && (C->Skateboard->IsEquipped() || C->Sailboat->IsEquipped());
    if (PendingPress&64)
    {
        Move=Look=FVector2D::ZeroVector; Buttons&=64; PendingPress=0; bJumpRelease=false;
        C->ReturnToSpawn();
    }
    C->MoveIntent=C->bMenuOpen?FVector2D::ZeroVector:bBrake?FVector2D(0,-1):Move;
    C->bJog=(Buttons&32)!=0;
    C->bSprintHeld=(Buttons&128)!=0;
    if(C->Controller && !C->bMenuOpen)
    {
        FRotator R=C->Controller->GetControlRotation();
        if(!Look.IsNearlyZero())C->MegaCameraGrace=2.f;
        R.Yaw+=FMath::Clamp(Look.X*C->MouseSensitivity/.4f,-45.,45.);R.Pitch=FMath::Clamp(FRotator::NormalizeAxis(R.Pitch)-Look.Y*C->MouseSensitivity/.4f,-65.,45.);
        C->Controller->SetControlRotation(R);
    }
    Look=FVector2D::ZeroVector;
    const FInputActionValue Press(true);
    if(PendingPress&1)C->RequestJump(Press);
    if(PendingPress&2)C->Dash(Press);
    if(PendingPress&256)C->Dodge(Press);
    if(PendingPress&4)C->Interact(Press);
    if(PendingPress&8)
    {
        C->ToggleSailboat(Press);
        if(auto S=Streamer.Pin())S->SendPlayerMessage(PlayerId,TEXT("Response"),FString::Printf(TEXT("{\"yorimichi\":1,\"kind\":\"hint\",\"text\":\"%s\"}"),*C->Sailboat->GetStatus().ReplaceCharWithEscapedChar()));
    }
    if(PendingPress&16)C->Wave(Press);
    if(bJumpRelease)C->ReleaseJump(FInputActionValue(false));
    PendingPress=0;bJumpRelease=false;
    if(Now-LastStatus>.2 && Now-LastInput<2.)
    {
        LastStatus=Now;
        if(auto S=Streamer.Pin())
        {
            const FVector P=C->GetActorLocation();
            const auto* Mega=Cast<UJapanCharacterMovement>(C->GetCharacterMovement());
            FString RampHint=C->GetZeppelin()?C->GetZeppelin()->Hint(C):FString();
            if(RampHint.IsEmpty())RampHint=Mega?Mega->MegaEntryHint():FString();
            // The broadcast API holds the participants lock while synchronously
            // sending, deadlocking against incoming data on UE5.8's RTC thread.
            // Unicast snapshots the track and releases that lock before sending.
            S->SendPlayerMessage(PlayerId,TEXT("Response"),FString::Printf(TEXT("{\"yorimichi\":1,\"ready\":%s,\"speed\":%.1f,\"skating\":%s,\"sailboat\":%s,\"falling\":%s,\"x\":%.1f,\"y\":%.1f,\"z\":%.1f,\"yaw\":%.1f,\"viewYaw\":%.2f,\"viewPitch\":%.2f,\"inputActive\":%s,\"fps\":%.1f,\"showFps\":%s,\"rampHint\":\"%s\",\"zeppelinStage\":%d,\"flightSpeed\":%.2f,\"propellerAngle\":%.2f,\"zeppelinDock\":%d,\"megaStage\":%d,\"stamina\":%.3f,\"staminaRings\":%.0f,\"sprinting\":%s,\"exhausted\":%s}"),C->IsReady()?TEXT("true"):TEXT("false"),(C->Sailboat->IsEquipped()?C->Sailboat->GetSpeed():C->GetVelocity().Size()),C->Skateboard->IsEquipped()?TEXT("true"):TEXT("false"),C->Sailboat->IsEquipped()?TEXT("true"):TEXT("false"),C->GetCharacterMovement()->IsFalling()?TEXT("true"):TEXT("false"),P.X,P.Y,P.Z,C->GetActorRotation().Yaw,C->GetControlRotation().Yaw,FRotator::NormalizeAxis(C->GetControlRotation().Pitch),bHasInput?TEXT("true"):TEXT("false"),1.f/FMath::Max(Dt,.001f),C->GetPreferences()->ShowFrameRate()?TEXT("true"):TEXT("false"),*RampHint.ReplaceCharWithEscapedChar(),C->GetZeppelin()?C->GetZeppelin()->GetStage():-1,C->GetZeppelin()?C->GetZeppelin()->GetFlightSpeed():1.f,C->GetZeppelin()?C->GetZeppelin()->GetPropellerAngle():0.f,C->GetZeppelin()?C->GetZeppelin()->GetDock():-1,Mega&&Mega->IsMega()?Mega->MegaStage():-1,C->Stamina.Units,C->Stamina.Capacity,C->Stamina.Sprinting?TEXT("true"):TEXT("false"),C->Stamina.Exhausted?TEXT("true"):TEXT("false")));
        }
    }
}
