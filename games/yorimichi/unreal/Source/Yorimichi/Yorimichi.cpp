#include "Yorimichi.h"
#include "GameFramework/InputSettings.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Modules/ModuleManager.h"

// An offscreen run (-RenderOffscreen: the captures, films and QA runs driven over the live bridge) has no window to
// play in, so it never takes the mouse: no capture at launch and no lock to the hidden viewport, and the cursor stays
// free on the whole screen while it renders. AWandererCharacter::SetMouseReleased keeps it so once the player spawns.
class FYorimichiModule : public FDefaultGameModuleImpl
{
    virtual void StartupModule() override
    {
        if (!FParse::Param(FCommandLine::Get(), TEXT("RenderOffscreen"))) return;
        UInputSettings* Input = GetMutableDefault<UInputSettings>();
        Input->bCaptureMouseOnLaunch = false;
        Input->DefaultViewportMouseCaptureMode = EMouseCaptureMode::NoCapture;
        Input->DefaultViewportMouseLockMode = EMouseLockMode::DoNotLock;
    }
};

IMPLEMENT_PRIMARY_GAME_MODULE(FYorimichiModule, Yorimichi, "Yorimichi");
