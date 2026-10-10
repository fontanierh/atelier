#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SkateMotionData.generated.h"

/** Simulation motion units (Y-up metres), unnormalised quaternion components and binary32 samples. */
USTRUCT()
struct ATELIERSKATE_API FSkateFloat3
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") float X = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Y = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Z = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateFloat4
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") float X = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Y = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Z = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float W = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateFloatRow
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> Values;
};

USTRUCT()
struct ATELIERSKATE_API FSkateBone
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int32 Parent = -1;
    UPROPERTY(VisibleAnywhere, Category="Motion") int32 Mirror = -1;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSample
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") float ScaleX = 1;
    UPROPERTY(VisibleAnywhere, Category="Motion") float ScaleY = 1;
    UPROPERTY(VisibleAnywhere, Category="Motion") float ScaleZ = 1;
    UPROPERTY(VisibleAnywhere, Category="Motion") float RotationX = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float RotationY = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float RotationZ = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float RotationW = 1;
    UPROPERTY(VisibleAnywhere, Category="Motion") float TranslationX = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float TranslationY = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float TranslationZ = 0;
};

/** One rig bone's tracks, in rig bone order. */
USTRUCT()
struct ATELIERSKATE_API FSkateBoneTracks
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") float ChannelWeight = 1;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> ScaleX;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> ScaleY;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> ScaleZ;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> RotationX;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> RotationY;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> RotationZ;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> RotationW;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> TranslationX;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> TranslationY;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> TranslationZ;
};

USTRUCT()
struct ATELIERSKATE_API FSkateReferencePose
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") int32 Bank = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceRecord = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateSample> Samples;
};

USTRUCT()
struct ATELIERSKATE_API FSkateAttribute
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") uint8 Type = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Begin = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float End = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Value = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") FString TargetBone;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceOffset = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateClipMetadata
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float FrameRate = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Frames = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float BaseSpeed = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") uint32 Flags = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateAttribute> Attributes;
};

USTRUCT()
struct ATELIERSKATE_API FSkatePhaseBlend
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Parameter;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FString> Children;
};

USTRUCT()
struct ATELIERSKATE_API FSkateBlendSimplex
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<uint32> Children;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateFloatRow> Vertices;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateFloatRow> Normals;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> Scales;
};

USTRUCT()
struct ATELIERSKATE_API FSkateBlendSpace
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FString> Parameters;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FString> Children;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateBlendSimplex> Simplexes;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelector
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Parameter;
    UPROPERTY(VisibleAnywhere, Category="Motion") FString DefaultChild;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FString> Children;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FString> Values;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelectionParameter
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") uint32 Mode = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Weight = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Minimum = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float Maximum = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelectionCandidate
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Child;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<float> Values;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelectionSpace
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateSelectionParameter> Parameters;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateSelectionCandidate> Candidates;
};

USTRUCT()
struct ATELIERSKATE_API FSkateUnsupportedTree
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") uint32 Type = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateMetadataBank
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString SourceBank;
    UPROPERTY(VisibleAnywhere, Category="Motion") FString SourceSha256;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceBytes = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateClipMetadata> Clips;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkatePhaseBlend> PhaseBlends;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateBlendSpace> BlendSpaces;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateSelector> Selectors;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateSelectionSpace> SelectionSpaces;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateUnsupportedTree> UnsupportedTrees;
};

USTRUCT()
struct ATELIERSKATE_API FSkateMotionClip
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Motion") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Motion") int32 Bank = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") int64 SourceRecord = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") float FrameRate = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") FSkateFloat3 LoopTranslation;
    UPROPERTY(VisibleAnywhere, Category="Motion") FSkateFloat4 LoopRotation;
    UPROPERTY(VisibleAnywhere, Category="Motion") bool bChannelAnimation = false;
    UPROPERTY(VisibleAnywhere, Category="Motion") int32 FrameCount = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateBoneTracks> Bones;
};

/** A bounded set of clips: normal asset references let Unreal cook and load each bank. */
UCLASS()
class ATELIERSKATE_API USkateMotionBank : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(VisibleAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateMotionClip> Clips;
};

/** Typed motion data, generated by the motion import and read-only in the editor (details-panel edits pass floats
 * through text). UAnimSequences remain derived preview/retargeting assets. */
UCLASS()
class ATELIERSKATE_API USkateMotionData : public UDataAsset
{
    GENERATED_BODY()
public:
    // The importer writes the current schema. The class default stays 0: a saved value equal to the class default is
    // omitted from the package, so a nonzero default would make an older asset read as current.
    static constexpr int32 CurrentSchema = 2;
    UPROPERTY(VisibleAnywhere, Category="Motion") int32 SchemaVersion = 0;
    UPROPERTY(VisibleAnywhere, Category="Motion") bool bHasTrajectory = false;
    UPROPERTY(VisibleAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateBone> Bones;
    UPROPERTY(VisibleAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateReferencePose> ReferencePoses;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<FSkateMetadataBank> Metadata;
    UPROPERTY(VisibleAnywhere, Category="Motion") TArray<TSoftObjectPtr<USkateMotionBank>> Banks;
};
