#include "V2SaveGuard.h"

#include "Misc/CoreDelegates.h"
#include "Misc/FileHelper.h"
#include "Misc/OutputDevice.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"

namespace
{
bool bActive = false;
bool bInstalled = false;
bool bAllowList = false;   // an allow list is in force: only its files may be saved
bool bListsRead = true;    // false when a named list could not be read: nothing may be saved
TSet<FString> Allowed;
TSet<FString> Denied;
TArray<FString> RefusedFiles;
FString LoadedFrom;        // the lists' names, sizes and times when read: a warm batch names new ones per action
FCoreUObjectDelegates::FIsPackageOKToSaveDelegate Previous;
FDelegateHandle PostInit;

FString Normalized(const FString& Filename)
{
    FString Full = FPaths::ConvertRelativePathToFull(Filename);
    FPaths::NormalizeFilename(Full);
    FPaths::CollapseRelativeDirectories(Full);
    return Full;
}

void Refresh();

bool IsOKToSave(UPackage* Package, const FString& Filename, FOutputDevice* Error)
{
    Refresh();
    const FString Full = Normalized(Filename);
    const bool bRefused = !bListsRead || (bAllowList && !Allowed.Contains(Full)) || Denied.Contains(Full);
    if (bRefused)
    {
        RefusedFiles.AddUnique(Full);
        UE_LOG(LogTemp, Error, TEXT("V2 save guard: refused %s (outside V2_SAVE_ALLOW or in V2_SAVE_DENY)"), *Full);
        if (Error)
        {
            Error->Logf(ELogVerbosity::Error, TEXT("V2 save guard: %s is outside this run's authorized write set"), *Full);
        }
        return false;
    }
    return Previous.IsBound() ? Previous.Execute(Package, Filename, Error) : true;
}

void Install()
{
    // The editor engine binds its own check during init; keep it and run it after ours.
    Previous = FCoreUObjectDelegates::IsPackageOKToSaveDelegate;
    FCoreUObjectDelegates::IsPackageOKToSaveDelegate.BindStatic(&IsOKToSave);
    bInstalled = true;
    UE_LOG(LogTemp, Display, TEXT("V2 save guard active: %s, %d denied file(s)"),
           bAllowList ? *FString::Printf(TEXT("%d authorized file(s)"), Allowed.Num()) : TEXT("no allow list"),
           Denied.Num());
}
}

namespace
{
bool ReadList(const TCHAR* Variable, TSet<FString>& Into)
{
    const FString List = FPlatformMisc::GetEnvironmentVariable(Variable);
    if (List.IsEmpty())
    {
        return false;
    }
    TArray<FString> Lines;
    if (!FFileHelper::LoadFileToStringArray(Lines, *List))
    {
        bListsRead = false;
        return true;
    }
    for (const FString& Line : Lines)
    {
        const FString Trimmed = Line.TrimStartAndEnd();
        if (!Trimmed.IsEmpty())
        {
            Into.Add(Normalized(Trimmed));
        }
    }
    return true;
}
}

namespace
{
FString ListsKey()
{
    FString Key;
    for (const TCHAR* Variable : {TEXT("V2_SAVE_ALLOW"), TEXT("V2_SAVE_DENY")})
    {
        const FString List = FPlatformMisc::GetEnvironmentVariable(Variable);
        Key += List + TEXT("|") + (List.IsEmpty() ? FString() : IFileManager::Get().GetTimeStamp(*List).ToString() + TEXT("|")
            + LexToString(IFileManager::Get().FileSize(*List))) + TEXT("\n");
    }
    return Key;
}

/** Reads the lists the environment names now. One editor process may run several authorized actions (a warm
 *  batch sets each action's environment): each save is checked against its own action's lists, and once the guard
 *  is active an action naming no list may save nothing. */
void Refresh()
{
    const FString Key = ListsKey();
    if (Key == LoadedFrom)
    {
        return;
    }
    const bool bWasActive = bActive;
    Allowed.Reset();
    Denied.Reset();
    bListsRead = true;
    bAllowList = ReadList(TEXT("V2_SAVE_ALLOW"), Allowed);
    const bool bDenyList = ReadList(TEXT("V2_SAVE_DENY"), Denied);
    if (bWasActive && !bAllowList && !bDenyList)
    {
        bListsRead = false;
    }
    LoadedFrom = Key;
    if (bWasActive)
    {
        UE_LOG(LogTemp, Display, TEXT("V2 save guard: this action's lists: %s, %d denied file(s)%s"),
               bAllowList ? *FString::Printf(TEXT("%d authorized file(s)"), Allowed.Num()) : TEXT("no allow list"),
               Denied.Num(), bListsRead ? TEXT("") : TEXT("; no list named, every save refused"));
    }
}
}

void UV2SaveGuard::Startup()
{
    Refresh();
    if (!bAllowList && Denied.IsEmpty() && bListsRead && FPlatformMisc::GetEnvironmentVariable(TEXT("V2_SAVE_DENY")).IsEmpty())
    {
        return;
    }
    bActive = true;
    PostInit = FCoreDelegates::OnPostEngineInit.AddStatic(&Install);
}

void UV2SaveGuard::Shutdown()
{
    FCoreDelegates::OnPostEngineInit.Remove(PostInit);
    if (bInstalled)
    {
        FCoreUObjectDelegates::IsPackageOKToSaveDelegate = Previous;
        bInstalled = false;
    }
}

bool UV2SaveGuard::IsActive()
{
    return bActive && bInstalled;
}

int32 UV2SaveGuard::DeniedCount()
{
    return Denied.Num();
}

int32 UV2SaveGuard::AllowedCount()
{
    return Allowed.Num();
}

TArray<FString> UV2SaveGuard::Refused()
{
    return RefusedFiles;
}
