#include "DesktopPreviewViewportClient.h"
#include "Widgets/SViewport.h"

TSharedRef<FSceneViewport> UDesktopPreviewViewportClient::CreateViewport(TSharedPtr<SViewport> InViewportWidget)
{
    if (InViewportWidget.IsValid()) InViewportWidget->SetRenderDirectlyToWindow(false);
    UE_LOG(LogTemp,Display,TEXT("DESKTOP PREVIEW separate_scene_target=1"));
    return Super::CreateViewport(InViewportWidget);
}
