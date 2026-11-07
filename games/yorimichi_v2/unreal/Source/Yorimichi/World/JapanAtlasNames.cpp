#include "JapanAtlasNames.h"
#include "Dom/JsonObject.h"
#include "HAL/PlatformFileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#endif

namespace
{
bool ValidName(const FString& Name)
{
    if (Name.IsEmpty() || Name.Len() > 48 || Name != Name.TrimStartAndEnd()) return false;
    for (TCHAR C : Name) if (C < 32 || C == 127) return false;
    return true;
}
bool ValidKey(const FString& Key)
{
    if (Key.IsEmpty() || Key.Len() > 64) return false;
    for (TCHAR C : Key) if (!(C >= 'a' && C <= 'z') && !(C >= '0' && C <= '9') && C != '_') return false;
    return true;
}
}

void FJapanAtlasNames::Load(const FString& ReviewFile)
{
    if (bLoaded) return;
    bLoaded = true;
    File = FPaths::ProjectSavedDir()/TEXT("stable-names.json");
    FString Preferences;
    if (FParse::Value(FCommandLine::Get(),TEXT("preferencesfile="),Preferences)) File = FPaths::GetPath(Preferences)/TEXT("stable-names.json");
    FParse::Value(FCommandLine::Get(),TEXT("atlasnamesfile="),File);
    if (!ReviewFile.IsEmpty()) File = ReviewFile;
    auto& Files = FPlatformFileManager::Get().GetPlatformFile();
    if (!Files.FileExists(*File)) return;
    FString Text; TSharedPtr<FJsonObject> Root; const TSharedPtr<FJsonObject>* Rows = nullptr; double Version = 0;
    bool Valid = Files.FileSize(*File) <= 65536 && FFileHelper::LoadFileToString(Text,*File)
        && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) && Root.IsValid()
        && Root->TryGetNumberField(TEXT("version"),Version) && Version == 1 && Root->TryGetObjectField(TEXT("names"),Rows)
        && (*Rows)->Values.Num() <= 128;
    TMap<FString,FString> Loaded;
    if (Valid) for (const auto& Row : (*Rows)->Values)
    {
        const FString Key(*Row.Key); FString Name;
        if (!ValidKey(Key) || !Row.Value.IsValid() || !Row.Value->TryGetString(Name) || !ValidName(Name)) { Valid = false; break; }
        Loaded.Add(Key,Name);
    }
    if (Valid) Names = MoveTemp(Loaded);
    else { bWritable = false; Error = TEXT("Stable names could not be read. The original save was preserved."); }
}

FString FJapanAtlasNames::Get(const FString& Key, const FString& Default) const
{
    const FString* Value = Names.Find(Key); return Value ? *Value : Default;
}

bool FJapanAtlasNames::Commit(const TMap<FString,FString>& Next)
{
    if (!bWritable) return false;
    auto Root = MakeShared<FJsonObject>(); auto Rows = MakeShared<FJsonObject>();
    Root->SetNumberField(TEXT("version"),1);
    for (const auto& Row : Next) Rows->SetStringField(Row.Key,Row.Value);
    Root->SetObjectField(TEXT("names"),Rows);
    FString Text; FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Text));
    auto& Files = FPlatformFileManager::Get().GetPlatformFile();
    const FString Dir = FPaths::GetPath(File), Temp = FPaths::CreateTempFilename(*Dir,TEXT("stable-names-"));
    bool Saved = Files.CreateDirectoryTree(*Dir) && FFileHelper::SaveStringToFile(Text,*Temp,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    if (Saved)
    {
#if PLATFORM_WINDOWS
        const FString From = Files.ConvertToAbsolutePathForExternalAppForWrite(*Temp), To = Files.ConvertToAbsolutePathForExternalAppForWrite(*File);
        Saved = ::MoveFileExW(*From,*To,MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
        Saved = Files.MoveFile(*File,*Temp);
#endif
    }
    if (!Saved) { Files.DeleteFile(*Temp); Error = TEXT("Could not save the stable name. Previous names are unchanged."); return false; }
    Names = Next; Error.Empty(); return true;
}

bool FJapanAtlasNames::Rename(const FString& Key, const FString& Input)
{
    Load(); const FString Name = Input.TrimStartAndEnd();
    if (!ValidKey(Key) || !ValidName(Name)) { Error = TEXT("Use a name of 1 to 48 characters, without control characters."); return false; }
    auto Next = Names; Next.Add(Key,Name);
    if (Next.Num() > 128) { Error = TEXT("Too many stable names saved."); return false; }
    return Commit(Next);
}

bool FJapanAtlasNames::Reset(const FString& Key)
{
    Load(); auto Next = Names; Next.Remove(Key); return Commit(Next);
}
