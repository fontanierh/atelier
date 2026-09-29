#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "Styling/SlateBrush.h"
#include "JapanMap.generated.h"

class AWandererCharacter;
class UTexture2D;
class SWidget;

/** A place the player can travel to from the map. Positions are Unreal centimetres, yaw is Unreal degrees. */
struct FJapanMapZone
{
    FString Key, Name, Hint;
    FVector Location = FVector::ZeroVector;
    float Yaw = 0.f;
};

/** The world map (Content/Data/map: the painted sheet plus map.json with its bounds and the teleport zones).
 *  Desktop: M opens a full-screen overlay showing the whole world, the player's position and heading, and the zones
 *  as pins; clicking a pin travels there. Phones get the same data over the stream and draw the map themselves. */
UCLASS()
class YORIMICHI_API UJapanMap : public UObject
{
    GENERATED_BODY()
public:
    void Initialize(AWandererCharacter* Pawn);
    bool IsLoaded() const { return bLoaded; }
    bool IsOpen() const { return Widget.IsValid(); }
    void Open();
    void Close();
    void Toggle() { if (IsOpen()) Close(); else Open(); }
    const TArray<FJapanMapZone>& GetZones() const { return Zones; }
    const FJapanMapZone* FindZone(const FString& Key) const;
    bool TeleportToZone(const FString& Key);
    /** Blender-metre bounds of the sheet: min x, min y, max x, max y (north up). */
    const FBox2D& GetBounds() const { return Bounds; }
    /** Unreal position -> sheet uv (0..1, top-left origin). */
    FVector2D ToSheet(const FVector& Location) const;
    /** Unreal yaw -> screen angle in degrees, clockwise from east, on the north-up sheet. */
    static float SheetHeading(float UEYaw) { return UEYaw; }
    const FSlateBrush* GetBrush() const { return &Brush; }
    AWandererCharacter* GetOwnerPawn() const { return Owner; }
    FString GetImageFile() const { return ImageFile; }
    const TArray<FVector2D>& GetProjectionX() const { return ProjectionX; }
    const TArray<FVector2D>& GetProjectionY() const { return ProjectionY; }
private:
    UPROPERTY() TObjectPtr<AWandererCharacter> Owner;
    UPROPERTY() TObjectPtr<UTexture2D> Texture;
    FSlateBrush Brush;
    TArray<FJapanMapZone> Zones;
    TArray<FVector2D> ProjectionX,ProjectionY;
    FBox2D Bounds = FBox2D(FVector2D(-300, -300), FVector2D(300, 300));
    TSharedPtr<SWidget> Widget;
    FString ImageFile;
    bool bLoaded = false;
};
