#pragma once

#include "CoreMinimal.h"

class FJsonObject;

/** The keys and cell pieces of ABelmonteRegion's runtime.json scenery groups (Belmonte and Brine Cove). Shared by the
 *  runtime (ABelmonteRegion::Spawn) and the saving migration (UV2Migration::MigrateRegionGroups), so both skip and save
 *  the same groups. */
namespace V2MigrationTowns
{
    /** Meters of one plant piece cell (a 128 m square of the world). */
    constexpr double PieceCellM = 128.0;

    /** Every group's key, in runtime.json order: its mesh name, unless another group of the file shares that name, then
     *  "<mesh>#<index>" (the index in the groups array). A plain mesh name keeps the key saved maps already hold. */
    TArray<FString> GroupKeys(const TSharedPtr<FJsonObject>& Data);

    /** A cell piece of a plant group: "<key>@<x>_<y>", the instances in that 128 m cell of the world. */
    FString PieceKey(const FString& Key, int32 CellX, int32 CellY);

    /** Splits a piece key into its group key and cell. False for a whole group's key. */
    bool ParsePieceKey(const FString& Key, FString& OutKey, int32& OutCellX, int32& OutCellY);

    /** The cell of a placement relative to its region's origin (cm): floor of the world's metres over PieceCellM, with
     *  y north as ABelmonteRegion::InClearance reads it (world y = -Y). */
    void CellOf(const FVector& OriginCm, const FTransform& Placement, int32& OutCellX, int32& OutCellY);

    /** The gondola's clearance data, the input of ABelmonteRegion::InClearance. */
    TSharedPtr<FJsonObject> GondolaClearance();
}
