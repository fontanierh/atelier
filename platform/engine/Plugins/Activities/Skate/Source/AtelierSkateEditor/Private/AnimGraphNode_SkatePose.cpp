#include "AnimGraphNode_SkatePose.h"
#include "Kismet2/CompilerResultsLog.h"

#define LOCTEXT_NAMESPACE "AtelierSkateAnimGraph"

FText UAnimGraphNode_SkatePose::GetNodeTitle(ENodeTitleType::Type TitleType) const
{
    return LOCTEXT("NodeTitle", "Skate Pose");
}

FText UAnimGraphNode_SkatePose::GetTooltipText() const
{
    return LOCTEXT("Tooltip", "Uses the live native skateboard rider pose. Copies the source on the game thread, then evaluates local transforms on animation workers. The base pose passes through when skating is inactive; Weight blends from that base into the skating pose.");
}

FText UAnimGraphNode_SkatePose::GetMenuCategory() const
{
    return LOCTEXT("MenuCategory", "Animation|Atelier|Skate");
}

FLinearColor UAnimGraphNode_SkatePose::GetNodeTitleColor() const
{
    return FLinearColor(.12f, .42f, .32f);
}

void UAnimGraphNode_SkatePose::ValidateAnimNodeDuringCompilation(USkeleton* ForSkeleton, FCompilerResultsLog& MessageLog)
{
    Super::ValidateAnimNodeDuringCompilation(ForSkeleton, MessageLog);
    if (!FMath::IsFinite(Node.Weight) || Node.Weight < 0.f || Node.Weight > 1.f)
        MessageLog.Error(TEXT("@@ Skate Pose Weight must be finite and between 0 and 1."), this);
    if (!Node.bFindComponentOnOwner && !Node.SourceComponent.IsValid() && IsPinUnlinkedUnboundAndUnset(TEXT("SourceComponent"), EGPD_Input))
        MessageLog.Warning(TEXT("@@ Skate Pose needs a Source Component when Find Component On Owner is disabled."), this);
}

#undef LOCTEXT_NAMESPACE
