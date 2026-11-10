#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MaterialInputAudit.generated.h"

class UMaterialExpression;

/** A read of one actual FExpressionInput, independent of Python's protected-property access. */
USTRUCT(BlueprintType)
struct FMaterialInputAuditResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category="V2|Authoring") FString Error;
    UPROPERTY(BlueprintReadOnly, Category="V2|Authoring") FString SourcePath;
    UPROPERTY(BlueprintReadOnly, Category="V2|Authoring") int32 OutputIndex = INDEX_NONE;
    /** Mask, R, G, B, A, in that order; preserve the native values rather than inferring them from an output name. */
    UPROPERTY(BlueprintReadOnly, Category="V2|Authoring") TArray<int32> Masks;
};

/** Native, read-only access to material input connections for source/rebuild acceptance. */
UCLASS()
class YORIMICHIIMPORT_API UMaterialInputAudit : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** @cc [owner:fontanierh,label:correctness] material-input-audit-read-only
     * Read exactly the requested input's source, output index and component masks. Invalid, absent or unconnected inputs
     * MUST report Error. This MUST NOT change a property flag, connect an input, compile, dirty or save any asset.
     */
    UFUNCTION(BlueprintCallable, Category="V2|Authoring")
    static FMaterialInputAuditResult ReadInput(UMaterialExpression* Expression, int32 InputIndex);
};
