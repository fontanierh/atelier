#pragma once
#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "JapanGameMode.h"
#include "JapanSession.generated.h"

class SWidget;
class AJapanWorld;

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
};

UCLASS()
class YORIMICHI_API AJapanPlayerState : public APlayerState
{
    GENERATED_BODY()
public:
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
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
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
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
    void MarkAdmissionComplete() { bAdmissionComplete = true; }
private:
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
