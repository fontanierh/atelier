#pragma once
#include "CoreMinimal.h"
class AWandererCharacter;
class FJsonObject;
namespace JapanVehicleQASite
{
    /** Find a flat approach to existing authored collision. Never spawns or changes geometry. */
    bool Crash(AWandererCharacter* Rider,FVector& Start,float& Yaw,TSharedPtr<FJsonObject>& Evidence);
}
