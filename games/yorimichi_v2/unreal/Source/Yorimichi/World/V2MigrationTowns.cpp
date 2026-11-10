#include "V2MigrationTowns.h"

#include "AtelierData.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace V2MigrationTowns
{
TArray<FString> GroupKeys(const TSharedPtr<FJsonObject>& Data)
{
    TArray<FString> Names;
    TMap<FString, int32> Count;
    for (const auto& Value : Data->GetArrayField(TEXT("groups")))
    {
        const FString Name = FPaths::GetBaseFilename(Value->AsObject()->GetStringField(TEXT("asset")));
        Names.Add(Name);
        int32& Seen = Count.FindOrAdd(Name);
        ++Seen;
    }
    TArray<FString> Keys;
    for (int32 Index = 0; Index < Names.Num(); ++Index)
        Keys.Add(Count[Names[Index]] > 1 ? FString::Printf(TEXT("%s#%d"), *Names[Index], Index) : Names[Index]);
    return Keys;
}

FString PieceKey(const FString& Key, int32 CellX, int32 CellY)
{
    return FString::Printf(TEXT("%s@%d_%d"), *Key, CellX, CellY);
}

bool ParsePieceKey(const FString& Key, FString& OutKey, int32& OutCellX, int32& OutCellY)
{
    int32 At = INDEX_NONE;
    if (!Key.FindLastChar(TEXT('@'), At)) return false;
    const FString Cell = Key.Mid(At + 1);
    FString X, Y;
    if (!Cell.Split(TEXT("_"), &X, &Y)) return false;
    OutKey = Key.Left(At);
    OutCellX = FCString::Atoi(*X);
    OutCellY = FCString::Atoi(*Y);
    return true;
}

void CellOf(const FVector& OriginCm, const FTransform& Placement, int32& OutCellX, int32& OutCellY)
{
    const FVector P = OriginCm + Placement.GetLocation();
    OutCellX = FMath::FloorToInt(P.X / 100.0 / PieceCellM);
    OutCellY = FMath::FloorToInt(-P.Y / 100.0 / PieceCellM);
}

TSharedPtr<FJsonObject> GondolaClearance()
{
    static TSharedPtr<FJsonObject> Cached;
    static FString CachedPath;
    const FString Path = AtelierDataPath(TEXT("gondola/runtime.json"));
    if (Cached.IsValid() && CachedPath == Path) return Cached;
    FString Raw;
    if (!FFileHelper::LoadFileToString(Raw, *Path)) return nullptr;
    // InClearance only reads clearance_segments_m / clearance_m (~20 KB); skip deserializing the 21 MB "lines" polylines.
    int32 LinesKey = Raw.Find(TEXT("\"lines\""), ESearchCase::CaseSensitive);
    if (LinesKey != INDEX_NONE)
    {
        int32 Colon = Raw.Find(TEXT(":"), ESearchCase::CaseSensitive, ESearchDir::FromStart, LinesKey + 7);
        int32 Open = Colon != INDEX_NONE ? Raw.Find(TEXT("["), ESearchCase::CaseSensitive, ESearchDir::FromStart, Colon + 1) : INDEX_NONE;
        if (Open != INDEX_NONE)
        {
            int32 Depth = 1, K = Open + 1;
            bool bInStr = false;
            while (K < Raw.Len() && Depth > 0)
            {
                const TCHAR C = Raw[K];
                if (bInStr) { if (C == TEXT('\\')) { K += 2; continue; } if (C == TEXT('"')) bInStr = false; }
                else { if (C == TEXT('"')) bInStr = true; else if (C == TEXT('[')) ++Depth; else if (C == TEXT(']')) --Depth; }
                ++K;
            }
            if (Depth == 0) Raw = Raw.Left(Open + 1) + Raw.Mid(K - 1);
        }
    }
    TSharedPtr<FJsonObject> Parsed;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw), Parsed) || !Parsed.IsValid()) return nullptr;
    CachedPath = Path;
    Cached = Parsed;
    return Cached;
}
}
