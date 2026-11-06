#pragma once
#include "CoreMinimal.h"

class AWandererCharacter;

/** One way back up Crater Park (docs/CRATERPARK.md, "Tower"): a line's roll-in crest on the tower deck, island cm,
 *  and the Unreal yaw facing down the line. */
struct FCraterParkStart
{
    FString Key, Name;
    FVector Ground = FVector::ZeroVector;
    float Yaw = 0.f;
};

/** The tower starts, from craterpark/park.json: one per designed line (`lines`, ground-checked by the build,
 *  world/regions/craterpark/v2/spawns.py), else the park's single `spawn` (the r4 drop-in). The menu's Crater Park
 *  tower buttons, F7 and the map's Crater Park stop all travel through Return. */
namespace CraterParkTower
{
    /** Hoist portal lift platform at the east foot of p183 (world (1326.9, 2494.0, 759.64) m) and 6x6 m rim landing. */
    inline const FVector HoistPortalGround(132690.f, -249400.f, 75964.f);
    inline const FVector HoistLandingGround(133150.f, -249400.f, 75960.f);
    inline constexpr float HoistInteractRadiusCm = 250.f;
    inline constexpr float HoistDeckZCm = 85800.f;

    /** Read once; empty when the island has no Crater Park data. */
    const TArray<FCraterParkStart>& Starts();
    /** Whether the starts are the generated park's lines (not the fallback drop-in). */
    bool HasLines();
    /** The start F7 uses: the last one chosen this session, the first (the hero line) by default. */
    int32 LastStart();
    /** Put Pawn on start Index, on foot and standing still, facing down its line. Refuses (with a message) unless a
     *  trace from 2 m over the start meets the ground within 50 cm of it: never a floating or buried start. */
    bool Return(AWandererCharacter* Pawn, int32 Index);
    /** Put Pawn back on the 6x6 m rim landing at the east foot of the tower, with ground check and camera fade. */
    bool ReturnDown(AWandererCharacter* Pawn);
    /** True when Pawn is on foot within 2.5 m of the base hoist portal ("Ride up"). */
    bool CanRideUp(const AWandererCharacter* Pawn);
    /** True when Pawn is on foot on the p183 tower deck within 2.5 m of a deck start ("Ride down"). */
    bool CanRideDown(const AWandererCharacter* Pawn);
    /** HUD prompt ("Ride up" or "Ride down") when within 2.5 m of the base hoist portal or deck start. */
    FString Hint(const AWandererCharacter* Pawn);
    /** Handle E / D-pad Down interaction at the hoist portal ("Ride up") or tower deck ("Ride down"). */
    bool TryInteract(AWandererCharacter* Pawn);
}
