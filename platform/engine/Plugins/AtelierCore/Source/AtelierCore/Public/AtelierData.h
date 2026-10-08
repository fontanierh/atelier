#pragma once

#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

/** Runtime data a game's build stages into Content/Data (layouts, maps, per-character runtime files). Packaged as loose
 *  files: add `+DirectoriesToAlwaysStageAsNonUFS=(Path="Data")` to the game's DefaultGame.ini. */
inline FString AtelierDataPath(const FString& Relative)
{
    return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Data") / Relative);
}

/** The JSON object in a file (AtelierReadJson(AtelierDataPath(TEXT("world.json")))), or null when the file is missing or
 *  does not hold an object. */
inline TSharedPtr<FJsonObject> AtelierReadJson(const FString& Path)
{
    FString Text;
    TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text, *Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root))
        return nullptr;
    return Root;
}
