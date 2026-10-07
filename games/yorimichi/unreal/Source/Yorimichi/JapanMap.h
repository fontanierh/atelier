#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "Styling/SlateBrush.h"
#include "JapanMap.generated.h"

class AWandererCharacter;
class UTexture2D;
class SWidget;
class SEditableTextBox;
class FJapanMarkers;

/** A place the player can travel to from the map. Positions are Unreal centimetres, yaw is Unreal degrees. */
struct FJapanMapZone
{
    FString Key, Name, Hint;
    FVector Location = FVector::ZeroVector;
    float Yaw = 0.f;
};

/** The world map (Content/Data/map: the painted sheet plus map.json with its bounds and the teleport zones).
 *  Desktop: M (or the controller's View / Touchpad) opens a full-screen overlay showing the whole world, the player's
 *  position and heading, and the zones as pins; clicking a pin travels there. With a controller, the left stick or d-pad
 *  picks a pin and the bottom button travels. Holding View instead opens the saved-places bar over the game, so a
 *  controller can save, choose, return to and delete markers without the map or a keyboard. Phones get the same data
 *  over the stream and draw the map themselves. */
UCLASS()
class YORIMICHI_API UJapanMap : public UObject
{
    GENERATED_BODY()
public:
    void Initialize(AWandererCharacter* Pawn);
    bool IsLoaded() const { return bLoaded; }
    bool IsOpen() const { return Widget.IsValid(); }
    void Open();
    /** Closes the map and the saved-places bar. */
    void Close();
    void OpenMarkerBar();
    void CloseMarkerBar();
    UFUNCTION(BlueprintPure, Category = "Map") bool IsMarkerBarOpen() const { return MarkerBar.IsValid(); }
    void Toggle() { if (IsOpen()) Close(); else Open(); }
    const TArray<FJapanMapZone>& GetZones() const;
    /** Save a new place on solid ground, using the next unused Marker N name. */
    UFUNCTION(BlueprintCallable, Category = "Map") bool SetMarker();
    UFUNCTION(BlueprintCallable, Category = "Map") bool SaveMarker(const FString& Name);
    /** Normal travel to the selected saved floor and heading; refuses unavailable or obstructed ground. */
    UFUNCTION(BlueprintCallable, Category = "Map") bool ReturnToMarker();
    UFUNCTION(BlueprintPure, Category = "Map") bool HasMarker() const;
    UFUNCTION(BlueprintPure, Category = "Map") FTransform GetMarkerTransform() const;
    UFUNCTION(BlueprintPure, Category = "Map") TArray<FString> GetMarkerKeys() const;
    UFUNCTION(BlueprintPure, Category = "Map") FString GetMarkerName() const;
    UFUNCTION(BlueprintPure, Category = "Map") FString GetSelectedMarkerKey() const;
    UFUNCTION(BlueprintCallable, Category = "Map") bool SelectMarker(const FString& Key);
    UFUNCTION(BlueprintCallable, Category = "Map") bool RenameMarker(const FString& Name);
    UFUNCTION(BlueprintCallable, Category = "Map") bool DeleteMarker();
    /** Review the real focused Slate text path, including gameplay-key leakage; requires the map already open. */
    UFUNCTION(BlueprintCallable, Category = "Map|Review") FString ReviewMarkerNameInput(const FString& Text);
    UFUNCTION(BlueprintCallable, Category = "Map|Review") bool ReviewCommitMarkerName();
    UFUNCTION(BlueprintPure, Category = "Map|Review") bool IsMarkerReviewOnVehicle() const;
    /** Review the bar's real focused Slate key path: one press and release of Key; requires the bar already open. */
    UFUNCTION(BlueprintCallable, Category = "Map|Review") bool ReviewMarkerBarKey(const FString& Key);
    /** One key press or release through Slate's normal routing (the focused widget, else the game viewport). */
    UFUNCTION(BlueprintCallable, Category = "Map|Review") bool ReviewSlateKey(const FString& Key, bool bPressed);
    UFUNCTION(BlueprintPure, Category = "Map") bool IsMapOpen() const { return IsOpen(); }
    void CycleMarker(int32 Direction);
    bool IsEditingMarkerName() const;
    const FJapanMapZone* FindZone(const FString& Key) const;
    UFUNCTION(BlueprintCallable, Category = "Map") bool TeleportToZone(const FString& Key);
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
    mutable TArray<FJapanMapZone> Zones;
    TArray<FVector2D> ProjectionX,ProjectionY;
    FBox2D Bounds = FBox2D(FVector2D(-300, -300), FVector2D(300, 300));
    TSharedPtr<SWidget> Widget, MarkerBar;
    FString ImageFile;
    TSharedPtr<SEditableTextBox> MarkerName;
    FJapanMarkers* MarkerStore() const;
    bool MarkerResult(bool Result);
    bool bLoaded = false;
};
