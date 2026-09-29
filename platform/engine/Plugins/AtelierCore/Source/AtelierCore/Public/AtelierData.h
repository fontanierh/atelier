#pragma once

#include "Misc/Paths.h"

/** Runtime data a game's build stages into Content/Data (layouts, maps, per-character runtime files). Packaged as loose
 *  files: add `+DirectoriesToAlwaysStageAsNonUFS=(Path="Data")` to the game's DefaultGame.ini. */
inline FString AtelierDataPath(const FString& Relative)
{
    return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Data") / Relative);
}
