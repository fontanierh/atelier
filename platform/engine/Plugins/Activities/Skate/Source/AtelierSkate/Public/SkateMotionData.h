#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SkateMotionData.generated.h"

/** Native motion units (Y-up metres), unnormalised quaternion components and binary32 samples. */
USTRUCT()
struct ATELIERSKATE_API FSkateFloat3
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") float X = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Y = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Z = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateFloat4
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") float X = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Y = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Z = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float W = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateFloatRow
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> Values;
};

USTRUCT()
struct ATELIERSKATE_API FSkateBone
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int32 Parent = -1;
    UPROPERTY(EditAnywhere, Category="Motion") int32 Mirror = -1;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSample
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") float ScaleX = 1;
    UPROPERTY(EditAnywhere, Category="Motion") float ScaleY = 1;
    UPROPERTY(EditAnywhere, Category="Motion") float ScaleZ = 1;
    UPROPERTY(EditAnywhere, Category="Motion") float RotationX = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float RotationY = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float RotationZ = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float RotationW = 1;
    UPROPERTY(EditAnywhere, Category="Motion") float TranslationX = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float TranslationY = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float TranslationZ = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateBoneTracks
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString BoneName;
    UPROPERTY(EditAnywhere, Category="Motion") float ChannelWeight = 1;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> ScaleX;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> ScaleY;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> ScaleZ;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> RotationX;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> RotationY;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> RotationZ;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> RotationW;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> TranslationX;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> TranslationY;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> TranslationZ;
};

USTRUCT()
struct ATELIERSKATE_API FSkateReferencePose
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") int32 Bank = 0;
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceRecord = 0;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateSample> Samples;
};

USTRUCT()
struct ATELIERSKATE_API FSkateAttribute
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") uint8 Type = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Begin = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float End = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Value = 0;
    UPROPERTY(EditAnywhere, Category="Motion") FString TargetBone;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceOffset = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateClipMetadata
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float FrameRate = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Frames = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float BaseSpeed = 0;
    UPROPERTY(EditAnywhere, Category="Motion") uint32 Flags = 0;
    UPROPERTY(EditAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateAttribute> Attributes;
};

USTRUCT()
struct ATELIERSKATE_API FSkatePhaseBlend
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(EditAnywhere, Category="Motion") FString Parameter;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FString> Children;
};

USTRUCT()
struct ATELIERSKATE_API FSkateBlendSimplex
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") TArray<uint32> Children;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateFloatRow> Vertices;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateFloatRow> Normals;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> Scales;
};

USTRUCT()
struct ATELIERSKATE_API FSkateBlendSpace
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FString> Parameters;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FString> Children;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateBlendSimplex> Simplexes;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelector
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(EditAnywhere, Category="Motion") FString Parameter;
    UPROPERTY(EditAnywhere, Category="Motion") FString DefaultChild;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FString> Children;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FString> Values;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelectionParameter
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") uint32 Mode = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Weight = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Minimum = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float Maximum = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelectionCandidate
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Child;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<float> Values;
};

USTRUCT()
struct ATELIERSKATE_API FSkateSelectionSpace
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateSelectionParameter> Parameters;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateSelectionCandidate> Candidates;
};

USTRUCT()
struct ATELIERSKATE_API FSkateUnsupportedTree
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceOffset = 0;
    UPROPERTY(EditAnywhere, Category="Motion") uint32 Type = 0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateMetadataBank
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString SourceBank;
    UPROPERTY(EditAnywhere, Category="Motion") FString SourceSha256;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceBytes = 0;
    UPROPERTY(EditAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateClipMetadata> Clips;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkatePhaseBlend> PhaseBlends;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateBlendSpace> BlendSpaces;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateSelector> Selectors;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateSelectionSpace> SelectionSpaces;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateUnsupportedTree> UnsupportedTrees;
};

USTRUCT()
struct ATELIERSKATE_API FSkateMotionClip
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Motion") FString Name;
    UPROPERTY(EditAnywhere, Category="Motion") int32 Bank = 0;
    UPROPERTY(EditAnywhere, Category="Motion") int64 SourceRecord = 0;
    UPROPERTY(EditAnywhere, Category="Motion") float FrameRate = 0;
    UPROPERTY(EditAnywhere, Category="Motion") FSkateFloat3 LoopTranslation;
    UPROPERTY(EditAnywhere, Category="Motion") FSkateFloat4 LoopRotation;
    UPROPERTY(EditAnywhere, Category="Motion") bool bChannelAnimation = false;
    UPROPERTY(EditAnywhere, Category="Motion") int32 FrameCount = 0;
    UPROPERTY(EditAnywhere, Category="Motion", meta=(TitleProperty="BoneName")) TArray<FSkateBoneTracks> Bones;
};

/** A bounded set of clips: normal asset references let Unreal cook and load each bank. */
UCLASS()
class ATELIERSKATE_API USkateMotionBank : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateMotionClip> Clips;
};

/** Typed authoritative motion data. UAnimSequences remain derived preview/retargeting assets. */
UCLASS()
class ATELIERSKATE_API USkateMotionData : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(VisibleAnywhere, Category="Motion") int32 SchemaVersion = 1;
    UPROPERTY(EditAnywhere, Category="Motion") bool bHasTrajectory = false;
    UPROPERTY(EditAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateBone> Bones;
    UPROPERTY(EditAnywhere, Category="Motion", meta=(TitleProperty="Name")) TArray<FSkateReferencePose> ReferencePoses;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<FSkateMetadataBank> Metadata;
    UPROPERTY(EditAnywhere, Category="Motion") TArray<TSoftObjectPtr<USkateMotionBank>> Banks;
};

UCLASS()
class ATELIERSKATE_API USkateMotionLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** One-time migration: decode the reference bundle into named Unreal properties and save packages. */
    UFUNCTION(BlueprintCallable, Category="Skate Motion") static bool ImportMotion(const FString& ReferenceFolder, const FString& AssetFolder, FString& Error);
    /** Fresh editor process: exhaustive comparison and deterministic production-session replays. */
    UFUNCTION(BlueprintCallable, Category="Skate Motion") static bool VerifyMotion(const FString& ReferenceFolder, USkateMotionData* Data, const FString& ReportFile, FString& Error);
};
