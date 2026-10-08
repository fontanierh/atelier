#pragma once

#include "CoreMinimal.h"

/** A game's saved settings: one key=value per line in Saved/settings.txt, or in the file -preferencesfile= names.
 *  `atelier play GAME --set "a=1;b=2"` starts the game with -set=a=1;b=2, which overrides those keys for that run. What
 *  the keys mean is the game's. */
namespace AtelierSettings
{
    /** The settings file: -preferencesfile= when given, else Saved/settings.txt. */
    ATELIERCORE_API FString FilePath();
    /** The keys and values of a settings file, trimmed; empty when the file is missing. */
    ATELIERCORE_API TMap<FString, FString> ReadFile(const FString& Path);
    /** This launch's -set= overrides. */
    ATELIERCORE_API TMap<FString, FString> Overrides();
    /** Writes the values sorted by key into a sibling file renamed over the old one, so a failed write never truncates
     *  the previous settings. False (the old file kept) when it could not. */
    ATELIERCORE_API bool WriteFile(const FString& Path, const TMap<FString, FString>& Values);
}
