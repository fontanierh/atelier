#include "JapanSkateWire.h"
#include "Math/Float16.h"

namespace
{
void Scalar(FArchive& Ar, double& Value, double Scale, double Limit)
{
    if (Ar.IsSaving() && (!FMath::IsFinite(Value) || FMath::Abs(Value) > Limit)) { Ar.SetError(); return; }
    int16 Encoded = Ar.IsSaving() ? int16(FMath::RoundToInt(Value * Scale)) : 0;
    Ar << Encoded;
    if (Ar.IsLoading()) Value = Encoded / Scale;
}
void Vector(FArchive& Ar, FVector& Value, bool bWorld)
{
    if (bWorld)
    {
        float X = Value.X, Y = Value.Y, Z = Value.Z;
        Ar << X << Y << Z;
        if (!FMath::IsFinite(X) || !FMath::IsFinite(Y) || !FMath::IsFinite(Z) ||
            FMath::Max3(FMath::Abs(X), FMath::Abs(Y), FMath::Abs(Z)) > 2000000.f) Ar.SetError();
        if (Ar.IsLoading()) Value = FVector(X, Y, Z);
    }
    else { Scalar(Ar, Value.X, 10., 3276.7); Scalar(Ar, Value.Y, 10., 3276.7); Scalar(Ar, Value.Z, 10., 3276.7); }
}
// Largest-component omission avoids Euler singularities during flips. 2 + 3*15 bits.
void Quaternion(FArchive& Ar, FQuat& Value)
{
    constexpr double Bound = .7071067811865475244;
    if (Ar.IsSaving())
    {
        if (Value.ContainsNaN() || Value.SizeSquared() < SMALL_NUMBER) { Ar.SetError(); return; }
        Value.Normalize();
    }
    double Parts[4] = {Value.X, Value.Y, Value.Z, Value.W};
    uint8 Largest = 0;
    if (Ar.IsSaving())
    {
        for (uint8 I = 1; I < 4; ++I) if (FMath::Abs(Parts[I]) > FMath::Abs(Parts[Largest])) Largest = I;
        if (Parts[Largest] < 0.) for (double& Part : Parts) Part = -Part;
    }
    Ar.SerializeBits(&Largest, 2);
    double Sum = 0.;
    for (uint8 I = 0; I < 4; ++I)
    {
        if (I == Largest) continue;
        uint16 Packed = Ar.IsSaving() ? uint16(FMath::Clamp(FMath::RoundToInt((Parts[I] + Bound) * (32767. / (2. * Bound))), 0, 32767)) : 0;
        Ar.SerializeBits(&Packed, 15);
        if (Ar.IsLoading()) Parts[I] = double(Packed) * (2. * Bound / 32767.) - Bound;
        Sum += Parts[I] * Parts[I];
    }
    if (Ar.IsLoading())
    {
        if (Sum > 1.001) { Ar.SetError(); return; }
        Parts[Largest] = FMath::Sqrt(FMath::Max(0., 1. - Sum));
        Value = FQuat(Parts[0], Parts[1], Parts[2], Parts[3]).GetNormalized();
    }
}
// Cairo and its merged move set share SK_Cairo's 148x reference root. Component-space
// bone scales therefore need more than a fixed 0..16 range. Half floats preserve 148 exactly
// in the same two bytes; strict positive finite bounds still reject malformed transforms.
void ScaleValue(FArchive& Ar, double& Value, double Limit)
{
    if (Ar.IsSaving() && (!FMath::IsFinite(Value) || Value < .0001 || Value > Limit)) { Ar.SetError(); return; }
    FFloat16 Encoded(Ar.IsSaving() ? float(Value) : 1.f);
    Ar << Encoded.Encoded;
    const double Decoded = Encoded.GetFloat();
    if (!FMath::IsFinite(Decoded) || Decoded <= 0. || Decoded > Limit) Ar.SetError();
    if (Ar.IsLoading()) Value = Decoded;
}
void Transform(FArchive& Ar, FTransform& Value, bool bWorld)
{
    FVector Position = Value.GetLocation(), Scale = Value.GetScale3D();
    FQuat Rotation = Value.GetRotation();
    Vector(Ar, Position, bWorld);
    Quaternion(Ar, Rotation);
    const double Limit = bWorld ? 16. : 1024.;
    ScaleValue(Ar, Scale.X, Limit); ScaleValue(Ar, Scale.Y, Limit); ScaleValue(Ar, Scale.Z, Limit);
    if (Scale.GetMin() <= 0.) Ar.SetError();
    if (Ar.IsLoading()) Value = FTransform(Rotation, Position, Scale);
}
}

bool FJapanSkateChunk::NetSerialize(FArchive& Ar, UPackageMap*, bool& bSuccess)
{
    Ar << Epoch << Frame << TotalBones << Chunk << Time << Interval;
    const int32 Chunks = FMath::Max(1, FMath::DivideAndRoundUp(int32(TotalBones), BonesPerChunk));
    if (!Epoch || TotalBones > MaximumBones || Chunk >= Chunks || !FMath::IsFinite(Time) || Time < 0.f || !FMath::IsFinite(Interval) || Interval < 1.f/120.f || Interval > 30.f)
    { Ar.SetError(); bSuccess = false; return true; }
    const int32 Count = FMath::Clamp(int32(TotalBones) - int32(Chunk) * BonesPerChunk, 0, BonesPerChunk);
    if (Ar.IsLoading()) Bones.SetNum(Count);
    if (Bones.Num() != Count) { Ar.SetError(); bSuccess = false; return true; }
    Transform(Ar, Root, true); Transform(Ar, Mesh, true); Transform(Ar, Deck, true);
    Ar << Shown << Mode << Surface << AudioFlags;
    if (Mode > 4 || Surface > 8 || AudioFlags > 7) Ar.SetError();
    if (!FMath::IsFinite(Shown) || Shown < 0.f || Shown > 1.f) Ar.SetError();
    Vector(Ar, Velocity, true);
    for (FTransform& Bone : Bones) Transform(Ar, Bone, false);
    bSuccess = !Ar.IsError();
    return true;
}

bool FJapanSkateAssembly::Add(const FJapanSkateChunk& Chunk, FJapanSkateFrame& Complete)
{
    if (!Chunk.Epoch || Chunk.TotalBones > FJapanSkateChunk::MaximumBones) return false;
    const int32 Count = FMath::Max(1, FMath::DivideAndRoundUp(int32(Chunk.TotalBones), FJapanSkateChunk::BonesPerChunk));
    if (Chunk.Chunk >= Count || Chunk.Bones.Num() != FMath::Clamp(int32(Chunk.TotalBones) -
        int32(Chunk.Chunk) * FJapanSkateChunk::BonesPerChunk, 0, FJapanSkateChunk::BonesPerChunk)) return false;
    const int32 Slot = Chunk.Frame % 3;
    FJapanSkateFrame& Frame = Frames[Slot];
    if (Frame.Epoch == Chunk.Epoch && int32(Chunk.Frame - Frame.Frame) < 0) return false;
    if (Frame.Epoch != Chunk.Epoch || Frame.Frame != Chunk.Frame)
    {
        Frame = FJapanSkateFrame(); Masks[Slot] = 0;
        Frame.Epoch = Chunk.Epoch; Frame.Frame = Chunk.Frame; Frame.Time = Chunk.Time; Frame.Interval = Chunk.Interval;
        Frame.Root = Chunk.Root; Frame.Mesh = Chunk.Mesh; Frame.Deck = Chunk.Deck; Frame.Shown = Chunk.Shown; Frame.Mode = Chunk.Mode; Frame.Surface = Chunk.Surface; Frame.AudioFlags = Chunk.AudioFlags; Frame.Velocity = Chunk.Velocity;
        Frame.Bones.SetNum(Chunk.TotalBones);
    }
    if (Frame.Bones.Num() != Chunk.TotalBones || Frame.Time != Chunk.Time || Frame.Interval != Chunk.Interval ||
        !Frame.Root.Equals(Chunk.Root, .001) || !Frame.Mesh.Equals(Chunk.Mesh, .001) ||
        !Frame.Deck.Equals(Chunk.Deck, .001) || Frame.Shown != Chunk.Shown || Frame.Mode != Chunk.Mode || Frame.Surface != Chunk.Surface || Frame.AudioFlags != Chunk.AudioFlags || !Frame.Velocity.Equals(Chunk.Velocity, .001)) return false;
    const uint8 Bit = uint8(1 << Chunk.Chunk);
    if (Masks[Slot] & Bit) return false;
    for (int32 I = 0; I < Chunk.Bones.Num(); ++I) Frame.Bones[int32(Chunk.Chunk) * FJapanSkateChunk::BonesPerChunk + I] = Chunk.Bones[I];
    Masks[Slot] |= Bit;
    if (Masks[Slot] != uint8((1 << Count) - 1)) return false;
    Complete = Frame;
    return true;
}

bool FJapanSkateBodies::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bSuccess)
{
    Pose.NetSerialize(Ar, Map, bSuccess);
    if (!bSuccess || Pose.Chunk != 0 || Pose.TotalBones == 0 || Pose.TotalBones > 32)
    { Ar.SetError(); bSuccess = false; return true; }
    if (Ar.IsLoading()) Indices.SetNum(Pose.TotalBones);
    if (Indices.Num() != Pose.TotalBones) { Ar.SetError(); bSuccess = false; return true; }
    bool Used[256] = {};
    for (uint8& Index : Indices)
    {
        Ar << Index;
        if (Used[Index]) Ar.SetError();
        Used[Index] = true;
    }
    bSuccess = !Ar.IsError();
    return true;
}
