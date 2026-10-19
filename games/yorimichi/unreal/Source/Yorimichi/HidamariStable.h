#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "HidamariStable.generated.h"

class UStaticMeshComponent;

/** One stall of the stable (world/regions/hidamari_stable/layout.py), in Unreal cm and degrees. */
struct FHidamariStall
{
    FString Id;                       // N1..N5, S1..S5, west to east
    FTransform Plaque;                // the name plate's centre, X along its outward normal
    FVector2D PlaqueSize = FVector2D::ZeroVector;   // cm
    FTransform Horse;                 // where its horse stands, facing the door
    TObjectPtr<UStaticMeshComponent> Door = nullptr;
    FVector DoorClosed = FVector::ZeroVector;       // the closed leaf's world location (cm)
    FVector DoorSlide = FVector::ZeroVector;        // the leaf's travel when open (cm)
};

/**
 * Henry's racing stable at Hidamari (world/regions/hidamari_stable/README.md), east of the hippodrome. Places the
 * imported meshes (Content/Data/hidamari_stable/stable.json, import_hidamari_stable.py) round the site origin: the
 * barn, gate, yard and paddock, the walkable pad and path, and a sliding leaf at every stall and room door. Keeps the
 * anchors the racing game uses later: stalls (name plates, horse spots), the sign, the transfers board, NPC spots.
 */
UCLASS()
class YORIMICHI_API AHidamariStable : public AActor
{
    GENERATED_BODY()
public:
    /** Committed switch paired with ENABLED in world/regions/hidamari_stable/layout.py. */
    static constexpr bool bEnabled = false;
    bool bGameplayReady = false;
    AHidamariStable();
    /** The stable described by Path (stable.json); null when the file is missing (the step is optional) or nothing
     *  could be placed. */
    static AHidamariStable* Spawn(UWorld* World, const FString& Path);
    static AHidamariStable* Find(const UObject* WorldContext);

    TArray<FHidamariStall> Stalls;
    TMap<FString, TObjectPtr<UStaticMeshComponent>> RoomDoors;
    TMap<FString, FVector> RoomDoorClosed, RoomDoorSlide;
    FTransform Sign, NoticeBoard, Arrival;
    TMap<FString, FTransform> NpcSpots;

    /** Slides a stall's door open (Alpha 1) or closed (0). */
    void SetDoorOpen(int32 Stall, float Alpha);
    /** Slides a room's door ('tack' or 'office') open (Alpha 1) or closed (0). */
    void SetRoomDoorOpen(const FString& Room, float Alpha);

private:
    UPROPERTY() TObjectPtr<USceneComponent> Root;
    FVector Origin = FVector::ZeroVector;   // Blender metres
    FVector World(const FVector& Local) const { return FVector((Origin.X + Local.X) * 100., -(Origin.Y + Local.Y) * 100., (Origin.Z + Local.Z) * 100.); }
    bool Initialize(const FString& Path);
};
