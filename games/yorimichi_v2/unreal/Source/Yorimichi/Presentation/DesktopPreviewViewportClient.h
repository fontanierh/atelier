#pragma once

#include "Engine/GameViewportClient.h"
#include "DesktopPreviewViewportClient.generated.h"

// Keep the game render target independent of macOS's scaled Retina window drawable,
// defaulting on-screen play to an aspect-matched 1440p scene target while honoring
// explicit offscreen/CLI capture resolutions (-RenderOffScreen, -resx/-resy).
UCLASS()
class YORIMICHI_API UDesktopPreviewViewportClient : public UGameViewportClient
{
    GENERATED_BODY()
public:
    virtual TSharedRef<FSceneViewport> CreateViewport(TSharedPtr<SViewport> InViewportWidget) override;
    virtual void Tick(float DeltaTime) override;
    void RefreshNative1440Target(bool bForce = false);
    bool IsManaging1440Target() const { return bManage1440Target; }
private:
    bool bManage1440Target = false;
    FIntPoint ExplicitFixedSize = FIntPoint::ZeroValue;
    FIntPoint LastWindowClientSize = FIntPoint::ZeroValue;
    int32 LastWindowMode = -1;
};
