#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SkateRuntimeData.generated.h"

// The session's settings, graphs, camera, gesture and physical skeleton records as Unreal properties. Every value the
// session reads as a binary32 or raw word is kept as its uint32 bit pattern (a float property would save negative zero
// as its default), so the encoded files are exactly the package's.

/** A settings field: Text, or Bytes of data in words (whole words big-endian, a last partial word in its low bytes). */
USTRUCT()
struct ATELIERSKATE_API FSkateSettingField
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Type;
    UPROPERTY(VisibleAnywhere, Category="Runtime") bool bText = false;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Text;
    UPROPERTY(VisibleAnywhere, Category="Runtime") int32 Bytes = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> Words;
};

/** A settings record; lookups take the first record that matches, so the order is kept. */
USTRUCT()
struct ATELIERSKATE_API FSkateSettingRecord
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Category;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Key;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Parent;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Name")) TArray<FSkateSettingField> Fields;
};

/** A graph attribute: its text, the text read as a binary32 (0 when it is not a number) and whether it is "true". */
USTRUCT()
struct ATELIERSKATE_API FSkateGraphAttribute
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Text;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 Number = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") bool bTrue = false;
};

/** A graph element in preorder; Children index the graph's elements. */
USTRUCT()
struct ATELIERSKATE_API FSkateGraphElement
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Tag;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Name")) TArray<FSkateGraphAttribute> Attributes;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<int32> Children;
};

USTRUCT()
struct ATELIERSKATE_API FSkateGraph
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Tag")) TArray<FSkateGraphElement> Elements;
};

/** A camera shot. Numbers are binary32 bit patterns, except the integer flags, types and units. */
USTRUCT()
struct ATELIERSKATE_API FSkateCameraShot
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 ShotType = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 Distance = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 LensLength = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> Smoothing;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> ReferenceWeights;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 BoardOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 PositionHeading = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 PositionElevation = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> Framing;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 FollowSubjectInAir = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 MirrorForStance = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 SnapToReferencePoint = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 UsePreviousShot = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 UseDropPredictor = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 UseFreeCameraStick = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 AvoidanceOverride = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 Blur = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 TransitionBlur = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 SubjectOpacity = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 CollisionHint = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 Anchor = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 CompassNorth = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 WorldHeading = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> ArmOrientation;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> CameraOrientation;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 TransitionTime = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 TransitionUnits = 0;
    /** Up to three child shots, in slot order. */
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<FString> Children;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> BlendPoints;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 BlendValue = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 BlendType = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 BlendSmoothing = 0;
};

/** A camera shake: four rotation and four translation words per sample. */
USTRUCT()
struct ATELIERSKATE_API FSkateCameraShake
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> Rotations;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> Translations;
};

/** A gesture pattern; Points holds x and y binary32 words per point. */
USTRUCT()
struct ATELIERSKATE_API FSkateGesturePattern
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 ToleranceSquared = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> Points;
};

/** A gesture set; pattern names repeat, so they are a list. */
USTRUCT()
struct ATELIERSKATE_API FSkateGestureSet
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint32 Stick = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Name")) TArray<FSkateGesturePattern> Patterns;
};

USTRUCT()
struct ATELIERSKATE_API FSkatePhysicalBone
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint64 SourceOffset = 0;
    /** The bone's 28 words: transforms, limits and hashes. */
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<uint32> Words;
};

USTRUCT()
struct ATELIERSKATE_API FSkatePhysicalSkeleton
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Name;
    UPROPERTY(VisibleAnywhere, Category="Runtime") uint64 SourceOffset = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Name")) TArray<FSkatePhysicalBone> Bones;
};

/** An encoded runtime file's size and SHA-1, checked when the game loads the data. */
USTRUCT()
struct ATELIERSKATE_API FSkateRuntimeDigest
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString File;
    UPROPERTY(VisibleAnywhere, Category="Runtime") int32 Bytes = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString Sha1;
};

/** Typed runtime data, generated by the runtime import and read-only in the editor. */
UCLASS()
class ATELIERSKATE_API USkateRuntimeData : public UDataAsset
{
    GENERATED_BODY()
public:
    // The class default stays 0, as in USkateMotionData.
    static constexpr int32 CurrentSchema = 1;
    UPROPERTY(VisibleAnywhere, Category="Runtime") int32 SchemaVersion = 0;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Key")) TArray<FSkateSettingRecord> Settings;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FSkateGraph ActionGraph;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FSkateGraph MotionGraph;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FSkateGraph CameraGraph;
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString CameraSource;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Name")) TArray<FSkateCameraShot> CameraShots;
    UPROPERTY(VisibleAnywhere, Category="Runtime") TArray<FSkateCameraShake> CameraShakes;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Name")) TArray<FSkateGestureSet> Gestures;
    /** The motion metadata's source SHA-256, which the physical skeletons are checked against. */
    UPROPERTY(VisibleAnywhere, Category="Runtime") FString PhysicalSource;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="Name")) TArray<FSkatePhysicalSkeleton> PhysicalSkeletons;
    UPROPERTY(VisibleAnywhere, Category="Runtime", meta=(TitleProperty="File")) TArray<FSkateRuntimeDigest> Digests;
};
