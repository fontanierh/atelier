#include "V2SaveGuard.h"

#include "Misc/CoreDelegates.h"
#include "Misc/FileHelper.h"
#include "Misc/OutputDevice.h"
#include "Misc/Paths.h"
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
FCoreUObjectDelegates::FIsPackageOKToSaveDelegate Previous;
FDelegateHandle PostInit;

FString Normalized(const FString& Filename)
{
    FString Full = FPaths::ConvertRelativePathToFull(Filename);
    FPaths::NormalizeFilename(Full);
    FPaths::CollapseRelativeDirectories(Full);
    return Full;
}

bool IsOKToSave(UPackage* Package, const FString& Filename, FOutputDevice* Error)
{
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

void UV2SaveGuard::Startup()
{
    bAllowList = ReadList(TEXT("V2_SAVE_ALLOW"), Allowed);
    const bool bDenyList = ReadList(TEXT("V2_SAVE_DENY"), Denied);
    if (!bAllowList && !bDenyList)
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
