#pragma once
#include "CoreMinimal.h"
class AWandererCharacter;
namespace JapanSoundBankNetworkQA
{
    // Called only for the existing gameplay driver's locally controlled skating pawn.
    bool Tick(AWandererCharacter* Local, FString& Error);
}
