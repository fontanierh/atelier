#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "JapanLive.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;

/**
 * A prop added to the running game without a rebuild: a GLB loaded at runtime (engine glTF parser, static mesh
 * built in memory, base-colour textures on the world's own painterly material). Identified by a stable id so the
 * agent can replace, move or remove it; the overlay files under games/yorimichi/live/overlays remember it across restarts.
 */
UCLASS()
class YORIMICHI_API ALiveProp : public AActor
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
 * The verbs the agent (through the live bridge's Python) uses on the running game. Python sees them as
 * unreal.LiveLibrary.<snake_case>. Everything works on the game world; nothing here runs in ordinary play unless
 * the bridge or an overlay asks for it.
 */
UCLASS()
class YORIMICHI_API ULiveLibrary : public UBlueprintFunctionLibrary
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
    UFUNCTION(BlueprintCallable, Category = "Live") static bool TeleportPlayer(FVector Location, float Yaw);
    /** Move the player as if the stick were held: Intent is camera-relative (Y forward, X right), Gait 0 walk, 1 run, 2 sprint.
     *  Zero intent stops. Any player input takes over again. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool Drive(FVector2D Intent, int32 Gait = 1);
    /** Press a button through the character's input handler: "jump", "jump_release" or "roll". */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool Press(const FString& Button);
    /** Draw or sheathe the sword, as the draw button does. False when the character has no sword. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool ToggleSword();
    /** Skateboarding (docs/SKATE.md): get on or off; hold skate. controls (sticks: x right, y away from the player) until
     *  SkateRelease; the ride's state as text; put the rider on the board at a ground point; the skate pier's spawn. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateToggle();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateInput(FVector2D Left, FVector2D Right, bool Push = false, bool Brake = false, bool Powerslide = false, bool GrabLeft = false, bool GrabRight = false);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateRelease();
    UFUNCTION(BlueprintCallable, Category = "Live") static FString SkateState();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkatePlace(FVector GroundPoint, float Yaw);
    UFUNCTION(BlueprintCallable, Category = "Live") static FTransform SkateParkSpawn();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateLaunch(FVector Velocity);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateGoofy(bool bGoofy);
    /** Feed a simulated input event to the player controller, as the platform would: Event "press", "release" or
     *  "axis" (send an axis every frame it moves, e.g. MouseX/MouseY deltas or Gamepad_RightX). Key is an FKey name. */
    /** Filming: a fixed simulation step (Fps > 0; 0 returns to real time), and the sound log that films mix offline
     *  (AudioLog: "start" clears and records, "stop" writes the events to Path as JSON; AudioFrame sets the frame). */
    UFUNCTION(BlueprintCallable, Category = "Live") static void FixedStep(float Fps);
    /** Filming the skating: the HUD keeps only the trick line and the balance needle. */
    UFUNCTION(BlueprintCallable, Category = "Live") static void FilmHud(bool bOn);
    static bool IsFilmHud();
    UFUNCTION(BlueprintCallable, Category = "Live") static int32 AudioLog(const FString& Command, const FString& Path = TEXT(""));
    UFUNCTION(BlueprintCallable, Category = "Live") static void AudioFrame(int32 Frame);
    /** The skate loops now: "volume pitch" for roll, grind, slide, skid and scrape. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString SkateLoops();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool InputKey(const FString& Key, const FString& Event, float Value = 1.f);
    /** Leave the camera where it is (no automatic skate follow) for Seconds, e.g. to film from the side. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool HoldCamera(float Seconds);
    /** A line of text for the player at the top of the screen. */
    UFUNCTION(BlueprintCallable, Category = "Live") static void Say(const FString& Text, float Seconds = 4.f);
    /** A screenshot of the game view (with the HUD) written to Path on the next frame. */
    UFUNCTION(BlueprintCallable, Category = "Live") static void Screenshot(const FString& Path);
    /** Overlays: games/yorimichi/live/overlays/<Name>.json lists props with their GLB, transform and collision. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SaveOverlay(const FString& Name);
    UFUNCTION(BlueprintCallable, Category = "Live") static int32 LoadOverlay(const FString& Name);
    UFUNCTION(BlueprintCallable, Category = "Live") static FString LiveRoot();
    /** The latest Say() line and its remaining time, for the HUD. */
    static bool CurrentMessage(FString& Text, float& Alpha);
};

/** Starts the live bridge (HTTP on localhost:8830) and loads every overlay once the world is ready. */
namespace JapanLive
{
    void Start(UWorld* World);
}
