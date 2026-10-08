#pragma once
#include "CoreMinimal.h"
#include "IpNetDriver.h"
#include "JapanIpNetDriver.generated.h"

/** Private friends sessions listen only on the selected tailnet address. */
UCLASS(Transient, Config=Engine)
class YORIMICHI_API UJapanIpNetDriver : public UIpNetDriver
{
    GENERATED_BODY()
public:
    UJapanIpNetDriver(const FObjectInitializer& Initializer = FObjectInitializer::Get());
    virtual bool InitBase(bool bInitAsClient, FNetworkNotify* Notify, const FURL& URL,
        bool bReuseAddressAndPort, FString& Error) override;
    virtual bool InitListen(FNetworkNotify* Notify, FURL& URL, bool bReuseAddressAndPort, FString& Error) override;
protected:
    virtual FUniqueSocket CreateAndBindSocket(TSharedRef<FInternetAddr> BindAddr, int32 Port,
        bool bReuseAddressAndPort, int32 ReceiveBytes, int32 SendBytes, FString& Error) override;
private:
    FString PrivateAddress;
};
