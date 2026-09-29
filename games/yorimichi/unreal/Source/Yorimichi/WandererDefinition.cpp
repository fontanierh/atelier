#include "WandererDefinition.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkinnedAssetCommon.h"

UAnimSequence* UWandererDefinition::FindAction(FName Name) const
{
    const TObjectPtr<UAnimSequence>* Entry = Actions.Find(Name);
    return Entry ? Entry->Get() : nullptr;
}

const FWandererSwordClip* UWandererDefinition::FindSwordClip(FName Role) const
{
    return SwordClips.FindByPredicate([Role](const FWandererSwordClip& C) { return C.Role == Role; });
}

bool UWandererContentLibrary::ConfigureMeshLODs(USkeletalMesh* Asset)
{
#if WITH_EDITOR
    if (!Asset || Asset->GetLODNum() == 0) return false;
    Asset->Modify();
    Asset->SetNumSourceModels(3);
    const float Fractions[] = {1.f,.35f,.10f};
    const float Screens[] = {1.f,.45f,.18f};
    for (int32 I = 1; I < 3; ++I)
    {
        FSkeletalMeshLODInfo* Info = Asset->GetLODInfo(I);
        if (!Info) return false;
        Info->ScreenSize.Default = Screens[I];
        Info->ReductionSettings.NumOfTrianglesPercentage = Fractions[I];
        Info->ReductionSettings.NumOfVertPercentage = Fractions[I];
        Info->ReductionSettings.BaseLOD = 0;
    }
    Asset->MarkPackageDirty();
    return true;
#else
    return false;
#endif
}

bool UWandererContentLibrary::ConfigureBlendSpace(UBlendSpace* Asset, const TArray<UAnimSequence*>& Clips, const TArray<float>& Speeds)
{
#if WITH_EDITOR
    if (!Asset || Clips.IsEmpty() || Clips.Num() != Speeds.Num()) return false;
    for (UAnimSequence* Clip : Clips) if (!Clip) return false;
    Asset->Modify();
    Asset->SetSkeleton(Clips[0]->GetSkeleton());
    while (Asset->GetNumberOfBlendSamples()) Asset->DeleteSample(Asset->GetNumberOfBlendSamples() - 1);
    for (int32 I = 0; I < Clips.Num(); ++I)
        if (Asset->AddSample(Clips[I], FVector(Speeds[I], 0, 0)) == INDEX_NONE) return false;
    Asset->ValidateSampleData();
    Asset->ResampleData();
    Asset->PostEditChange();
    Asset->MarkPackageDirty();
    return true;
#else
    return false;
#endif
}
