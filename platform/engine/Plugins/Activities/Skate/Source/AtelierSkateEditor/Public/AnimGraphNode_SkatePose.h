#pragma once

#include "CoreMinimal.h"
#include "AnimGraphNode_Base.h"
#include "AnimNodes/AnimNode_SkatePose.h"
#include "AnimGraphNode_SkatePose.generated.h"

/** Editor wrapper for the worker-safe native skating pose node. */
UCLASS()
class ATELIERSKATEEDITOR_API UAnimGraphNode_SkatePose : public UAnimGraphNode_Base
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, Category = "Settings")
    FAnimNode_SkatePose Node;

    virtual FText GetNodeTitle(ENodeTitleType::Type TitleType) const override;
    virtual FText GetTooltipText() const override;
    virtual FText GetMenuCategory() const override;
    virtual FLinearColor GetNodeTitleColor() const override;
    virtual void ValidateAnimNodeDuringCompilation(USkeleton* ForSkeleton, FCompilerResultsLog& MessageLog) override;
};
