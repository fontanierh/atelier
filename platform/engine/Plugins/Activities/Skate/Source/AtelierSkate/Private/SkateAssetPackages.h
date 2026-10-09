#pragma once
#include "CoreMinimal.h"
#if WITH_EDITOR
#include "AssetRegistry/AssetRegistryModule.h"
#include "HAL/FileManager.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"

// Editor: the generated typed data packages (motion and runtime imports).
namespace SkateAssetPackages
{
// The asset at PackageName, loaded, or created in a new package.
template<class T> T* Asset(const FString& PackageName)
{
    const auto Name=FPackageName::GetLongPackageAssetName(PackageName);
    if(T* Existing=LoadObject<T>(nullptr,*(PackageName+TEXT(".")+Name)))return Existing;
    T* Out=NewObject<T>(CreatePackage(*PackageName),*Name,RF_Public|RF_Standalone);
    FAssetRegistryModule::AssetCreated(Out);return Out;
}
inline bool Save(UObject* Object,FString& Error)
{
    Object->MarkPackageDirty();FSavePackageArgs Args;Args.TopLevelFlags=RF_Public|RF_Standalone;
    const auto File=FPackageName::LongPackageNameToFilename(Object->GetOutermost()->GetName(),FPackageName::GetAssetPackageExtension());
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(File),true);
    if(!UPackage::SavePackage(Object->GetOutermost(),Object,*File,Args)) {Error=TEXT("Cannot save ")+File;return false;}
    return true;
}
}
#endif
