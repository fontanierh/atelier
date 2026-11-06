#pragma once
#include "CoreMinimal.h"
#include "JapanSkateWire.generated.h"

/** One small unreliable datagram. Never allocate a pose from a peer-provided unbounded count. */
USTRUCT()
struct FJapanSkateChunk
{
    GENERATED_BODY()
    static constexpr int32 BonesPerChunk = 32, MaximumBones = 256;
    uint32 Epoch = 1, Frame = 0;
    uint16 TotalBones = 0;
    uint8 Chunk = 0;
    double Time = 0.;
    float Interval = 1.f / 30.f; // server-assigned delivery interval for this recipient
    FTransform Root = FTransform::Identity, Mesh = FTransform::Identity, Deck = FTransform::Identity;
    float Shown = 0.f;
    uint8 Mode = 0, Surface = 0, AudioFlags = 0;
    FVector Velocity = FVector::ZeroVector;
    // Component-space transforms captured after animation and physics blending, never RiderPose.
    TArray<FTransform> Bones;
    bool NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bSuccess);
};
template<> struct TStructOpsTypeTraits<FJapanSkateChunk> : TStructOpsTypeTraitsBase2<FJapanSkateChunk>
{ enum { WithNetSerializer = true }; };

USTRUCT()
struct FJapanBoardState
{
    GENERATED_BODY()
    // Board lifetime deliberately does not use the rider activity epoch: it can remain on the ground after dismount.
    UPROPERTY() uint32 Sequence = 0;
    UPROPERTY() FTransform Deck = FTransform::Identity;
    UPROPERTY() float Shown = 0.f;
    UPROPERTY() double Time = 0.;
};

struct FJapanSkateFrame
{
    uint32 Epoch = 0, Frame = 0;
    double Time = 0.;
    float Interval = 1.f / 30.f; // server-assigned delivery interval for this recipient
    FTransform Root = FTransform::Identity, Mesh = FTransform::Identity, Deck = FTransform::Identity;
    float Shown = 0.f;
    uint8 Mode = 0, Surface = 0, AudioFlags = 0;
    FVector Velocity = FVector::ZeroVector;
    TArray<FTransform> Bones;
};

/** A fixed-size assembly window tolerates reordering and drops incomplete old frames. */
struct FJapanSkateAssembly
{
    FJapanSkateFrame Frames[3];
    uint8 Masks[3] = {};
    bool Add(const FJapanSkateChunk& Chunk, FJapanSkateFrame& Complete);
    void Reset() { for (int32 I = 0; I < 3; ++I) { Frames[I] = FJapanSkateFrame(); Masks[I] = 0; } }
};

/** High-rate bail anchors: the fitted physical bodies, indexed in the admitted rider skeleton. */
USTRUCT()
struct FJapanSkateBodies
{
    GENERATED_BODY()
    FJapanSkateChunk Pose;
    TArray<uint8> Indices;
    bool NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bSuccess);
};
template<> struct TStructOpsTypeTraits<FJapanSkateBodies> : TStructOpsTypeTraitsBase2<FJapanSkateBodies>
{ enum { WithNetSerializer = true }; };
