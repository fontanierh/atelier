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
    /** Send accept (Enter), next (Tab) or previous (Shift+Tab) through the open native settings menu's actual widgets.
     *  Refuses unknown keys or a closed menu; useful for reviewing warnings and cancellation without changing preferences directly. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool MenuKey(const FString& Key);
    /** Change a setting as the Esc menu and the phone do (UJapanPreferences::SetValue, saved); false for an unknown key. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SetPreference(const FString& Key, float Value);
    /** An adventure move set's state (UAdventureMoveSet::Describe: mode, action, stamina, glider, wall, target, counts) as JSON;
     *  "{}" when the player has none. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString MoveState();
    /** Throw the player (cm/s, replacing the velocity): a glide or a plunge from height without a cliff. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool Launch(FVector Velocity);
    /** Draw or sheathe the sword, as the draw button does. False when the character has no sword. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool ToggleSword();
    /** Skateboarding (docs/SKATE.md): get on or off; hold skate. controls (sticks: x right, y away from the player) until
     *  SkateRelease; the ride's state as text; put the rider on the board at a ground point; the skate pier's spawn. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateToggle();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateInput(FVector2D Left, FVector2D Right, bool Push = false, bool Brake = false, bool Powerslide = false, float GrabLeft = 0, float GrabRight = 0);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateRelease();
    UFUNCTION(BlueprintCallable, Category = "Live") static FString SkateState();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkatePlace(FVector GroundPoint, float Yaw);
    UFUNCTION(BlueprintCallable, Category = "Live") static FTransform SkateParkSpawn();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateLaunch(FVector Velocity);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool SkateGoofy(bool bGoofy);
    /** The bike (docs/BIKE.md) as text: state, clip and its time, speed, steering, the rider and the bike's placement. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString BikeState();
    /** The skate loops now: "volume pitch" for roll, grind, slide, skid and scrape. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString SkateLoops();
    /** The bike's loops, "volume pitch" each (UBikeComponent::GetLoopState). */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString BikeLoops();
    /** Filming the skating: the HUD keeps only the trick line and the balance needle. */
    UFUNCTION(BlueprintCallable, Category = "Live") static void FilmHud(bool bOn);
    static bool IsFilmHud();
    /** Leave the camera where it is (no automatic skate follow) for Seconds, e.g. to film from the side. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool HoldCamera(float Seconds);
    /** The Esc menu's character switch (FPlayableCharacter::SwitchPlayer): "Cairo" or a rider; returns the character playing. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString SwitchCharacter(const FString& Name);
    /** The sword trainer (ASwordTrainer): her state as JSON; a bout with the player (level 0 gentle, 1 steady, 2 master);
     *  her menu; ending a bout; forcing her next opening ("combo", "charge", "dash", "jump", "double", "feint") or her
     *  answer to the next blow ("parry", "dodge", "perfect", "guard", "take"); her location for filming (Ground Yaw). */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString TrainerState();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool TrainerBout(int32 Level = 1, bool bHerShield = false, bool bPlayerShield = false);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool TrainerMenu();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool TrainerEnd();
    UFUNCTION(BlueprintCallable, Category = "Live") static bool TrainerForce(const FString& Attack, const FString& Defence);
    UFUNCTION(BlueprintCallable, Category = "Live") static bool TrainerPlace(FVector Ground, float Yaw);
    /** Visit the hippodrome as a public venue. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool HippodromeVisit();
};
