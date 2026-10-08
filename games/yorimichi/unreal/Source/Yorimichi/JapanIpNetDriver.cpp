#include "JapanIpNetDriver.h"
#include "JapanNetwork.h"
#include "IPAddress.h"
#include "SocketSubsystem.h"
#include "Sockets.h"
#include "Misc/CommandLine.h"

UJapanIpNetDriver::UJapanIpNetDriver(const FObjectInitializer& Initializer) : Super(Initializer) {}

bool UJapanIpNetDriver::InitBase(bool bInitAsClient, FNetworkNotify* InNotify, const FURL& URL,
    bool bReuseAddressAndPort, FString& Error)
{
    PrivateAddress.Reset();
    if (!bInitAsClient)
    {
        // The local QA harness opts into loopback explicitly. Travel URL options cannot
        // enable it, and ordinary hosting has no wildcard/public fallback.
        FString QARole, Multihome;
        const bool bLocalQA = FParse::Value(FCommandLine::Get(), TEXT("networkqa="), QARole) && QARole == TEXT("server") &&
            FParse::Value(FCommandLine::Get(), TEXT("MULTIHOME="), Multihome) && Multihome == TEXT("127.0.0.1");
        if (bLocalQA) PrivateAddress = TEXT("127.0.0.1");
        else if (!JapanNetwork::PrivateHostAddress(PrivateAddress, Error)) return false;
        MaxPortCountToTry = 0;
        bExitOnBindFailure = false;
    }
    if (!Super::InitBase(bInitAsClient, InNotify, URL, bReuseAddressAndPort, Error))
    {
        if (!bInitAsClient)
        {
            UE_LOG(LogTemp, Warning, TEXT("Private listener initialization failed: %s"), *Error);
            Error = FString::Printf(TEXT("Could not open game port %d on Tailscale. Close any other hosted game and check Tailscale."), URL.Port);
        }
        return false;
    }
    if (!PrivateAddress.IsEmpty())
    {
        auto Actual = GetSocketSubsystem()->CreateInternetAddr();
        if (GetSocket()) GetSocket()->GetAddress(*Actual);
        if (!GetSocket() || Actual->ToString(false) != PrivateAddress)
        {
            LowLevelDestroy();
            Error = TEXT("The game could not open its private network address. Check Tailscale and try hosting again.");
            return false;
        }
    }
    return true;
}

FUniqueSocket UJapanIpNetDriver::CreateAndBindSocket(TSharedRef<FInternetAddr> BindAddr, int32 Port,
    bool bReuseAddressAndPort, int32 ReceiveBytes, int32 SendBytes, FString& Error)
{
    if (!PrivateAddress.IsEmpty())
    {
        ISocketSubsystem* Sockets = GetSocketSubsystem();
        if (!Sockets) { Error = TEXT("No socket subsystem is available."); return nullptr; }
        // Replace the resolver's wildcard, including an IPv6 wildcard, before creating
        // the socket. Resolver InitListen binds one socket and obtains its actual address.
        BindAddr = Sockets->CreateInternetAddr(FNetworkProtocolTypes::IPv4);
        bool bValid = false;
        BindAddr->SetIp(*PrivateAddress, bValid);
        if (!bValid) { Error = TEXT("The private network address is invalid."); return nullptr; }
    }
    return Super::CreateAndBindSocket(BindAddr, Port, bReuseAddressAndPort, ReceiveBytes, SendBytes, Error);
}

bool UJapanIpNetDriver::InitListen(FNetworkNotify* InNotify, FURL& URL, bool bReuseAddressAndPort, FString& Error)
{
    const bool bListening = Super::InitListen(InNotify, URL, bReuseAddressAndPort, Error);
    if (!bListening && IsRunningDedicatedServer())
    {
        UE_LOG(LogTemp, Error, TEXT("Private dedicated listener failed: %s"), *Error);
        JapanNetwork::RequestFailureExit();
    }
    return bListening;
}
