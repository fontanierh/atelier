#pragma once

#include "Engine/GameViewportClient.h"
#include "DesktopPreviewViewportClient.generated.h"

// Selected only by the desktop preview's per-process Engine config override.
// Keep the game render target independent of macOS's scaled window drawable.
UCLASS()
class UDesktopPreviewViewportClient : public UGameViewportClient
{
    GENERATED_BODY()
public:
    virtual TSharedRef<FSceneViewport> CreateViewport(TSharedPtr<SViewport> InViewportWidget) override;
};
