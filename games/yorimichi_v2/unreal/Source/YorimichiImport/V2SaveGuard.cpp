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
TSet<FString> Allowed;
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
    if (!Allowed.Contains(Full))
    {
        RefusedFiles.AddUnique(Full);
        UE_LOG(LogTemp, Error, TEXT("V2 save guard: refused %s (not in V2_SAVE_ALLOW)"), *Full);
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
    UE_LOG(LogTemp, Display, TEXT("V2 save guard active: %d authorized file(s)"), Allowed.Num());
}
}

void UV2SaveGuard::Startup()
{
    const FString List = FPlatformMisc::GetEnvironmentVariable(TEXT("V2_SAVE_ALLOW"));
    if (List.IsEmpty())
    {
        return;
    }
    bActive = true;   // from here an unreadable or empty list admits nothing
    TArray<FString> Lines;
    if (FFileHelper::LoadFileToStringArray(Lines, *List))
    {
        for (const FString& Line : Lines)
        {
            const FString Trimmed = Line.TrimStartAndEnd();
            if (!Trimmed.IsEmpty())
            {
                Allowed.Add(Normalized(Trimmed));
            }
        }
    }
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

int32 UV2SaveGuard::AllowedCount()
{
    return Allowed.Num();
}

TArray<FString> UV2SaveGuard::Refused()
{
    return RefusedFiles;
}
