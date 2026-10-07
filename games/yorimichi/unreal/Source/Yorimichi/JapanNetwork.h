#pragma once
#include "CoreMinimal.h"

class AJapanWorld;
class UWorld;

/** The same compatibility contract is checked before hosting and before a client becomes playable. */
namespace JapanNetwork
{
    constexpr int32 Protocol = 1;
    constexpr int32 DefaultCapacity = 2;
    constexpr int32 MaximumCapacity = 64;
    const TCHAR* Map();
    bool IsOnline(const UWorld* World);
    enum class EActivity : uint8 { Horse, Race, WorldEdit };
    /** One policy for every entry point, including menus and live commands. */
    bool Allows(UWorld* World, EActivity Activity);
    /** Copyable Tailscale IPv4 endpoint if the adapter is available; otherwise empty. */
    FString LocalEndpoint(UWorld* World);
    /** A strict host[:port] endpoint; never accept travel options, paths or console commands from the join field. */
    bool ParseEndpoint(const FString& Input, FString& Endpoint, FString& Error);
    /** Hashes the actual staged gameplay data and checks its build manifest. Cached for this process. */
    bool Identity(FString& Signature, FString& Error);
    /** A separate, nonreplicated static world on each machine. Shared actors have their own authority rules. */
    AJapanWorld* FindWorld(UWorld* World);
    AJapanWorld* EnsureWorld(UWorld* World);
    /** Reject arbitrary asset paths: online character definitions are selected from the installed playable roster. */
    bool IsPlayableRider(const FString& Name);
    FString DefaultRider();
}
