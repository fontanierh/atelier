#pragma once
#include "CoreMinimal.h"

// Called by the existing guarded worker's fixed native finalise entry point.
FString AtelierZenFinaliseRequest(const FString& RequestJson);
