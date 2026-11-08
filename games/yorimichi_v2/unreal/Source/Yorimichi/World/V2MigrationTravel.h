#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "V2MigrationTravel.generated.h"

/** The one-time editor migration of the transport routes' static scenery (docs/YORIMICHI_V2_PLAN.md §6; the route objects
 *  of tools/migrate/objects.py): the railway track, the ferry terminals and the gondola's static stations and pylons are saved
 *  as one AV2ScenePatch per unit, each component built by the runtime service's own builder (BelmonteTrack, FerryService,
 *  GondolaService), and the manifest lists each saved entry as "<tag>:<name>" so the runtime skips exactly those. Moving
 *  parts (cabins, ropes, ships, brows) and the services' logic stay runtime. */
UCLASS()
class YORIMICHI_API UV2MigrationTravel : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Saves the railway's pieces and instanced groups (DataFile, belmonte_track/track.json; ABelmonteTrack::Initialize reads it).
     *  Names[i] is a piece's name, or "<mesh>#<key>" for an instanced group (ABelmonteTrack::GroupName), and Units[i] the
     *  object it joins. A unit already saved (V2Id: region, tag, unit) is kept as it is. Returns the number of actors created,
     *  or -1 with Error set; nothing changes on an error. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateRailwayPieces(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Names, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error);
    /** Saves ferry terminals (DataFile, ferry/service/service.json; AFerryService::Initialize reads it): Names[i] is a terminal's
     *  key, Units[i] the object it joins. Each terminal's static parts and hidden collision are built by AFerryService::MakeTerminal.
     *  Same contract as MigrateRailwayPieces. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateFerryTerminals(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Names, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error);
    /** Saves gondola static entries (DataFile, gondola/runtime.json; AGondolaService::Initialize reads its `static` list): Names[i]
     *  is an entry's name, Units[i] the object it joins, built by AGondolaService::MakeStatic. Same contract as MigrateRailwayPieces. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateGondolaStatics(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Names, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error);
};
