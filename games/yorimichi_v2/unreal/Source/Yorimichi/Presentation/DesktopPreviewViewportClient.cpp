#include "DesktopPreviewViewportClient.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Slate/SceneViewport.h"
#include "Widgets/SViewport.h"
#include "Widgets/SWindow.h"

namespace
{
bool ShouldManageNative1440Target()
{
    const TCHAR* CmdLine = FCommandLine::Get();
    if (GIsEditor || IsRunningCommandlet() || !FApp::CanEverRender()) return false;
    // Offscreen test/parity sessions (-RenderOffScreen) render directly into Slate's offscreen texture at their requested -resx/-resy.
    if (FParse::Param(CmdLine, TEXT("RenderOffScreen"))) return false;
    if (FParse::Param(CmdLine, TEXT("desktopnative1440"))) return true;
    int32 CliX = 0, CliY = 0;
    FString CliRes;
    const bool bHasX = FParse::Value(CmdLine, TEXT("ResX="), CliX);
    const bool bHasY = FParse::Value(CmdLine, TEXT("ResY="), CliY);
    const bool bHasRes = FParse::Value(CmdLine, TEXT("Res="), CliRes);
    if (!bHasX && !bHasY && !bHasRes) return true;   // Bare packaged YorimichiV2.app launch: default to 1440p aspect-matched target.
    if (FParse::Param(CmdLine, TEXT("fullscreen")) && (!bHasY || CliY == 1440)) return true;
    const int32 TargetY = bHasY ? CliY : (bHasX ? FMath::RoundToInt(double(CliX) * 9.0 / 16.0) : 0);
    // Honor explicit non-1440p windowed launches (e.g. [play.megapark] 1920x1080 or custom 1280x720).
    return TargetY == 1440;
}
}

TSharedRef<FSceneViewport> UDesktopPreviewViewportClient::CreateViewport(TSharedPtr<SViewport> InViewportWidget)
{
    bManage1440Target = ShouldManageNative1440Target();
    if (bManage1440Target && InViewportWidget.IsValid())
    {
        InViewportWidget->SetRenderDirectlyToWindow(false);
        UE_LOG(LogTemp, Display, TEXT("DESKTOP PREVIEW separate_scene_target=1"));
    }
    TSharedRef<FSceneViewport> SceneViewport = Super::CreateViewport(InViewportWidget);
    if (bManage1440Target) RefreshNative1440Target(true);
    return SceneViewport;
}

void UDesktopPreviewViewportClient::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);
    if (bManage1440Target) RefreshNative1440Target(false);
}

void UDesktopPreviewViewportClient::RefreshNative1440Target(bool bForce)
{
    if (!bManage1440Target) return;
    FSceneViewport* SceneViewport = GetGameViewport();
    const TSharedPtr<SWindow> Window = GetWindow();
    if (!SceneViewport || !Window.IsValid()) return;
    const FVector2D ClientSizeF = Window->GetClientSizeInScreen();
    const FIntPoint ClientSize(FMath::RoundToInt(ClientSizeF.X), FMath::RoundToInt(ClientSizeF.Y));
    if (ClientSize.X <= 0 || ClientSize.Y <= 0) return;
    const int32 Mode = int32(Window->GetWindowMode());
    if (!bForce && ClientSize == LastWindowClientSize && Mode == LastWindowMode) return;
    LastWindowClientSize = ClientSize;
    LastWindowMode = Mode;
    const double Aspect = double(ClientSize.X) / double(FMath::Max(1, ClientSize.Y));
    const uint32 Width = uint32(FMath::Max(2, FMath::RoundToInt(1440.0 * Aspect / 2.0) * 2));
    SceneViewport->SetFixedViewportSize(Width, 1440);
    UE_LOG(LogTemp, Display, TEXT("DESKTOP PREVIEW viewport=%ux1440 fullscreen=%d window=%dx%d window_aspect=%.6f"),
        Width, SceneViewport->IsFullscreen() ? 1 : 0, ClientSize.X, ClientSize.Y, Aspect);
}
