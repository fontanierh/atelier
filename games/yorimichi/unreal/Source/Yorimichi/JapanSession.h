#pragma once
#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "Containers/Ticker.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "JapanGameMode.h"
#include "JapanSkateWire.h"
#include "JapanSkateBudget.h"
#include "JapanSession.generated.h"

class SWidget;
class AJapanWorld;
class AWandererCharacter;

UCLASS()
class YORIMICHI_API UJapanGameInstance : public UGameInstance
{
    GENERATED_BODY()
public:
    virtual void Init() override;
    virtual void Shutdown() override;
    UFUNCTION(Exec) void HostGame(int32 Capacity = 2);
    UFUNCTION(Exec) void JoinGame(const FString& Address);
    UFUNCTION(Exec) void LeaveGame();
    UFUNCTION(Exec) void Friends();
    void CloseFriends();
    void ShowPendingStatus();
    FString GetJoinRider() const;
    void SetSessionStatus(const FString& Message) { Status = Message; }
    void ReturnWithError(const FString& Message);
    const FString& GetSessionStatus() const { return Status; }
private:
    FString Status = TEXT("Host a private game, or join your friend's device.");
    void RememberRider();
    FString JoinRider;
    FString JoinAddress;
    bool bShowAfterTravel = false;
    TSharedPtr<SWidget> Menu;
    void NetworkFailure(UWorld*, UNetDriver*, ENetworkFailure::Type, const FString&);
    void TravelFailure(UWorld*, ETravelFailure::Type, const FString&);
    void MapLoaded(UWorld*);
    // Opt-in native lifecycle proof; available in packaged Development without editor Python.
    void StartNetworkQA();
    bool TickNetworkQA(float Dt);
    bool WriteNetworkQA(const TCHAR* Stage, const FString& Error = FString());
    FString NetworkQARole, NetworkQADirectory;
    FTSTicker::FDelegateHandle NetworkQATicker;
    double NetworkQAStarted = 0, NetworkQAConnected = 0, NetworkQALeaving = 0;
    bool bNetworkQAWorld = false, bNetworkQASawPeer = false;
};

UCLASS()
class YORIMICHI_API AJapanPlayerState : public APlayerState
{
    GENERATED_BODY()
public:
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    UPROPERTY(Replicated) FString SessionPlayerId;
    UPROPERTY(Replicated) FString RiderName;
    UPROPERTY(Replicated) bool bShield = false;
    UPROPERTY(Replicated) bool bWorldReady = false;
};

UCLASS()
class YORIMICHI_API AJapanGameState : public AGameStateBase
{
    GENERATED_BODY()
public:
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    UPROPERTY(Replicated) FString SessionId;
    UPROPERTY(Replicated) FString ContentIdentity;
    UPROPERTY(Replicated) FString StartupError;
    UPROPERTY(Replicated) int32 Capacity = 2;
    UPROPERTY(Replicated) bool bTrustedSkating = true;
    UPROPERTY(Replicated) bool bWorldReady = false;
};

UCLASS()
class YORIMICHI_API AJapanPlayerController : public APlayerController
{
    GENERATED_BODY()
public:
    AJapanPlayerController();
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    virtual void SetupInputComponent() override;
    UFUNCTION(Server, Reliable) void ServerWorldReady(const FString& Identity, const FString& RiderName, bool bShield);
    UFUNCTION(Client, Reliable) void ClientAdmissionFailure(const FString& Reason);
    UFUNCTION(Client, Reliable) void ClientSessionReady();
    // Server routes complete frames per connection, never back to the predicting owner.
    void SendSkateFrame(AWandererCharacter* Subject, const FJapanSkateFrame& Frame);
    void SendSkateBodies(AWandererCharacter* Subject, const FJapanSkateBodies& State);
    UFUNCTION(Client, Unreliable) void ClientSkatePose(AWandererCharacter* Subject, const FJapanSkateChunk& Chunk);
    UFUNCTION(Client, Unreliable) void ClientSkateBodies(AWandererCharacter* Subject, const FJapanSkateBodies& State);
    void MarkAdmissionComplete() { bAdmissionComplete = true; }
private:
    struct FSkateDelivery
    {
        double NextPose = -1., NextBodies = -1., PoseQueued = 0., BodiesQueued = 0.;
        bool bWarnedCapacity = false;
        FJapanSkateFrame LatestPose;
        FJapanSkateBodies LatestBodies;
        bool bPose = false, bBodies = false;
    };
    TMap<TWeakObjectPtr<AWandererCharacter>, FSkateDelivery> SkateDelivery;
    FJapanSkateBudget SkateBudget;
    int32 SkateRoundRobin = 0;
    uint64 SkateSuperseded = 0, SkateRoomRefused = 0, SkateBudgetRefused = 0;
    double LastSkateStats = -1.;
    uint64 LastSkateStatsTotal = 0;
    bool bSkateRoomBlocked = false;
    void DrainSkateFrames();
    void DeliverSkateFrame(AWandererCharacter* Subject, const FJapanSkateFrame& Frame);
    void DeliverSkateBodies(AWandererCharacter* Subject, const FJapanSkateBodies& State);
    double SkateInterest(AWandererCharacter* Subject, bool bBodies, double& TotalWeight) const;
    void OpenFriends();
    bool bReadinessSent = false;
    bool bServerReadinessReceived = false;
    bool bAdmissionComplete = false;
    double AdmissionStarted = 0;
};

/** Online game rules share the offline world's content, but never require a host avatar. */
UCLASS()
class YORIMICHI_API AJapanNetworkGameMode : public AJapanGameMode
{
    GENERATED_BODY()
public:
    AJapanNetworkGameMode();
    virtual void InitGame(const FString& MapName, const FString& Options, FString& Error) override;
    virtual void BeginPlay() override;
    virtual void PreLogin(const FString& Options, const FString& Address, const FUniqueNetIdRepl& UniqueId, FString& Error) override;
    virtual void PostLogin(APlayerController* Player) override;
    virtual void HandleStartingNewPlayer_Implementation(APlayerController* Player) override;
    virtual UClass* GetDefaultPawnClassForController_Implementation(AController* Controller) override;
    virtual APawn* SpawnDefaultPawnAtTransform_Implementation(AController* Controller, const FTransform& Transform) override;
    void Admit(AJapanPlayerController* Player, const FString& Identity, const FString& RiderName, bool bShield);
private:
    int32 SessionCapacity = 2;
    UPROPERTY() TObjectPtr<AJapanWorld> SessionWorld;
};
