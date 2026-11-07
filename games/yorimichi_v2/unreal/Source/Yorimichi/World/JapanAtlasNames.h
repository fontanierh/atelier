#pragma once
#include "CoreMinimal.h"

/** Local, world-owned stable label overrides. Changes become visible only after an atomic save succeeds. */
class FJapanAtlasNames
{
public:
    void Load(const FString& ReviewFile = FString());
    FString Get(const FString& Key, const FString& Default) const;
    bool Rename(const FString& Key, const FString& Name);
    bool Reset(const FString& Key);
    FString Error;
private:
    TMap<FString,FString> Names;
    FString File;
    bool bLoaded = false, bWritable = true;
    bool Commit(const TMap<FString,FString>& Next);
};
