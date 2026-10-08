#include "AtelierSettings.h"
#include "HAL/PlatformFileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#endif

FString AtelierSettings::FilePath()
{
    FString File;
    if (FParse::Value(FCommandLine::Get(), TEXT("preferencesfile="), File) && !File.IsEmpty())
        return FPaths::ConvertRelativePathToFull(File);
    return FPaths::ProjectSavedDir() / TEXT("settings.txt");
}

TMap<FString, FString> AtelierSettings::ReadFile(const FString& Path)
{
    TMap<FString, FString> Result;
    TArray<FString> Lines;
    FFileHelper::LoadFileToStringArray(Lines, *Path);
    for (const FString& Line : Lines)
        if (FString K, V; Line.Split(TEXT("="), &K, &V)) Result.Add(K.TrimStartAndEnd(), V.TrimStartAndEnd());
    return Result;
}

TMap<FString, FString> AtelierSettings::Overrides()
{
    TMap<FString, FString> Result;
    FString Overrides;
    if (FParse::Value(FCommandLine::Get(), TEXT("set="), Overrides))
    {
        TArray<FString> Pairs; Overrides.ParseIntoArray(Pairs, TEXT(";"));
        for (const FString& Pair : Pairs) if (FString K, V; Pair.Split(TEXT("="), &K, &V)) Result.Add(K, V);
    }
    return Result;
}

bool AtelierSettings::WriteFile(const FString& Path, const TMap<FString, FString>& Values)
{
    TArray<FString> Keys; Values.GetKeys(Keys); Keys.Sort();
    FString Content;
    for (const FString& K : Keys) Content += K + TEXT("=") + Values[K] + TEXT("\n");
    // Flush a unique sibling first: an incomplete write must never truncate the previous settings.
    const FString Temporary = FPaths::CreateTempFilename(*FPaths::GetPath(Path), TEXT("settings-"));
    IPlatformFile& Files = FPlatformFileManager::Get().GetPlatformFile();
    bool Saved = FFileHelper::SaveStringToFile(Content, *Temporary, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    if (Saved)
    {
#if PLATFORM_WINDOWS
        // Windows's IPlatformFile::MoveFile does not replace existing files.
        const FString From = Files.ConvertToAbsolutePathForExternalAppForWrite(*Temporary);
        const FString To = Files.ConvertToAbsolutePathForExternalAppForWrite(*Path);
        Saved = ::MoveFileExW(*From, *To, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
        // Apple/Unix MoveFile uses rename(), which replaces a same-filesystem sibling atomically.
        // IFileManager::Move deletes the destination first, so it is unsafe for this operation.
        Saved = Files.MoveFile(*Path, *Temporary);
#endif
    }
    if (!Saved) Files.DeleteFile(*Temporary);
    return Saved;
}
