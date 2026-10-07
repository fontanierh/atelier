#include "JapanSession.h"
#include "LiveLibrary.h"
#include "JapanNetwork.h"
#include "JapanWorld.h"
#include "JapanPreferences.h"
#include "JapanHUD.h"
#include "BotwRider.h"
#include "BotwMoveSet.h"
#include "CairoCharacter.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/GameSession.h"
#include "Kismet/GameplayStatics.h"
#include "Net/UnrealNetwork.h"
#include "UObject/UObjectGlobals.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Containers/Ticker.h"

void UJapanGameInstance::Init()
{
    Super::Init();
    if (GEngine)
    {
        GEngine->OnNetworkFailure().AddUObject(this, &UJapanGameInstance::NetworkFailure);
        GEngine->OnTravelFailure().AddUObject(this, &UJapanGameInstance::TravelFailure);
    }
    FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(this, &UJapanGameInstance::MapLoaded);
    StartNetworkQA();
}
void UJapanGameInstance::Shutdown()
{
    FTSTicker::GetCoreTicker().RemoveTicker(NetworkQATicker);
    CloseFriends();
    if (GEngine)
    {
        GEngine->OnNetworkFailure().RemoveAll(this);
        GEngine->OnTravelFailure().RemoveAll(this);
    }
    FCoreUObjectDelegates::PostLoadMapWithWorld.RemoveAll(this);
    Super::Shutdown();
}
void UJapanGameInstance::RememberRider()
{
    if (APlayerController* Player = GetFirstLocalPlayerController())
        if (auto* Pawn = Cast<AWandererCharacter>(Player->GetPawn()))
            JoinRider = ABotwRider::NameOf(Pawn);
    if (!JapanNetwork::IsPlayableRider(JoinRider)) JoinRider = JapanNetwork::DefaultRider();
}
FString UJapanGameInstance::GetJoinRider() const
{
    return JapanNetwork::IsPlayableRider(JoinRider) ? JoinRider : JapanNetwork::DefaultRider();
}
void UJapanGameInstance::HostGame(int32 Capacity)
{
    if (!GetWorld() || JapanNetwork::IsOnline(GetWorld()))
    { Status = TEXT("Leave the current session before hosting another game."); return; }
    FString Identity, Error;
    if (!JapanNetwork::Identity(Identity, Error)) { Status = Error; return; }
    if (!JapanNetwork::IsPlayableRider(JapanNetwork::DefaultRider()))
    { Status = TEXT("The merged player character is missing from this build."); return; }
    RememberRider();
    Capacity = FMath::Clamp(Capacity, 2, JapanNetwork::MaximumCapacity);
    CloseFriends();
    AtelierLive::Stop();
    Status = TEXT("Starting your shared world..."); bShowAfterTravel = false;
    const FString Options = FString::Printf(TEXT("listen?game=/Script/Yorimichi.JapanNetworkGameMode?capacity=%d"), Capacity);
    UGameplayStatics::OpenLevel(this, FName(JapanNetwork::Map()), true, Options);
}
void UJapanGameInstance::JoinGame(const FString& Address)
{
    if (!GetWorld() || JapanNetwork::IsOnline(GetWorld()))
    { Status = TEXT("Leave the current session before joining another game."); return; }
    FString Endpoint, Error, Identity;
    if (!JapanNetwork::ParseEndpoint(Address, Endpoint, Error) || !JapanNetwork::Identity(Identity, Error))
    { Status = Error; return; }
    APlayerController* Player = GetFirstLocalPlayerController();
    if (!Player) { Status = TEXT("The local player is still loading."); return; }
    RememberRider();
    JoinAddress = Endpoint; CloseFriends();
    AtelierLive::Stop();
    Status = TEXT("Connecting to ") + Endpoint + TEXT("..."); bShowAfterTravel = false;
    Player->ClientTravel(Endpoint, TRAVEL_Absolute);
}
void UJapanGameInstance::LeaveGame()
{
    CloseFriends();
    Status = TEXT("You left the shared session.");
    bShowAfterTravel = true;
    UGameplayStatics::OpenLevel(this, FName(JapanNetwork::Map()), true);
}
void UJapanGameInstance::ReturnWithError(const FString& Message)
{
    LeaveGame(); Status = Message;
}
void UJapanGameInstance::NetworkFailure(UWorld* World, UNetDriver*, ENetworkFailure::Type, const FString& Reason)
{
    if (World && World != GetWorld()) return;
    Status = Reason.IsEmpty() ? TEXT("Connection lost. Check that the host is running and reachable, then join again.") : Reason;
    bShowAfterTravel = true; CloseFriends();
    // Engine disconnect handling returns to the default map; do not start a second competing travel here.
    UE_LOG(LogTemp, Warning, TEXT("NETWORK failure: %s"), *Status);
}
void UJapanGameInstance::TravelFailure(UWorld* World, ETravelFailure::Type, const FString& Reason)
{
    if (World && World != GetWorld()) return;
    Status = TEXT("Could not enter the shared world: ") + Reason;
    bShowAfterTravel = true;
    if (GetFirstLocalPlayerController()) Friends();
}
void UJapanGameInstance::MapLoaded(UWorld* World)
{
    if (World == GetWorld() && JapanNetwork::IsOnline(World)) AtelierLive::Stop();
    if (World == GetWorld()) ShowPendingStatus();
}

void UJapanGameInstance::ShowPendingStatus()
{
    // PostLoadMap may run before the replacement local controller exists. Keep the notice
    // pending until its UI really opens; the controller retries on its first standalone tick.
    if (bShowAfterTravel && GetWorld() && GetWorld()->GetNetMode() == NM_Standalone) Friends();
}

void UJapanGameInstance::Friends()
{
    if (!GetWorld() || GetWorld()->GetNetMode() == NM_DedicatedServer || !GEngine || !GEngine->GameViewport) return;
    CloseFriends();
    APlayerController* Player = GetFirstLocalPlayerController();
    if (!Player) return;
    bShowAfterTravel = false;
    if (auto* Pawn = Cast<AWandererCharacter>(Player->GetPawn()))
    {
        if (Pawn->GetPreferences()) Pawn->GetPreferences()->CloseMenu();
        Pawn->SetMenuOpen(true);
    }
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    TSharedPtr<SButton> FirstButton;
    Rows->AddSlot().AutoHeight().Padding(0,0,0,16)[SNew(STextBlock).Text(FText::FromString(TEXT("Play with friends"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",24))];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,16)[SNew(STextBlock).AutoWrapText(true).Text_Lambda([this] { return FText::FromString(Status); })];
    if (!JapanNetwork::IsOnline(GetWorld()))
    {
        Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SAssignNew(FirstButton, SButton).Text(FText::FromString(TEXT("Host a private game")))
            .OnClicked_Lambda([this] { HostGame(); return FReply::Handled(); })];
        Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[SNew(STextBlock).AutoWrapText(true)
            .Text(FText::FromString(TEXT("Use matching builds. Connect both devices through Tailscale, then enter the host's full device name or IPv4 address below. Game port: 7777.")))];
        Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[SNew(SEditableTextBox).Text(FText::FromString(JoinAddress))
            .HintText(FText::FromString(TEXT("Host device name or 100.x.x.x:7777")))
            .OnTextChanged_Lambda([this](const FText& Text) { JoinAddress = Text.ToString(); })];
        Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(SButton).Text(FText::FromString(TEXT("Join game")))
            .OnClicked_Lambda([this] { JoinGame(JoinAddress); return FReply::Handled(); })];
    }
    else
    {
        Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(STextBlock).AutoWrapText(true)
            .Text(FText::FromString(GetWorld()->GetNetMode() == NM_ListenServer
                ? TEXT("You are hosting. Share this device's Tailscale name or address, with port 7777. Leaving ends the session for everyone.")
                : TEXT("You are connected. Leaving returns you to your own world.")))];
        if (GetWorld()->GetNetMode() == NM_ListenServer)
        {
            const FString Endpoint = JapanNetwork::LocalEndpoint(GetWorld());
            if (!Endpoint.IsEmpty())
            {
                Rows->AddSlot().AutoHeight().Padding(0,0,0,8)[SNew(STextBlock).Text(FText::FromString(Endpoint))];
                Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(SButton).Text(FText::FromString(TEXT("Copy join address")))
                    .OnClicked_Lambda([Endpoint] { FPlatformApplicationMisc::ClipboardCopy(*Endpoint); return FReply::Handled(); })];
            }
        }
        Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SAssignNew(FirstButton, SButton).Text(FText::FromString(TEXT("Leave session")))
            .OnClicked_Lambda([this] { LeaveGame(); return FReply::Handled(); })];
    }
    Rows->AddSlot().AutoHeight()[SNew(SButton).Text(FText::FromString(TEXT("Back to game")))
        .OnClicked_Lambda([this] { CloseFriends(); return FReply::Handled(); })];
    Menu = SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center)
        .BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0,0,0,.65f))
        [SNew(SBox).WidthOverride(560)[SNew(SBorder).Padding(28)
            .BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.025f,.032f,.028f,1))[Rows]]];
    GEngine->GameViewport->AddViewportWidgetContent(Menu.ToSharedRef(),30);
    FInputModeUIOnly Mode; Mode.SetWidgetToFocus(FirstButton); Player->SetInputMode(Mode); Player->bShowMouseCursor = true;
}
void UJapanGameInstance::CloseFriends()
{
    if (!Menu) return;
    if (GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
    Menu.Reset();
    if (APlayerController* Player = GetFirstLocalPlayerController())
    {
        if (auto* Pawn = Cast<AWandererCharacter>(Player->GetPawn())) Pawn->SetMenuOpen(false);
        Player->SetInputMode(FInputModeGameOnly()); Player->bShowMouseCursor = false;
    }
}

void AJapanPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AJapanPlayerState, SessionPlayerId);
    DOREPLIFETIME(AJapanPlayerState, RiderName);
    DOREPLIFETIME(AJapanPlayerState, bShield);
    DOREPLIFETIME(AJapanPlayerState, bWorldReady);
}
void AJapanGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AJapanGameState, SessionId);
    DOREPLIFETIME(AJapanGameState, ContentIdentity);
    DOREPLIFETIME(AJapanGameState, StartupError);
    DOREPLIFETIME(AJapanGameState, Capacity);
    DOREPLIFETIME(AJapanGameState, bTrustedSkating);
    DOREPLIFETIME(AJapanGameState, bWorldReady);
}

AJapanPlayerController::AJapanPlayerController()
{
    PrimaryActorTick.bCanEverTick = true;
}
void AJapanPlayerController::BeginPlay()
{
    Super::BeginPlay();
    AdmissionStarted = FPlatformTime::Seconds();
    if (GetNetMode() == NM_Client && IsLocalController()) JapanNetwork::EnsureWorld(GetWorld());
}
void AJapanPlayerController::SetupInputComponent()
{
    Super::SetupInputComponent();
    if (InputComponent)
        InputComponent->BindKey(EKeys::F10, IE_Pressed, this, &AJapanPlayerController::OpenFriends);
}
void AJapanPlayerController::OpenFriends()
{
    if (IsLocalController()) if (auto* Session = GetGameInstance<UJapanGameInstance>()) Session->Friends();
}
void AJapanPlayerController::Tick(float Dt)
{
    Super::Tick(Dt);
    if (IsLocalController()) if (auto* Session = GetGameInstance<UJapanGameInstance>()) Session->ShowPendingStatus();
    if (!JapanNetwork::IsOnline(GetWorld())) return;
    if (HasAuthority() && !IsLocalController()) DrainSkateFrames();
    if (HasAuthority() && !bAdmissionComplete && FPlatformTime::Seconds() - AdmissionStarted > 180.)
    {
        bAdmissionComplete = true;
        ClientAdmissionFailure(TEXT("World loading timed out. Try joining again with the matching build."));
        if (auto* Mode = GetWorld()->GetAuthGameMode<AJapanNetworkGameMode>())
            if (Mode->GameSession) Mode->GameSession->KickPlayer(this, FText::FromString(TEXT("World readiness timed out")));
        return;
    }
    if (!IsLocalController() || bReadinessSent) return;
    const AJapanGameState* State = GetWorld()->GetGameState<AJapanGameState>();
    if (!State) return;
    if (!State->StartupError.IsEmpty())
    { bReadinessSent = true; ClientAdmissionFailure_Implementation(State->StartupError); return; }
    AJapanWorld* World = JapanNetwork::FindWorld(GetWorld());
    if (World && !World->BootstrapError.IsEmpty())
    { bReadinessSent = true; ClientAdmissionFailure_Implementation(TEXT("Incomplete local world: ") + World->BootstrapError); return; }
    if (!World || !World->bGameplayReady || !State->bWorldReady || State->ContentIdentity.IsEmpty()) return;
    FString Identity, Error;
    if (!JapanNetwork::Identity(Identity, Error) || Identity != State->ContentIdentity)
    {
        bReadinessSent = true;
        ClientAdmissionFailure_Implementation(Error.IsEmpty() ? TEXT("The host has a different game build or gameplay data. Install matching builds.") : Error);
        return;
    }
    bReadinessSent = true;
    const auto* Session = GetGameInstance<UJapanGameInstance>();
    ServerWorldReady(Identity, Session ? Session->GetJoinRider() : JapanNetwork::DefaultRider(), UJapanPreferences::Saved(TEXT("shield"), 0.f) > .5f);
}
void AJapanPlayerController::ServerWorldReady_Implementation(const FString& Identity, const FString& RiderName, bool bShield)
{
    if (bServerReadinessReceived) return;
    bServerReadinessReceived = true;
    if (Identity.Len() > 160 || RiderName.Len() > 64)
    { ClientAdmissionFailure(TEXT("Invalid join request.")); return; }
    if (auto* Mode = GetWorld()->GetAuthGameMode<AJapanNetworkGameMode>()) Mode->Admit(this, Identity, RiderName, bShield);
    else ClientAdmissionFailure(TEXT("This world does not support multiplayer."));
}
void AJapanPlayerController::ClientAdmissionFailure_Implementation(const FString& Reason)
{
    UE_LOG(LogTemp, Warning, TEXT("NETWORK admission refused: %s"), *Reason);
    if (auto* Session = GetGameInstance<UJapanGameInstance>()) Session->ReturnWithError(Reason);
}
void AJapanPlayerController::ClientSessionReady_Implementation()
{
    bAdmissionComplete = true;
    if (auto* Session = GetGameInstance<UJapanGameInstance>()) Session->SetSessionStatus(TEXT("Connected. Your shared world is ready."));
    UE_LOG(LogTemp, Display, TEXT("NETWORK client ready"));
}

AJapanNetworkGameMode::AJapanNetworkGameMode()
{
    PlayerControllerClass = AJapanPlayerController::StaticClass();
    PlayerStateClass = AJapanPlayerState::StaticClass();
    GameStateClass = AJapanGameState::StaticClass();
    DefaultPawnClass = ACairoCharacter::StaticClass();
    HUDClass = AJapanHUD::StaticClass();
    bStartPlayersAsSpectators = true;
    bPauseable = false;
}
void AJapanNetworkGameMode::InitGame(const FString& MapName, const FString& Options, FString& Error)
{
    Super::InitGame(MapName, Options, Error);
    SessionCapacity = FMath::Clamp(UGameplayStatics::GetIntOption(Options, TEXT("capacity"), JapanNetwork::DefaultCapacity), 2, JapanNetwork::MaximumCapacity);
    if (GameSession) GameSession->MaxPlayers = SessionCapacity;
}
void AJapanNetworkGameMode::BeginPlay()
{
    // Deliberately skip the offline mode's player-0 bootstrap. This server can have no local controller.
    AGameModeBase::BeginPlay();
    SessionWorld = JapanNetwork::EnsureWorld(GetWorld());
    if (auto* State = GetGameState<AJapanGameState>())
    {
        State->SessionId = FGuid::NewGuid().ToString(EGuidFormats::Digits);
        State->Capacity = SessionCapacity;
        JapanNetwork::Identity(State->ContentIdentity, State->StartupError);
        State->bWorldReady = SessionWorld && SessionWorld->bGameplayReady;
        if (!State->bWorldReady) State->StartupError = TEXT("The server could not finish loading gameplay collision and rails: ") +
            (SessionWorld ? SessionWorld->BootstrapError : TEXT("world actor missing"));
        State->ForceNetUpdate();
        UE_LOG(LogTemp, Display, TEXT("NETWORK server session=%s capacity=%d ready=%d dedicated=%d"),
            *State->SessionId, SessionCapacity, State->bWorldReady, GetNetMode() == NM_DedicatedServer);
    }
}
void AJapanNetworkGameMode::PreLogin(const FString& Options, const FString& Address, const FUniqueNetIdRepl& UniqueId, FString& Error)
{
    Super::PreLogin(Options, Address, UniqueId, Error);
    if (!Error.IsEmpty()) return;
    if (const auto* State = GetGameState<AJapanGameState>())
    {
        if (!State->StartupError.IsEmpty()) Error = State->StartupError;
        else if (State->PlayerArray.Num() >= SessionCapacity) Error = TEXT("This session is full.");
    }
}
void AJapanNetworkGameMode::PostLogin(APlayerController* Player)
{
    Super::PostLogin(Player);
    if (auto* State = Player->GetPlayerState<AJapanPlayerState>())
        State->SessionPlayerId = FGuid::NewGuid().ToString(EGuidFormats::Digits);
}
void AJapanNetworkGameMode::HandleStartingNewPlayer_Implementation(APlayerController*)
{
    // World/content acknowledgement is the only path to a playable pawn.
}
UClass* AJapanNetworkGameMode::GetDefaultPawnClassForController_Implementation(AController* Controller)
{
    const auto* State = Controller ? Controller->GetPlayerState<AJapanPlayerState>() : nullptr;
    return State && State->RiderName != ACairoCharacter::BotwName() ? ABotwRider::StaticClass() : ACairoCharacter::StaticClass();
}
APawn* AJapanNetworkGameMode::SpawnDefaultPawnAtTransform_Implementation(AController* Controller, const FTransform& Transform)
{
    const auto* State = Controller ? Controller->GetPlayerState<AJapanPlayerState>() : nullptr;
    if (!State || !State->bWorldReady || !SessionWorld || !SessionWorld->bGameplayReady) return nullptr;
    AWandererCharacter* Pawn = GetWorld()->SpawnActorDeferred<AWandererCharacter>(GetDefaultPawnClassForController(Controller), Transform,
        nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
    if (!Pawn) return nullptr;
    Pawn->ConfigureNetworkRider(State->RiderName, State->bShield);
    FVector At = Transform.GetLocation();
    FRotator Facing = Transform.Rotator();
    At.Z += Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 3.f;
    if (!GetWorld()->FindTeleportSpot(Pawn, At, Facing)) { Pawn->Destroy(); return nullptr; }
    Pawn->FinishSpawning(FTransform(Facing, At));
    Pawn->EnterWorld(SessionWorld);
    return Pawn;
}
void AJapanNetworkGameMode::Admit(AJapanPlayerController* Player, const FString& Identity, const FString& RiderName, bool bShield)
{
    auto* State = GetGameState<AJapanGameState>();
    auto* Person = Player ? Player->GetPlayerState<AJapanPlayerState>() : nullptr;
    if (!Player || !State || !Person) return;
    if (Person->bWorldReady) return;
    FString Error;
    if (!State->bWorldReady || !State->StartupError.IsEmpty()) Error = TEXT("The server world is not ready.");
    else if (Identity != State->ContentIdentity) Error = TEXT("The game builds or gameplay data differ. Install matching builds.");
    else if (!JapanNetwork::IsPlayableRider(RiderName)) Error = TEXT("The requested character is not available in this build.");
    if (!Error.IsEmpty()) { Player->ClientAdmissionFailure(Error); return; }
    Person->RiderName = RiderName;
    Person->bShield = bShield;
    Person->bWorldReady = true;
    const int32 Index = FMath::Max(0, State->PlayerArray.IndexOfByKey(Person));
    const FRotator Facing = SessionWorld->PlayerStart.Rotator();
    FVector Ground = SessionWorld->PlayerStart.GetLocation() + Facing.RotateVector(FVector((Index / 4) * 160.f, (Index % 4) * 160.f, 0.f));
    FHitResult Hit;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(NetworkSpawn), false);
    if (!GetWorld()->LineTraceSingleByChannel(Hit, Ground + FVector(0,0,600), Ground - FVector(0,0,1800), ECC_WorldStatic, Query))
    { Person->bWorldReady = false; Player->ClientAdmissionFailure(TEXT("No safe spawn ground was found.")); return; }
    Ground.Z = Hit.ImpactPoint.Z;
    RestartPlayerAtTransform(Player, FTransform(Facing, Ground));
    if (!Player->GetPawn())
    { Person->bWorldReady = false; Player->ClientAdmissionFailure(TEXT("No clear player spawn was found.")); return; }
    Player->MarkAdmissionComplete();
    Player->ClientSessionReady();
    Person->ForceNetUpdate();
    UE_LOG(LogTemp, Display, TEXT("NETWORK admitted player=%s rider=%s"), *Person->SessionPlayerId, *Person->RiderName);
}
