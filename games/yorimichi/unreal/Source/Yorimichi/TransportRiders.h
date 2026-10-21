#pragma once
#include "CoreMinimal.h"
#include "Engine/EngineTypes.h"

class AActor;
class AWandererCharacter;
class UPrimitiveComponent;

/** Which passenger vehicle carries a player (AWandererCharacter::AboardVehicle). */
enum class ETransportVehicle : uint8 { None, Train, Ferry };

/** A player a passenger vehicle carries: the Belmonte train's coaches (ABelmonteTrainService) or the ferry
 *  (AFerryService). Each service keeps one per player and adds its own state (seats, tickets, boarding walks). */
struct YORIMICHI_API FTransportRider
{
    TWeakObjectPtr<AWandererCharacter> Character;
    /** The service's vehicle index the rider is aboard, or INDEX_NONE. */
    int32 Vehicle = INDEX_NONE;
    bool bAboard = false, bCameraLag = true, bTickOrdered = false;
    bool bCollisionOverridden = false;
    /** The capsule's responses before boarding a vehicle that holds its riders alone (FTransportRiders::SetAboard). */
    FCollisionResponseContainer Responses;
};

/**
 * The one rider mechanism of Yorimichi's passenger vehicles: the vehicles are moved before the characters each frame,
 * and a rider standing on a vehicle's floor is carried by it as the character's movement base (SetBase on the vehicle's
 * body); a rider off the floor for a moment (a stumble) is moved with the vehicle by the service offline, and online
 * the base's velocity carries them as for any moving floor. Aboard (AWandererCharacter::bTrainAboard, AboardVehicle)
 * the rider cannot jump or deploy a vehicle and the camera does not lag behind the moving floor.
 */
struct YORIMICHI_API FTransportRiders
{
    /** The service's actor ticks before the rider and the rider's movement (once per rider). */
    static void OrderTick(AActor& Service, FTransportRider& Rider);
    /** Aboard or off. bVehiclesOnly: aboard, only vehicle objects (ECC_Vehicle) and other pawns hold the rider, so
     *  ground the vehicle passes through cannot push them out (the train, whose line still clips hillsides). Returns
     *  false when the rider already was in that state. */
    static bool SetAboard(FTransportRider& Rider, bool bAboard, bool bVehiclesOnly, ETransportVehicle Kind);
    /** Carries a rider aboard Body, which stood at Previous last frame and has moved since when bMoved: on its floor the
     *  body becomes their movement base; offline, off the floor, they move with it (location, yaw and view). Service owns
     *  Body; a rider already based on one of Service's components is left to their base. */
    static void Carry(FTransportRider& Rider, const AActor& Service, UPrimitiveComponent* Body, const FTransform& Previous, bool bMoved);
};
