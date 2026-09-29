#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "SandboxGameMode.generated.h"

UCLASS()
class SANDBOX_API ASandboxGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    ASandboxGameMode();
};

/** The controls, and the live bridge's line of text (ULiveLibrary::Say) at the top. */
UCLASS()
class SANDBOX_API ASandboxHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};
