// SPDX-License-Identifier: Apache-2.0
#include "SkateRuntimeAssetLibrary.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Containers/StringConv.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/LinkerInstancingContext.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UObjectGlobals.h"
#include <filesystem>

namespace
{
std::filesystem::path NativePath(const FString& Path)
{const FTCHARToUTF8 Text(*Path,Path.Len());return std::filesystem::u8path(Text.Get(),Text.Get()+Text.Length());}

FString UnrealPath(const std::filesystem::path& Path)
{
    const auto Bytes=Path.u8string();
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Bytes.data()),static_cast<int32>(Bytes.size()));
    return FString(Text.Length(),Text.Get());
}

bool IsWithin(const std::filesystem::path& Root,const std::filesystem::path& Path)
{
    auto Candidate=Path.begin();
    for(auto Part=Root.begin();Part!=Root.end();++Part,++Candidate)
        if(Candidate==Path.end() || *Part!=*Candidate)return false;
    return true;
}

void CopyData(const USkateRuntimeAsset& Source,USkateRuntimeAsset& Destination)
{
    Destination.Version=Source.Version;Destination.ExpectedRecordCount=Source.ExpectedRecordCount;
    Destination.ManifestBytes=Source.ManifestBytes;Destination.ManifestSha256=Source.ManifestSha256;
    Destination.SourceIdentity=Source.SourceIdentity;Destination.Records=Source.Records;
}

void AppendIssues(FSkateRuntimeAssetValidationReport& Report,const FSkateRuntimeAssetValidationReport& Other,
    const FString& Prefix)
{for(const auto& Issue:Other.Issues)Report.Issues.Add(Prefix+Issue);}

bool CompareSaved(const USkateRuntimeAsset& Source,const FString& Filename,FSkateRuntimeAssetValidationReport& Report)
{
    // Load the actual saved package under a distinct identity, rather than
    // resolving the still-resident authoring object through LoadObject.
    const FString InstanceName=TEXT("/Temp/SkateRuntimeValidation_")+FGuid::NewGuid().ToString(EGuidFormats::Digits);
    TStrongObjectPtr<UPackage> Instance(CreatePackage(*InstanceName));
    FLinkerInstancingContext Context;
    Context.AddPackageMapping(Source.GetOutermost()->GetFName(),Instance->GetFName());
    UPackage* Loaded=LoadPackage(Instance.Get(),*Filename,LOAD_DisableCompileOnLoad,nullptr,&Context);
    USkateRuntimeAsset* Reloaded=Loaded?FindObject<USkateRuntimeAsset>(Loaded,*Source.GetName()):nullptr;
    if(!Reloaded || Reloaded==&Source)
    {Report.Issues.Add(TEXT("Saved runtime asset could not be independently reloaded"));return false;}
    const auto Validation=Reloaded->Validate(false);
    AppendIssues(Report,Validation,TEXT("Saved asset: "));
    bool bEqual=true;
    if(Reloaded->Version!=Source.Version || Reloaded->ExpectedRecordCount!=Source.ExpectedRecordCount
        || Reloaded->ManifestBytes!=Source.ManifestBytes || Reloaded->ManifestSha256!=Source.ManifestSha256
        || Reloaded->SourceIdentity!=Source.SourceIdentity)
    {Report.Issues.Add(TEXT("Saved asset manifest or identity changed during serialization"));bEqual=false;}
    if(Reloaded->Records.Num()!=Source.Records.Num())
    {Report.Issues.Add(TEXT("Saved asset record count changed during serialization"));bEqual=false;}
    const int32 Common=FMath::Min(Reloaded->Records.Num(),Source.Records.Num());
    for(int32 Index=0;Index<Common;++Index)
    {
        const auto& Before=Source.Records[Index];const auto& After=Reloaded->Records[Index];
        if(!Before.RelativePath.Equals(After.RelativePath,ESearchCase::CaseSensitive)
            || !Before.Sha256.Equals(After.Sha256,ESearchCase::CaseSensitive) || Before.Payload!=After.Payload)
        {
            Report.Issues.Add(FString::Printf(TEXT("Saved asset record %d changed: %s"),Index,*Before.RelativePath));
            bEqual=false;
        }
    }
    Reloaded->ClearFlags(RF_Public|RF_Standalone);Instance->SetFlags(RF_Transient);
    return bEqual && Validation.bValid;
}
}

FSkateRuntimeAssetValidationReport USkateRuntimeAssetLibrary::ValidateRuntimeAsset(const USkateRuntimeAsset* Asset,
    bool bCheckDecodedPayloads)
{
    if(Asset)return Asset->Validate(bCheckDecodedPayloads);
    FSkateRuntimeAssetValidationReport Report;Report.Issues.Add(TEXT("Runtime asset is not loaded"));return Report;
}

FSkateRuntimeAssetValidationReport USkateRuntimeAssetLibrary::ValidateResourceEquivalence(const USkateRuntimeAsset* Asset,
    const FString& BundleDirectory,int32 TicksPerStance)
{
    if(Asset)return Asset->ValidateSourceEquivalence(BundleDirectory,TicksPerStance);
    FSkateRuntimeAssetValidationReport Report;Report.Issues.Add(TEXT("Runtime asset is not loaded"));return Report;
}

FSkateRuntimeAssetValidationReport USkateRuntimeAssetLibrary::BuildRuntimeAsset(const FString& BundleDirectory,
    const FString& AssetPath,const FString& ExpectedManifestSha256,int32 ExpectedRecordCount)
{
    FSkateRuntimeAssetValidationReport Report;
    Report.AssetPath=AssetPath;
    if(!IsInGameThread()){Report.Issues.Add(TEXT("Runtime asset building requires the game thread"));return Report;}
    FString PackageName=AssetPath;
    FString ObjectName;
    int32 Dot=INDEX_NONE;
    if(AssetPath.FindChar(TEXT('.'),Dot))
    {
        PackageName=AssetPath.Left(Dot);ObjectName=AssetPath.Mid(Dot+1);
        if(ObjectName!=FPackageName::GetLongPackageAssetName(PackageName))
            Report.Issues.Add(TEXT("Runtime asset object name must match its package name"));
    }
    else ObjectName=FPackageName::GetLongPackageAssetName(PackageName);
    FText PathError;
    if(!PackageName.StartsWith(TEXT("/Game/"),ESearchCase::CaseSensitive)
        || !FPackageName::IsValidLongPackageName(PackageName,false,&PathError))
        Report.Issues.Add(TEXT("Runtime asset requires a writable /Game package path"));
    if(!USkateRuntimeAsset::IsSha256(ExpectedManifestSha256))
        Report.Issues.Add(TEXT("Expected manifest SHA-256 must contain 64 lowercase hexadecimal characters"));
    if(ExpectedRecordCount<=0)Report.Issues.Add(TEXT("Expected runtime asset record count must be positive"));
    if(!Report.Issues.IsEmpty())return Report;

    std::error_code Ec;
    const auto Root=std::filesystem::canonical(NativePath(BundleDirectory),Ec);
    if(Ec || !std::filesystem::is_directory(Root,Ec) || Ec)
    {Report.Issues.Add(TEXT("Native source bundle directory is unavailable"));return Report;}
    TStrongObjectPtr<USkateRuntimeAsset> Candidate(NewObject<USkateRuntimeAsset>(GetTransientPackage()));
    Candidate->ExpectedRecordCount=ExpectedRecordCount;
    const auto ManifestPath=Root/"package-manifest.json";
    const auto CanonicalManifest=std::filesystem::canonical(ManifestPath,Ec);
    if(Ec || !IsWithin(Root,CanonicalManifest))
    {Report.Issues.Add(TEXT("Source manifest is missing or escapes the source bundle directory"));return Report;}
    const FString ManifestFilename=UnrealPath(CanonicalManifest);
    if(!FFileHelper::LoadFileToArray(Candidate->ManifestBytes,*ManifestFilename))
    {Report.Issues.Add(TEXT("Cannot read source package-manifest.json"));return Report;}
    Candidate->ManifestSha256=USkateRuntimeAsset::HashPayload(Candidate->ManifestBytes);
    if(Candidate->ManifestSha256!=ExpectedManifestSha256)
        Report.Issues.Add(TEXT("Source manifest differs from the expected SHA-256"));
    for(uint8 Byte:Candidate->ManifestBytes)if(Byte==0 || Byte>127)
    {Report.Issues.Add(TEXT("Source manifest must contain ASCII JSON without NUL bytes"));return Report;}
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Candidate->ManifestBytes.GetData()),Candidate->ManifestBytes.Num());
    const FString Json(Text.Length(),Text.Get());
    TSharedPtr<FJsonObject> Manifest;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Manifest) || !Manifest.IsValid())
    {Report.Issues.Add(TEXT("Invalid source package manifest JSON"));return Report;}
    if(!Manifest->TryGetStringField(TEXT("source_identity"),Candidate->SourceIdentity))
        Report.Issues.Add(TEXT("Source manifest has no source identity"));
    const TSharedPtr<FJsonObject>* Files=nullptr;
    if(!Manifest->TryGetObjectField(TEXT("files"),Files))
    {Report.Issues.Add(TEXT("Source manifest has no files object"));return Report;}
    TArray<FString> Names;
    Names.Reserve((*Files)->Values.Num());
    for(const auto& Pair:(*Files)->Values)
        Names.Add(FString::ConstructFromPtrSize(*Pair.Key,Pair.Key.Len()));
    Names.Sort([](const FString& A,const FString& B){return A.Compare(B,ESearchCase::CaseSensitive)<0;});
    Candidate->Records.Reserve(Names.Num());
    for(const FString& Name:Names)
    {
        auto& Record=Candidate->Records.AddDefaulted_GetRef();Record.RelativePath=Name;
        const auto Value=(*Files)->TryGetField(Name);
        const auto Spec=Value.IsValid() && Value->Type==EJson::Object?Value->AsObject():nullptr;
        if(!Spec.IsValid() || !Spec->TryGetStringField(TEXT("sha256"),Record.Sha256))
            Report.Issues.Add(TEXT("Missing source manifest record SHA-256: ")+Name);
        if(!USkateRuntimeAsset::IsValidRelativePath(Name))
        {Report.Issues.Add(TEXT("Unsafe source resource path: ")+Name);continue;}
        const auto Path=std::filesystem::canonical(Root/NativePath(Name),Ec);
        if(Ec || !IsWithin(Root,Path))
        {Report.Issues.Add(TEXT("Source resource is missing or escapes its bundle: ")+Name);continue;}
        const FString Filename=UnrealPath(Path);
        if(!FFileHelper::LoadFileToArray(Record.Payload,*Filename))
            Report.Issues.Add(TEXT("Cannot read source resource: ")+Name);
    }
    const auto Validation=Candidate->Validate(true);
    AppendIssues(Report,Validation,TEXT(""));
    Report.RecordCount=Validation.RecordCount;Report.ClipCount=Validation.ClipCount;
    Report.PayloadBytes=Validation.PayloadBytes;Report.ManifestSha256=Validation.ManifestSha256;
    Report.SourceIdentity=Validation.SourceIdentity;Report.bSemanticLoadSucceeded=Validation.bSemanticLoadSucceeded;
    if(!Report.Issues.IsEmpty())return Report;
    // Compare real sessions before replacing an existing asset. The same
    // file-source entry point remains available to the standalone CLI.
    const auto Equivalence=Candidate->ValidateSourceEquivalence(BundleDirectory,120);
    AppendIssues(Report,Equivalence,TEXT(""));
    Report.bFileAssetEquivalent=Equivalence.bFileAssetEquivalent;Report.ComparedTicks=Equivalence.ComparedTicks;
    Report.FileWordSha256=Equivalence.FileWordSha256;Report.AssetWordSha256=Equivalence.AssetWordSha256;
    Report.bSnapshotIntegrityVerified=Equivalence.bSnapshotIntegrityVerified;
    Report.bChecksumCorruptionRejected=Equivalence.bChecksumCorruptionRejected;
    Report.bSnapshotOutputRetained=Equivalence.bSnapshotOutputRetained;
    Report.bSnapshotImmutable=Equivalence.bSnapshotImmutable;
    Report.IntegrityChecks=Equivalence.IntegrityChecks;
    Report.IntegrityChecksPassed=Equivalence.IntegrityChecksPassed;
    if(!Report.Issues.IsEmpty())return Report;

    FString Filename;
    if(!FPackageName::TryConvertLongPackageNameToFilename(PackageName,Filename,FPackageName::GetAssetPackageExtension()))
    {Report.Issues.Add(TEXT("Cannot resolve runtime asset package filename"));return Report;}
    UPackage* Package=CreatePackage(*PackageName);Package->FullyLoad();
    UObject* Existing=FindObject<UObject>(Package,*ObjectName);
    if(Existing && !Existing->IsA<USkateRuntimeAsset>())
    {Report.Issues.Add(TEXT("Runtime asset path is occupied by another asset class"));return Report;}
    USkateRuntimeAsset* Asset=Existing?CastChecked<USkateRuntimeAsset>(Existing):
        NewObject<USkateRuntimeAsset>(Package,*ObjectName,RF_Public|RF_Standalone);
    TStrongObjectPtr<USkateRuntimeAsset> Previous;
    if(Existing)
    {Previous.Reset(NewObject<USkateRuntimeAsset>(GetTransientPackage()));CopyData(*Asset,*Previous);}
    CopyData(*Candidate,*Asset);
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename),true);
    FSavePackageArgs Args;Args.TopLevelFlags=RF_Public|RF_Standalone;Args.bSlowTask=false;
    Report.bSaved=UPackage::SavePackage(Package,Asset,*Filename,Args);
    if(!Report.bSaved)
    {
        Report.Issues.Add(TEXT("Cannot save runtime asset package"));
        if(Previous.IsValid())CopyData(*Previous,*Asset);
        else Asset->ClearFlags(RF_Public|RF_Standalone);
        return Report;
    }
    if(!Existing)FAssetRegistryModule::AssetCreated(Asset);
    Report.AssetPath=Asset->GetPathName();
    Report.bRoundTripVerified=CompareSaved(*Asset,Filename,Report);
    Report.bValid=Report.Issues.IsEmpty() && Report.bRoundTripVerified && Report.bFileAssetEquivalent;
    return Report;
}
