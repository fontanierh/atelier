#pragma once

#include "Misc/Paths.h"

/** Runtime data staged by `atelier build` into Content/Data: the world layout (world.json, heightmap.bin), the city
 *  (hidamari/city.json), the skate pier (skatepark/park.json), the map (map/), the desktop city tiles
 *  (city_surface_tiles/) and per-character runtime files (characters/<id>/). Packaged as loose files
 *  (DefaultGame.ini, DirectoriesToAlwaysStageAsNonUFS). The prototype read the same files from japan/out. */
inline FString YoriDataPath(const FString& Relative)
{
    return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Data") / Relative);
}
