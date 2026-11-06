#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "V2SaveGuard.generated.h"

/**
 * The save boundary of a V2 write (CONTRACTS yorimichi-v2-single-writer). When the editor starts with
 * V2_SAVE_ALLOW naming a file of absolute package filenames (one per line), every other package save is refused
 * before any bytes are written; an unreadable list refuses every save. Without V2_SAVE_ALLOW the editor's own
 * rules apply unchanged. The authorized route (an import, a claimed editor script) writes the list.
 */
UCLASS()
class YORIMICHIIMPORT_API UV2SaveGuard : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** True when this editor enforces an allow list; scripts that require it check this before writing. */
    UFUNCTION(BlueprintCallable, Category="V2|Authoring")
    static bool IsActive();
    /** How many package files the allow list admits. */
    UFUNCTION(BlueprintCallable, Category="V2|Authoring")
    static int32 AllowedCount();
    /** Packages whose save the guard refused in this editor session. */
    UFUNCTION(BlueprintCallable, Category="V2|Authoring")
    static TArray<FString> Refused();

    /** Reads V2_SAVE_ALLOW and, after engine init, wraps the editor's IsPackageOKToSave check. */
    static void Startup();
    static void Shutdown();
};
