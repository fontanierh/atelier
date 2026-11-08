#include "V2MigrationTowns.h"

#include "AtelierData.h"
#include "Dom/JsonObject.h"
#include "Misc/Paths.h"

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
    return AtelierReadJson(AtelierDataPath(TEXT("gondola/runtime.json")));
}
}
