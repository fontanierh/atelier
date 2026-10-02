#include "SkateCollisionCommandlet.h"
#include "SkateCollisionBuilder.h"
#include "SkateCollisionAsset.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/AssetData.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Editor.h"
#include "FileHelpers.h"
#include "Misc/PackageName.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

USkateCollisionCommandlet::USkateCollisionCommandlet()
{IsClient=false;IsServer=false;IsEditor=true;LogToConsole=true;ShowErrorCount=true;}
int32 USkateCollisionCommandlet::Main(const FString& Params)
{
    FString Map,CatalogPackage=TEXT("/Game/SkateNative/DA_Collision"),Report,ExplicitMeshes,Roots;
    FParse::Value(*Params,TEXT("Map="),Map);FParse::Value(*Params,TEXT("Catalog="),CatalogPackage);
    FParse::Value(*Params,TEXT("Report="),Report);FParse::Value(*Params,TEXT("Meshes="),ExplicitMeshes);FParse::Value(*Params,TEXT("Roots="),Roots);
    const bool ValidateOnly=FParse::Param(*Params,TEXT("ValidateOnly"));
    TArray<FString> Errors,Warnings;UWorld* World=nullptr;
    if(!Map.IsEmpty())
    {
        FString Filename=Map;
        if(FPackageName::IsValidLongPackageName(Map))Filename=FPackageName::LongPackageNameToFilename(Map,FPackageName::GetMapPackageExtension());
        World=UEditorLoadingAndSavingUtils::LoadMap(Filename);
        if(!World)Errors.Add(TEXT("Could not load map ")+Map);
    }
    else if(GEditor)World=GEditor->GetEditorWorldContext().World();
    USkateCollisionAsset* Catalog=nullptr;
    if(Errors.IsEmpty())
    {
        if(ValidateOnly)
            Catalog=LoadObject<USkateCollisionAsset>(nullptr,*(CatalogPackage+TEXT(".")+FPackageName::GetLongPackageAssetName(CatalogPackage)));
        else if(!ExplicitMeshes.IsEmpty()||!Roots.IsEmpty())
        {
            TArray<UStaticMesh*> Meshes;TArray<FString> Paths;ExplicitMeshes.ParseIntoArray(Paths,TEXT(","),true);
            for(const FString& Path:Paths)
            {
                if(auto* Mesh=LoadObject<UStaticMesh>(nullptr,*Path))Meshes.AddUnique(Mesh);
                else Errors.Add(TEXT("Could not load collision mesh ")+Path);
            }
            if(!Roots.IsEmpty())
            {
                TArray<FString> FolderRoots;Roots.ParseIntoArray(FolderRoots,TEXT(","),true);
                auto& Registry=FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
                Registry.SearchAllAssets(true);TArray<FAssetData> Assets;
                Registry.GetAssetsByClass(UStaticMesh::StaticClass()->GetClassPathName(),Assets,true);
                for(const FAssetData& Asset:Assets)
                {
                    const FString Folder=Asset.PackagePath.ToString();
                    if(!FolderRoots.ContainsByPredicate([&](const FString& Root){return Folder==Root||Folder.StartsWith(Root+TEXT("/"));}))continue;
                    if(auto* Mesh=Cast<UStaticMesh>(Asset.GetAsset()))Meshes.AddUnique(Mesh);
                    else Errors.Add(TEXT("Could not load collision mesh ")+Asset.GetSoftObjectPath().ToString());
                }
            }
            if(Errors.IsEmpty())
            {
                TArray<FString> E,W;Catalog=USkateCollisionBuilderLibrary::BuildCatalog(Meshes,CatalogPackage,true,E,W);
                Errors.Append(E);Warnings.Append(W);
            }
        }
        else if(World)
        {
            TArray<FString> E,W;Catalog=USkateCollisionBuilderLibrary::BuildForWorld(World,CatalogPackage,true,E,W);
            Errors.Append(E);Warnings.Append(W);
        }
        else Errors.Add(TEXT("Supply -Map, -Meshes or -Roots to bake collision"));
        if(!Catalog&&Errors.IsEmpty())Errors.Add(TEXT("Missing collision catalog ")+CatalogPackage);
    }
    if(Catalog)
    {
        TArray<FString> E,W;USkateCollisionBuilderLibrary::ValidateCatalog(Catalog,true,E,W);Errors.Append(E);Warnings.Append(W);
        if(World){E.Reset();W.Reset();USkateCollisionBuilderLibrary::ValidateWorld(World,Catalog,E,W);Errors.Append(E);Warnings.Append(W);}
        if(Catalog->Meshes.IsEmpty())Errors.Add(TEXT("Catalog contains no baked meshes; an empty map is not validation coverage"));
    }
    for(const FString& Error:Errors)UE_LOG(LogTemp,Error,TEXT("SKATE COLLISION: %s"),*Error);
    for(const FString& Warning:Warnings)UE_LOG(LogTemp,Warning,TEXT("SKATE COLLISION: %s"),*Warning);
    if(!Report.IsEmpty())
    {
        auto Object=MakeShared<FJsonObject>();Object->SetBoolField(TEXT("success"),Errors.IsEmpty());Object->SetStringField(TEXT("catalog"),CatalogPackage);
        Object->SetStringField(TEXT("map"),Map);Object->SetNumberField(TEXT("baked_meshes"),Catalog?Catalog->Meshes.Num():0);
        Object->SetNumberField(TEXT("revision"),Catalog?Catalog->Revision:0);
        TArray<TSharedPtr<FJsonValue>> E,W;for(const auto& S:Errors)E.Add(MakeShared<FJsonValueString>(S));for(const auto& S:Warnings)W.Add(MakeShared<FJsonValueString>(S));
        Object->SetArrayField(TEXT("errors"),E);Object->SetArrayField(TEXT("warnings"),W);
        FString Text;auto Writer=TJsonWriterFactory<>::Create(&Text);FJsonSerializer::Serialize(Object,Writer);
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(Report),true);
        if(!FFileHelper::SaveStringToFile(Text,*Report)) {UE_LOG(LogTemp,Error,TEXT("Could not write collision report %s"),*Report);return 1;}
    }
    return Errors.IsEmpty()?0:1;
}
