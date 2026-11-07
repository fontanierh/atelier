#pragma once
#include "CoreMinimal.h"

class AWandererCharacter;
class UWorld;
struct FSlateBrush;

/**
 * Startup and on-demand character selection screen, designed from the Sunburst UI reference
 * (assets/characters/concepts/character-select.jpg) with each playable character's staged
 * profile portrait (Content/Data/<id>/portrait.png).
 */
struct YORIMICHI_API FJapanCharacterSelect
{
    struct FCardInfo
    {
        FString Id;
        FString Name;
        FString Badge;
        FString Tagline;
        FLinearColor Accent;
        FLinearColor AccentBorder;
        FLinearColor BadgeFill;
        FLinearColor BadgeText;
        bool bDefault = false;
        bool bBuilt = false;
        bool bPortraitLoaded = false;
    };

    /** Whether this session should open the character selection screen when the local player enters the world. */
    static bool ShouldOpenAtStartup(const UWorld* World);
    /** Whether the startup character selection screen has already opened in this world. */
    static bool HasOpenedForWorld(const UWorld* World);
    /** Open the character selection screen for Pawn (bStartup marks the initial launch screen). */
    static bool Open(AWandererCharacter* Pawn, bool bStartup = false);
    /** Close the character selection screen without changing characters (when OwnerPawn is given, only if owned by it). */
    static void Close(const AWandererCharacter* OwnerPawn = nullptr);
    static bool IsOpen();
    /** Move the highlighted card by Delta (-1 left, +1 right). */
    static bool StepSelection(int32 Delta);
    /** Highlight a character by name or id without closing the screen. */
    static bool Highlight(const FString& NameOrId);
    /** Confirm the highlighted character (or NameOrId when given), switching the player pawn if needed, and close. */
    static AWandererCharacter* Choose(const FString& NameOrId = FString());
    /** Currently highlighted character display name, or empty when closed. */
    static FString SelectedName();
    /** Control focus key for the live bridge (e.g. character_select:Cairo). */
    static FString FocusedControl();
    /** JSON description of the screen state and roster cards for live QA inspection. */
    static FString Describe();
    /** Roster cards for every registered playable character. */
    static TArray<FCardInfo> Cards();
    /** Cached Slate brush for Content/Data/<id>/portrait.png, or nullptr if missing. */
    static const FSlateBrush* PortraitBrush(const FString& CharacterId);
};

