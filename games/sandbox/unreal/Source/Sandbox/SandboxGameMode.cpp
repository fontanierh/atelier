#include "SandboxGameMode.h"
#include "SandboxCharacter.h"
#include "LiveLibrary.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"

ASandboxGameMode::ASandboxGameMode()
{
    DefaultPawnClass = ASandboxCharacter::StaticClass();
    HUDClass = ASandboxHUD::StaticClass();
}

void ASandboxHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas) return;
    UFont* Font = GEngine->GetMediumFont();
    DrawText(TEXT("Sandbox   WASD / left stick move   mouse / right stick look   Space / A jump"), FLinearColor(1, 1, 1, .8f), 24, Canvas->SizeY - 44, Font, 1.f);
    FString Line; float Alpha = 0.f;
    if (ULiveLibrary::CurrentMessage(Line, Alpha))
    {
        float W = 0, H = 0; GetTextSize(Line, W, H, Font, 1.4f);
        DrawText(Line, FLinearColor(1, .93f, .75f, Alpha), (Canvas->SizeX - W) * .5f, 40, Font, 1.4f);
    }
}
