#include "JapanMarkers.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/FileManager.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#endif

namespace
{
constexpr int32 MaxMarkers = 64;
constexpr int32 MaxNameLength = 48;
bool CleanName(const FString& Name)
{
    if (Name.IsEmpty() || Name.Len() > MaxNameLength) return false;
    for (TCHAR C : Name) if (C < 32 || C == 127) return false;
    return true;
}
}

void FJapanMarkers::Load()
{
    if (bLoaded) return;
    bLoaded = true;
    File = FPaths::ProjectSavedDir()/TEXT("markers.json");
    FString Preferences;
    if (FParse::Value(FCommandLine::Get(),TEXT("preferencesfile="),Preferences))
        File = FPaths::GetPath(Preferences)/TEXT("markers.json");
    // Review games use a private save rather than modifying the player's locations.
    FParse::Value(FCommandLine::Get(),TEXT("markersave="),File);
    IPlatformFile& Files = FPlatformFileManager::Get().GetPlatformFile();
    if (!Files.FileExists(*File)) return;
    FString Text; TSharedPtr<FJsonObject> Root;
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    double Version = 0;
    TArray<FJapanMarker> Loaded;
    FString Selection;
    bool Valid = Files.FileSize(*File) <= 1024*1024 && FFileHelper::LoadFileToString(Text,*File)
        && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) && Root.IsValid()
        && Root->TryGetNumberField(TEXT("version"),Version) && Version == 1
        && Root->TryGetArrayField(TEXT("markers"),Rows) && Rows->Num() <= MaxMarkers
        && Root->TryGetStringField(TEXT("selected"),Selection);
    if (Valid) for (const auto& Value : *Rows)
    {
        const TSharedPtr<FJsonObject>* Row = nullptr;
        FJapanMarker Marker; FGuid Id; double X,Y,Z,Yaw;
        Valid = Value.IsValid() && Value->TryGetObject(Row) && (*Row)->TryGetStringField(TEXT("id"),Marker.Key)
            && Marker.Key.StartsWith(TEXT("marker_")) && FGuid::ParseExact(Marker.Key.Mid(7),EGuidFormats::Digits,Id)
            && (*Row)->TryGetStringField(TEXT("name"),Marker.Name) && CleanName(Marker.Name)
            && (*Row)->TryGetNumberField(TEXT("x"),X) && (*Row)->TryGetNumberField(TEXT("y"),Y)
            && (*Row)->TryGetNumberField(TEXT("z"),Z) && (*Row)->TryGetNumberField(TEXT("yaw"),Yaw)
            && FMath::IsFinite(X) && FMath::IsFinite(Y) && FMath::IsFinite(Z) && FMath::IsFinite(Yaw)
            && FMath::Abs(X)<1.e8 && FMath::Abs(Y)<1.e8 && FMath::Abs(Z)<1.e8 && FMath::Abs(Yaw)<1.e6
            && !Loaded.ContainsByPredicate([&](const FJapanMarker& Prior) { return Prior.Key == Marker.Key || Prior.Name.Equals(Marker.Name,ESearchCase::IgnoreCase); });
        if (!Valid) break;
        Marker.Ground = FTransform(FRotator(0,FMath::UnwindDegrees(Yaw),0),FVector(X,Y,Z));
        Loaded.Add(MoveTemp(Marker));
    }
    Valid = Valid && (Loaded.IsEmpty() ? Selection.IsEmpty() : Loaded.ContainsByPredicate([&](const FJapanMarker& M) { return M.Key == Selection; }));
    if (!Valid)
    {
        bWritable = false;
        Error = TEXT("Saved markers could not be read. The save was preserved; restore markers.json before saving new places.");
        UE_LOG(LogTemp,Warning,TEXT("MARKERS invalid save preserved: %s"),*File);
        return;
    }
    Markers = MoveTemp(Loaded); SelectedKey = Selection;
    UE_LOG(LogTemp,Display,TEXT("MARKERS loaded %d saved places"),Markers.Num());
}

const FJapanMarker* FJapanMarkers::Selected() const
{
    return Markers.FindByPredicate([this](const FJapanMarker& M) { return M.Key == SelectedKey; });
}

FString FJapanMarkers::NextName() const
{
    for (int32 I=1;;++I)
    {
        FString Name = FString::Printf(TEXT("Marker %d"),I);
        if (!Markers.ContainsByPredicate([&](const FJapanMarker& M) { return M.Name.Equals(Name,ESearchCase::IgnoreCase); })) return Name;
    }
}

bool FJapanMarkers::NameValid(const FString& Name)
{
    if (!CleanName(Name)) { Error = TEXT("Give the marker a name of 1 to 48 characters."); return false; }
    return true;
}

bool FJapanMarkers::Commit(TArray<FJapanMarker> Next, const FString& Selected)
{
    if (!bWritable) return false;
    auto Root = MakeShared<FJsonObject>();
    Root->SetNumberField(TEXT("version"),1); Root->SetStringField(TEXT("selected"),Selected);
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (const auto& M : Next)
    {
        auto Row = MakeShared<FJsonObject>(); const FVector P = M.Ground.GetLocation();
        Row->SetStringField(TEXT("id"),M.Key); Row->SetStringField(TEXT("name"),M.Name);
        Row->SetNumberField(TEXT("x"),P.X); Row->SetNumberField(TEXT("y"),P.Y); Row->SetNumberField(TEXT("z"),P.Z);
        Row->SetNumberField(TEXT("yaw"),M.Ground.Rotator().Yaw);
        Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("markers"),Rows);
    FString Text;
    FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Text));
    IPlatformFile& Files = FPlatformFileManager::Get().GetPlatformFile();
    const FString Dir = FPaths::GetPath(File);
    const FString Temp = FPaths::CreateTempFilename(*Dir,TEXT("markers-"));
    bool Saved = Files.CreateDirectoryTree(*Dir) && FFileHelper::SaveStringToFile(Text,*Temp,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    if (Saved)
    {
#if PLATFORM_WINDOWS
        const FString From = Files.ConvertToAbsolutePathForExternalAppForWrite(*Temp);
        const FString To = Files.ConvertToAbsolutePathForExternalAppForWrite(*File);
        Saved = ::MoveFileExW(*From,*To,MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
        Saved = Files.MoveFile(*File,*Temp);
#endif
    }
    if (!Saved)
    {
        Files.DeleteFile(*Temp);
        Error = TEXT("Could not save markers. Your previous saved places are unchanged.");
        UE_LOG(LogTemp,Warning,TEXT("MARKERS save failed; previous save preserved: %s"),*File);
        return false;
    }
    Markers = MoveTemp(Next); SelectedKey = Selected; Error.Empty();
    UE_LOG(LogTemp,Display,TEXT("MARKERS saved %d places"),Markers.Num());
    return true;
}

bool FJapanMarkers::Add(const FString& Input, const FTransform& Ground)
{
    Load(); const FString Name = Input.TrimStartAndEnd();
    if (!NameValid(Name)) return false;
    if (Markers.Num() >= MaxMarkers) { Error = TEXT("64 markers saved. Delete a place before saving another."); return false; }
    if (Markers.ContainsByPredicate([&](const FJapanMarker& M) { return M.Name.Equals(Name,ESearchCase::IgnoreCase); }))
    { Error = TEXT("That marker name is already saved. Choose another name."); return false; }
    auto Next = Markers; const FString Key = TEXT("marker_")+FGuid::NewGuid().ToString(EGuidFormats::Digits);
    Next.Add({Key,Name,Ground}); return Commit(MoveTemp(Next),Key);
}

bool FJapanMarkers::Select(const FString& Key)
{
    Load();
    if (!Markers.ContainsByPredicate([&](const FJapanMarker& M) { return M.Key == Key; })) return false;
    return Key == SelectedKey || Commit(Markers,Key);
}

bool FJapanMarkers::Rename(const FString& Input)
{
    Load(); const FString Name = Input.TrimStartAndEnd();
    if (!Selected() || !NameValid(Name)) return false;
    if (Markers.ContainsByPredicate([&](const FJapanMarker& M) { return M.Key != SelectedKey && M.Name.Equals(Name,ESearchCase::IgnoreCase); }))
    { Error = TEXT("That marker name is already saved. Choose another name."); return false; }
    auto Next = Markers;
    for (auto& M : Next) if (M.Key == SelectedKey) M.Name = Name;
    return Commit(MoveTemp(Next),SelectedKey);
}

bool FJapanMarkers::Delete()
{
    Load(); if (!Selected()) return false;
    auto Next = Markers; Next.RemoveAll([this](const FJapanMarker& M) { return M.Key == SelectedKey; });
    const FString Selection = Next.IsEmpty() ? FString() : Next.Last().Key;
    return Commit(MoveTemp(Next),Selection);
}
