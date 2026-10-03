#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/DeveloperSettings.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "LiveLibrary.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;

/** What the bridge needs from the game, set in the game's DefaultGame.ini under [/Script/AtelierLive.AtelierLiveSettings]. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Atelier Live Bridge"))
class ATELIERLIVE_API UAtelierLiveSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    /** Material for runtime GLB props: parameters "Tint" (vector) and "Tex" (texture) receive the glTF base colour. */
    UPROPERTY(Config, EditAnywhere, Category = "Live") FSoftObjectPath PropMaterial;
    /** Folder of overlay files (<Name>.json), relative to the repository root. Every overlay loads at start. */
    UPROPERTY(Config, EditAnywhere, Category = "Live") FString OverlayFolder;
    /** Folder of the game's in-game Python helper module, relative to the repository root, and its module name. */
    UPROPERTY(Config, EditAnywhere, Category = "Live") FString PythonFolder;
    UPROPERTY(Config, EditAnywhere, Category = "Live") FString PythonModule;
    /** Loopback port; -liveport=N overrides it, -nolive turns the bridge off. */
    UPROPERTY(Config, EditAnywhere, Category = "Live") int32 Port = 8830;
};

/**
 * A prop added to the running game without a rebuild: a GLB loaded at runtime (engine glTF parser, static mesh built in
 * memory, base-colour textures on the configured material). Identified by a stable id so the agent can replace, move
 * or remove it; overlay files remember it across restarts.
 */
UCLASS()
class ATELIERLIVE_API ALiveProp : public AActor
{
    GENERATED_BODY()
public:
    ALiveProp();
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Live") FString Id;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Live") FString Source;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Live") FString Overlay;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Live") FString Collision;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Live") TObjectPtr<UStaticMeshComponent> Mesh;
};

/**
 * The game-independent verbs an agent uses on the running game, seen from Python as unreal.LiveLibrary.<snake_case>.
 * A game adds its own verbs in its own function library (for example unreal.<Game>Live).
 */
UCLASS()
class ATELIERLIVE_API ULiveLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category = "Live") static UWorld* GameWorld();
    UFUNCTION(BlueprintCallable, Category = "Live") static APawn* Player();
    UFUNCTION(BlueprintCallable, Category = "Live") static FTransform PlayerTransform();
    UFUNCTION(BlueprintCallable, Category = "Live") static FTransform CameraTransform();
    /** Where the camera looks: the first surface hit within MaxDistance cm (ignores the player), or the point at that distance. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FVector AimPoint(float MaxDistance = 3000.f);
    /** Ground height under (X, Y), tracing down from Z + 2000; returns the input Z when nothing is hit. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FVector GroundAt(FVector Location);
    /** Load a GLB (cached per file and modification time) and place it: Location is where its base (lowest point) sits.
     *  Collision: "box", "complex" (the mesh itself) or "none". Replaces a prop with the same id. */
    UFUNCTION(BlueprintCallable, Category = "Live") static ALiveProp* SpawnModel(const FString& Id, const FString& GlbPath, FVector Location, float Yaw = 0.f, float Scale = 1.f, const FString& Collision = TEXT("box"), const FString& Overlay = TEXT(""));
    UFUNCTION(BlueprintCallable, Category = "Live") static ALiveProp* FindProp(const FString& Id);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool RemoveProp(const FString& Id);
    UFUNCTION(BlueprintCallable, Category = "Live") static TArray<FString> PropIds();
    /** Size of a loaded model in cm (before Scale): X/Y footprint and Z height. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FVector ModelSize(const FString& GlbPath);
    /** Move the player to the ground under Location. A game can route this through its own travel (AtelierLive::SetTeleport). */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool TeleportPlayer(FVector Location, float Yaw);
    /** Feed a simulated input event to the player controller, as the platform would: Event "press", "release" or
     *  "axis" (send an axis every frame it moves, e.g. MouseX/MouseY deltas or Gamepad_RightX). Key is an FKey name. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool InputKey(const FString& Key, const FString& Event, float Value = 1.f);
    /** Filming: a fixed simulation step (Fps > 0; 0 returns to real time). */
    UFUNCTION(BlueprintCallable, Category = "Live") static void FixedStep(float Fps);
    /** Playing at real speed with a fixed frame time (Fps > 0; 0 returns to real time): the engine waits out each frame
     *  to 1/Fps and counts every frame as 1/Fps, however long it took, so a recorded session replays exactly. */
    UFUNCTION(BlueprintCallable, Category = "Live") static void FixedFrameRate(float Fps);
    /** A line of text for the player at the top of the screen (the game's HUD draws CurrentMessage). */
    UFUNCTION(BlueprintCallable, Category = "Live") static void Say(const FString& Text, float Seconds = 4.f);
    /** A screenshot of the game view (with the HUD) written to Path on the next frame. */
    UFUNCTION(BlueprintCallable, Category = "Live") static void Screenshot(const FString& Path);
    /** Overlays: <OverlayFolder>/<Name>.json lists props with their GLB, transform and collision. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SaveOverlay(const FString& Name);
    UFUNCTION(BlueprintCallable, Category = "Live") static int32 LoadOverlay(const FString& Name);
    /** The repository root (games/<game>/unreal is three levels down); relative paths in verbs resolve against it. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString LiveRoot();
    static FString Resolve(const FString& Path);
    /** The latest Say() line and its remaining time, for the HUD. */
    static bool CurrentMessage(FString& Text, float& Alpha);
};

namespace AtelierLive
{
    /** Start the bridge (HTTP on localhost), boot the game's Python helper and load every overlay. Call once the world
     *  and the player are ready. */
    ATELIERLIVE_API void Start(UWorld* World);
    /** Route TeleportPlayer through the game's own travel (so it can stow vehicles, settle the camera...). */
    ATELIERLIVE_API void SetTeleport(TFunction<bool(APawn*, const FVector&, float)> Teleport);
}
