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
class FJapanAtlasNames;
class FJsonObject;

struct FJapanAtlasFrame
{
    FString Key, Name, ImagePath;
    FBox2D Bounds;
    FVector2D LabelPosition = FVector2D::ZeroVector;
    TArray<FVector2D> Polygon;
    FLinearColor Colour = FLinearColor(.65f,.6f,.4f);
    mutable FSlateBrush Brush;
};

struct FJapanAtlasLandmark
{
    FString Key, Name, Region, Category;
    FVector Location = FVector::ZeroVector;
    bool bEditable = false;
};

struct FJapanAtlasTarget
{
    FString Key, Name, Hint, Category, Region;
    FVector Location = FVector::ZeroVector;
    bool bTravel = false, bEditable = false;
    FVector Link = FVector::ZeroVector;
};

struct FJapanAtlasAirStop
{
    FString Key, Name;
    FVector Location = FVector::ZeroVector;
};

struct FJapanAtlasAirLeg
{
    FString From, To;
    double Seconds = 0., Height = 0.;
};

struct FJapanAtlasAirRoute
{
    TArray<FString> Line;
    TArray<FJapanAtlasAirStop> Stops;
    TArray<FJapanAtlasAirLeg> Legs;
    FString Note;
};

/** A place the player can travel to from the map. Positions are Unreal centimetres, yaw is Unreal degrees. */
struct FJapanMapZone
{
    FString Key, Name, Hint;
    FVector Location = FVector::ZeroVector;
    float Yaw = 0.f;
    /** Landing trace height above Location (cm); indoor stops start below their roof. */
    float Above = 2500.f;
};

/** The world map (Content/Data/map: the painted sheet plus map.json with its bounds and the teleport zones).
 *  Desktop: M (or the controller's View / Touchpad) opens a full-screen overlay showing the whole world, the player's
 *  position and heading, and the zones as pins; clicking a pin travels there. With a controller, the left stick or d-pad
 *  picks a pin and the bottom button travels. Holding View instead opens the saved-places bar over the game, so a
 *  controller can save, choose, return to and delete markers without the map or a keyboard. */
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
    /** Send an actual Slate gamepad axis event to the focused map widget. */
    UFUNCTION(BlueprintCallable, Category = "Map|Review") bool ReviewSlateAnalog(const FString& Key, float Value);
    /** Read the real rendered controller selection, zoom and pan for native acceptance. */
    UFUNCTION(BlueprintPure, Category = "Map|Review") FString ReviewAtlasController() const;
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
    const FSlateBrush* GetBrush() const;
    AWandererCharacter* GetOwnerPawn() const { return Owner; }
    FString GetImageFile() const { return ImageFile; }
    const TArray<FVector2D>& GetProjectionX() const { return ProjectionX; }
    const TArray<FVector2D>& GetProjectionY() const { return ProjectionY; }
    const TArray<FJapanAtlasFrame>& GetAtlasRegions() const { return AtlasRegions; }
    const FJapanAtlasFrame* GetAtlasFrame(const FString& Key) const;
    const FSlateBrush* GetAtlasBrush() const;
    FVector2D ToAtlas(const FVector& Location, const FString& Region = FString()) const;
    TArray<FJapanAtlasTarget> GetAtlasTargets() const;
    const FJapanAtlasAirRoute& GetAtlasAirRoute() const { return AirRoute; }
    FString RegionForLocation(const FVector& Location) const;
    FString RegionForZone(const FJapanMapZone& Zone) const;
    TSharedPtr<FJsonObject> GetAtlasJson() const;
    UFUNCTION(BlueprintPure, Category="Map|Atlas") FString GetAtlasRegion() const { return ActiveRegion; }
    UFUNCTION(BlueprintPure, Category="Map|Atlas") FString GetAtlasTitle() const;
    UFUNCTION(BlueprintPure, Category="Map|Atlas") TArray<FString> GetAtlasRegionKeys() const;
    UFUNCTION(BlueprintCallable, Category="Map|Atlas") bool SelectAtlasRegion(const FString& Key);
    UFUNCTION(BlueprintCallable, Category="Map|Atlas") void AtlasBack();
    UFUNCTION(BlueprintCallable, Category="Map|Atlas") void AtlasCurrentRegion();
    UFUNCTION(BlueprintPure, Category="Map|Atlas") TArray<FString> GetAtlasZoneKeys(const FString& Region) const;
    UFUNCTION(BlueprintPure, Category="Map|Atlas") FString GetStableName(const FString& Key) const;
    UFUNCTION(BlueprintPure, Category="Map|Atlas") FString GetAtlasError() const;
    UFUNCTION(BlueprintPure, Category="Map|Atlas") FString ReviewAtlasAirRoute() const;
    UFUNCTION(BlueprintCallable, Category="Map|Atlas") bool RenameStable(const FString& Key, const FString& Name);
    UFUNCTION(BlueprintCallable, Category="Map|Atlas") bool ResetStableName(const FString& Key);
    UFUNCTION(BlueprintCallable, Category="Map|Atlas") void SelectStable(const FString& Key);
    UFUNCTION(BlueprintPure, Category="Map|Atlas") FString GetSelectedStable() const { return SelectedStable; }
    bool IsEditingMapText() const;
    FString SearchText;
    int32 AtlasRevision = 0;
private:
    friend class SJapanAtlas;

    friend class FRemoteVehiclePresentationTest;
    void RefreshPlayerZones() const;
    UPROPERTY() TObjectPtr<AWandererCharacter> Owner;
    UPROPERTY() mutable TObjectPtr<UTexture2D> Texture;
    UPROPERTY() mutable TArray<TObjectPtr<UTexture2D>> AtlasTextures;
    TArray<FJapanAtlasFrame> AtlasRegions;
    FJapanAtlasFrame WorldFrame;
    TArray<FJapanAtlasLandmark> AtlasLandmarks;
    FJapanAtlasAirRoute AirRoute;
    TSharedPtr<FJsonObject> AtlasData;
    FString ActiveRegion = TEXT("world"), SelectedStable;
    mutable FSlateBrush Brush;
    mutable TArray<FJapanMapZone> Zones;
    TArray<FVector2D> ProjectionX,ProjectionY;
    FBox2D Bounds = FBox2D(FVector2D(-300, -300), FVector2D(300, 300));
    TSharedPtr<SWidget> Widget, MarkerBar;
    FString ImageFile;
    FIntPoint SheetImageSize = FIntPoint::ZeroValue;
    TSharedPtr<SEditableTextBox> MarkerName;
    TSharedPtr<SEditableTextBox> AtlasSearch, StableName;
    FJapanMarkers* MarkerStore() const;
    FJapanAtlasNames* AtlasNameStore() const;
    void InitializeAtlas(const TSharedPtr<FJsonObject>& Root, const FString& Dir);
    UTexture2D* EnsureSheetTexture() const;
    UTexture2D* EnsureFrameTexture(const FJapanAtlasFrame& Frame) const;
    bool MarkerResult(bool Result);
    static bool ReadPngHeaderSize(const FString& Path, FIntPoint& OutSize);
    bool bLoaded = false;
};
