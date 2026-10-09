#pragma once
#include "CoreMinimal.h"
#include <memory>
#include <string>
namespace atelier::skate { struct AnimationSource; }
class USkateMotionData;
// Unreal objects are resolved on the game thread; only immutable native values cross to the simulation worker.
bool LoadSkateMotion(const FSoftObjectPath& Path, std::shared_ptr<const atelier::skate::AnimationSource>& Out, FString& Error);
bool DecodeSkateMotion(const USkateMotionData& Data, std::shared_ptr<const atelier::skate::AnimationSource>& Out, std::string& Error);
