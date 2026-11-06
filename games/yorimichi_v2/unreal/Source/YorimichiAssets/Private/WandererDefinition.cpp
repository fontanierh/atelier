#include "WandererDefinition.h"
#include "Animation/AnimSequence.h"

UAnimSequence* UWandererDefinition::FindAction(FName Name) const
{
    const TObjectPtr<UAnimSequence>* Entry = Actions.Find(Name);
    return Entry ? Entry->Get() : nullptr;
}

const FWandererSwordClip* UWandererDefinition::FindSwordClip(FName Role) const
{
    return SwordClips.FindByPredicate([Role](const FWandererSwordClip& C) { return C.Role == Role; });
}
