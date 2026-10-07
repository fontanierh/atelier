#pragma once
#include "CoreMinimal.h"

/** Saved player locations in Unreal centimetres/degrees; no generated-world or character dependencies. */
struct FJapanMarker
{
    FString Key, Name;
    FTransform Ground;
};

/** A world-owned save: pawn switches share it. Mutations commit only after the sibling file is replaced. */
class FJapanMarkers
{
public:
    void Load();
    const TArray<FJapanMarker>& All() const { return Markers; }
    const FJapanMarker* Selected() const;
    FString NextName() const;
    bool Add(const FString& Name, const FTransform& Ground);
    bool Select(const FString& Key);
    bool Rename(const FString& Name);
    bool Delete();
    FString Error;
private:
    TArray<FJapanMarker> Markers;
    FString SelectedKey, File;
    bool bLoaded = false, bWritable = true;
    bool Commit(TArray<FJapanMarker> Next, const FString& Selected);
    bool NameValid(const FString& Name);
};
