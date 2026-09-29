#include "SkateSettings.h"

USkateSettings::USkateSettings()
{
    // Common material names; a game lists its own in DefaultGame.ini (the list there replaces this one).
    auto Rule = [](const TCHAR* Keywords, float Drag) { FSkateSurfaceRule R; R.Keywords = Keywords; R.Drag = Drag; return R; };
    Surfaces = { Rule(TEXT("Grass,Ground,Moss,Flower,Leaf"), 20.f), Rule(TEXT("Water,Mud"), 25.f), Rule(TEXT("Sand,Dirt"), 12.f), Rule(TEXT("Rock,Gravel"), 4.f) };
}
