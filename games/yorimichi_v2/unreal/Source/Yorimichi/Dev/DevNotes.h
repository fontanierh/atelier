#pragma once
#include "CoreMinimal.h"

class UJapanPreferences;
class UWorld;

/** Dev mode, from the settings menu: a free camera flies anywhere without gravity or collision, and each note records
 * the camera, the point it looks at, a screenshot and typed text. Export writes every note and screenshot as one zip
 * beside the notes (the app's sandbox container), shows it in Finder and copies the notes as text. Keys while flying: WASD or the left stick move, the mouse or the right
 * stick look, E/Space or the right trigger up, Q/C or the left trigger down, Shift or the left shoulder fast, N or the
 * top face button take a note (Enter saves, Escape cancels), X or the View button exports. */
namespace DevNotes
{
    YORIMICHI_API bool IsOn();
    YORIMICHI_API void Toggle(UWorld* World, UJapanPreferences* Menu);
    /** Writes the zip; returns its path, or empty. */
    YORIMICHI_API FString Export();
    YORIMICHI_API int32 Count();
}
