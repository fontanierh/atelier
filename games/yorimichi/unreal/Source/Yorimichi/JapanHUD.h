#pragma once
#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "JapanHUD.generated.h"

/** Loading screen (solid backdrop, title, progress bar while shaders compile and the world warms up) and the control hints. */
UCLASS()
class YORIMICHI_API AJapanHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
private:
    double LastFrameTime = 0., FrameWindowTime = 0.;
    int32 FrameWindowCount = 0;
    float DisplayedFrameRate = 0.f;
    double NextControllerCheck = 0.;
    int32 ControllerStyle = 0;
};
