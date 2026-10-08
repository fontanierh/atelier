#pragma once

#include "CoreMinimal.h"

/** Ends the game through the normal engine shutdown with this process exit status. UE's Mac fallback for
 *  RequestExitWithStatus drops the status, so a failed scripted run (QA, a review, a capture) would exit 0 there. */
ATELIERCORE_API void AtelierRequestExit(int32 Status);
