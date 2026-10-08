#pragma once
#include "CoreMinimal.h"
class AWandererCharacter;
class FJsonObject;
namespace JapanVehicleQASite
{
    /** Certify an existing infield disk for the bounded motion route; no geometry mutation. */
    bool Circuit(AWandererCharacter* Rider,bool Guest,FVector& Start,TSharedPtr<FJsonObject>& Evidence);
    /** Find a flat approach to existing authored collision. Never spawns or changes geometry. */
    bool Crash(AWandererCharacter* Rider,FVector& Start,float& Yaw,TSharedPtr<FJsonObject>& Evidence);
}
