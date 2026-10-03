#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "YorimichiLive.generated.h"

/**
 * Yorimichi's verbs for the live bridge (the platform's LiveBridge plugin has the game-independent ones in
 * ULiveLibrary). Python sees them as unreal.YorimichiLive.<snake_case>; the game's helper module (live/python)
 * looks names up here first, then in unreal.LiveLibrary.
 */
UCLASS()
class YORIMICHI_API UYorimichiLive : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Move the player as if the stick were held: Intent is camera-relative (Y forward, X right), Gait 0 walk, 1 run, 2 sprint.
     *  Zero intent stops. Any player input takes over again. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool Drive(FVector2D Intent, int32 Gait = 1);
    /** Press a button through the character's input handler (AWandererCharacter::Live_Press lists them). */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool Press(const FString& Button);
    /** Change a setting as the Esc menu and the phone do (UJapanPreferences::SetValue, saved); false for an unknown key. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SetPreference(const FString& Key, float Value);
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
    /** The skate loops now: "volume pitch" for roll, grind, slide, skid and scrape. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString SkateLoops();
    /** Filming the skating: the HUD keeps only the trick line and the balance needle. */
    UFUNCTION(BlueprintCallable, Category = "Live") static void FilmHud(bool bOn);
    static bool IsFilmHud();
    /** The sound log that films mix offline ("start" clears and records, "stop" writes the events to Path as JSON);
     *  AudioFrame sets the frame index. */
    UFUNCTION(BlueprintCallable, Category = "Live") static int32 AudioLog(const FString& Command, const FString& Path = TEXT(""));
    UFUNCTION(BlueprintCallable, Category = "Live") static void AudioFrame(int32 Frame);
    /** Leave the camera where it is (no automatic skate follow) for Seconds, e.g. to film from the side. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool HoldCamera(float Seconds);
    /** BOTW characters (BotwCreature.h): the roster as JSON; spawn one standing on a ground point (Mode idle, showcase,
     *  wander, camp or scripted) and get its actor name; play a clip or "role:<role>" (returns seconds); walk or run it to
     *  a ground point; change its mode; the spawned ones as JSON; remove them all. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString BotwRoster();
    UFUNCTION(BlueprintCallable, Category = "Live") static FString BotwSpawn(const FString& Name, FVector Ground, float Yaw, const FString& Mode = TEXT("idle"));
    UFUNCTION(BlueprintCallable, Category = "Live") static float BotwPlay(const FString& Actor, const FString& Clip, bool bLoop = true, float Rate = 1.f);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool BotwMoveTo(const FString& Actor, FVector Ground, bool bRun = false);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool BotwMode(const FString& Actor, const FString& Mode);
    UFUNCTION(BlueprintCallable, Category = "Live") static FString BotwList();
    UFUNCTION(BlueprintCallable, Category = "Live") static int32 BotwClear();
    /** The Esc menu's character switch (ABotwRider::SwitchPlayer): "Cairo" or a rider; returns the character playing. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString SwitchCharacter(const FString& Name);
};
