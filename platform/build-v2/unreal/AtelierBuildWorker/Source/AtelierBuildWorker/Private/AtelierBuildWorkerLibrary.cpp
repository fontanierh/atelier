#include "AtelierBuildWorkerLibrary.h"

#include "AssetCompilingManager.h"
#include "HAL/FileManager.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "DerivedDataCacheInterface.h"
#include "DerivedDataCacheUsageStats.h"
#include "Editor.h"
#include "Editor/Transactor.h"
#include "Engine/Selection.h"
#include "InterchangeManager.h"
#include "Misc/CoreDelegates.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/CoreMisc.h"
#include "Misc/FileHelper.h"
#include "Misc/SecureHash.h"
#include "UObject/ReferenceChainSearch.h"
#include "UObject/UObjectHash.h"
#include "Dom/JsonObject.h"
#include "HAL/IConsoleManager.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Modules/ModuleManifest.h"
#include "RHIGlobals.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "ShaderCompiler.h"
#include "Serialization/ArchiveProxy.h"

#include <sys/stat.h>
#include "UObject/ObjectResource.h"
#include "UObject/ObjectSaveContext.h"
#include "UObject/PackageFileSummary.h"
#include "UObject/Package.h"
#include "UObject/UObjectIterator.h"
#include "UObject/UObjectGlobals.h"

namespace
{
    struct FSaved
    {
        FString Package;
        FString Filename;
        /** SHA1 of each file this save wrote, taken after the save's writes were flushed. */
        TMap<FString, FString> Files;
    };

    /** Files a save may write beside its target `.uasset` or `.umap`; the other main extension never is one. */
    const TCHAR* const GCompanionExtensions[] = {TEXT(".uexp"), TEXT(".ubulk"), TEXT(".uptnl")};

    /** Which file is at a path: a save writes a temporary file and moves it into place. */
    struct FStamp
    {
        bool bExists = false;
        uint64 Device = 0;
        uint64 Inode = 0;
        int64 Size = 0;
        int64 Seconds = 0;
        int64 Nanoseconds = 0;

        bool operator==(const FStamp& Other) const
        {
            return bExists == Other.bExists && Device == Other.Device && Inode == Other.Inode && Size == Other.Size
                && Seconds == Other.Seconds && Nanoseconds == Other.Nanoseconds;
        }
    };

    FStamp StampOf(const FString& File)
    {
        struct stat Info;
        FStamp Stamp;
        if (::stat(TCHAR_TO_UTF8(*File), &Info) != 0 || !S_ISREG(Info.st_mode))
        {
            return Stamp;
        }
        Stamp.bExists = true;
        Stamp.Device = static_cast<uint64>(Info.st_dev);
        Stamp.Inode = static_cast<uint64>(Info.st_ino);
        Stamp.Size = static_cast<int64>(Info.st_size);
#if PLATFORM_APPLE
        Stamp.Seconds = static_cast<int64>(Info.st_mtimespec.tv_sec);
        Stamp.Nanoseconds = static_cast<int64>(Info.st_mtimespec.tv_nsec);
#else
        Stamp.Seconds = static_cast<int64>(Info.st_mtim.tv_sec);
        Stamp.Nanoseconds = static_cast<int64>(Info.st_mtim.tv_nsec);
#endif
        return Stamp;
    }

    TArray<FSaved> GSaved;
    /** Each companion path's stamp just before the save that targets its package. */
    TMap<FString, FStamp> GBefore;
    FDelegateHandle GPreSaveHandle;
    FDelegateHandle GSaveHandle;
    FDelegateHandle GEnsureHandle;
    int32 GEnsures = 0;

    void OnPackagePreSave(UPackage*, FObjectPreSaveContext Context)
    {
        const FString Target = Context.GetTargetFilename();
        if (Target.IsEmpty())
        {
            return;
        }
        UPackage::WaitForAsyncFileWrites();
        const FString Base = FPaths::ChangeExtension(FPaths::ConvertRelativePathToFull(Target), FString());
        for (const TCHAR* Extension : GCompanionExtensions)
        {
            GBefore.Add(Base + Extension, StampOf(Base + Extension));
        }
    }

    void HashInto(TMap<FString, FString>& Files, const FString& File)
    {
        TArray<uint8> Bytes;
        if (FPaths::FileExists(File) && FFileHelper::LoadFileToArray(Bytes, *File))
        {
            Files.Add(File, FSHA1::HashBuffer(Bytes.GetData(), Bytes.Num()).ToString().ToLower());
        }
    }

    void OnPackageSaved(const FString& PackageFileName, UPackage* Package, FObjectPostSaveContext)
    {
        FSaved Saved{Package ? Package->GetName() : FString(), FPaths::ConvertRelativePathToFull(PackageFileName), {}};
        // The event can fire before the package's file writes finish; hash only flushed bytes.
        UPackage::WaitForAsyncFileWrites();
        // Only the files this save wrote: its target, and each companion it created or replaced.
        // A file already there that the save left alone (a plain write beside it, or the other
        // main extension) is never certified as saved.
        HashInto(Saved.Files, Saved.Filename);
        const FString Base = FPaths::ChangeExtension(Saved.Filename, FString());
        for (const TCHAR* Extension : GCompanionExtensions)
        {
            const FString File = Base + Extension;
            FStamp Before;
            const bool bSeen = GBefore.RemoveAndCopyValue(File, Before);
            const FStamp After = StampOf(File);
            if (bSeen && After.bExists && !(After == Before))
            {
                HashInto(Saved.Files, File);
            }
        }
        GSaved.Add(MoveTemp(Saved));
    }

    /** Reads names through a package file's own name map, as its linker would. */
    class FNameMapReader : public FArchiveProxy
    {
    public:
        FNameMapReader(FArchive& Inner, const TArray<FName>& InNames) : FArchiveProxy(Inner), Names(InNames) {}

        virtual FArchive& operator<<(FName& Name) override
        {
            int32 Index = 0;
            int32 Number = 0;
            InnerArchive << Index << Number;
            if (!Names.IsValidIndex(Index))
            {
                SetError();
                Name = NAME_None;
                return *this;
            }
            Name = FName(Names[Index], Number);
            return *this;
        }

    private:
        const TArray<FName>& Names;
    };

    /** The import table of a saved package file, or false when the file cannot be read as one. */
    bool ReadImportTable(const FString& Filename, TArray<FObjectImport>& OutImports)
    {
        const TUniquePtr<FArchive> File(IFileManager::Get().CreateFileReader(*Filename));
        if (!File)
        {
            return false;
        }
        FPackageFileSummary Summary;
        *File << Summary;
        if (File->IsError() || Summary.Tag != PACKAGE_FILE_TAG || Summary.NameCount < 0 || Summary.ImportCount < 0)
        {
            return false;
        }
        File->SetUEVer(Summary.GetFileVersionUE());
        File->SetLicenseeUEVer(Summary.GetFileVersionLicenseeUE());
        File->SetCustomVersions(Summary.GetCustomVersionContainer());
        TArray<FName> Names;
        File->Seek(Summary.NameOffset);
        for (int32 Index = 0; Index < Summary.NameCount && !File->IsError(); ++Index)
        {
            FNameEntrySerialized Entry(ENAME_LinkerConstructor);
            *File << Entry;
            Names.Add(FName(Entry));
        }
        FNameMapReader Reader(*File, Names);
        Reader.SetUEVer(Summary.GetFileVersionUE());
        Reader.SetLicenseeUEVer(Summary.GetFileVersionLicenseeUE());
        Reader.SetCustomVersions(Summary.GetCustomVersionContainer());
        Reader.Seek(Summary.ImportOffset);
        OutImports.SetNum(Summary.ImportCount);
        for (FObjectImport& Import : OutImports)
        {
            Reader << Import;
        }
        if (File->IsError() || Reader.IsError())
        {
            return false;
        }
        for (const FObjectImport& Import : OutImports)
        {
            if (Import.OuterIndex.IsExport() || (Import.OuterIndex.IsImport() && !OutImports.IsValidIndex(Import.OuterIndex.ToImport())))
            {
                return false;
            }
        }
        return true;
    }

    FString Write(const TSharedRef<FJsonValue>& Value)
    {
        FString Text;
        const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
        FJsonSerializer::Serialize(Value, FString(), Writer);
        return Text;
    }

    TSharedRef<FJsonValue> Strings(const TArray<FString>& Values)
    {
        TArray<TSharedPtr<FJsonValue>> Items;
        for (const FString& Value : Values)
        {
            Items.Add(MakeShared<FJsonValueString>(Value));
        }
        return MakeShared<FJsonValueArray>(Items);
    }
}

FString UAtelierBuildWorkerLibrary::NativeContext()
{
    const TSharedRef<FJsonObject> Context = MakeShared<FJsonObject>();
    FModuleManifest Engine;
    const FString EngineBinaries = FPaths::Combine(FPaths::EngineDir(), TEXT("Binaries"), FPlatformProcess::GetBinariesSubdirectory());
    Context->SetStringField(TEXT("build_id"), FModuleManifest::TryRead(FModuleManifest::GetFileName(EngineBinaries, false), Engine) ? Engine.BuildId : FString());

    const FString Project = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir());
    TArray<FModuleStatus> Statuses;
    FModuleManager::Get().QueryModules(Statuses);
    TArray<FString> Modules, Libraries;
    for (const FModuleStatus& Status : Statuses)
    {
        if (!Status.bIsLoaded || Status.FilePath.IsEmpty())
        {
            continue;
        }
        const FString File = FPaths::ConvertRelativePathToFull(Status.FilePath);
        Libraries.Add(File);
        if (File.StartsWith(FPaths::Combine(Project, TEXT("Binaries"))))
        {
            Modules.Add(Status.Name);
        }
    }
    Modules.Sort();
    Libraries.Sort();
    Context->SetField(TEXT("modules"), Strings(Modules));
    Context->SetField(TEXT("libraries"), Strings(Libraries));

    const TSharedRef<FJsonObject> Plugins = MakeShared<FJsonObject>();
    for (const TSharedRef<IPlugin>& Plugin : IPluginManager::Get().GetEnabledPlugins())
    {
        Plugins->SetStringField(Plugin->GetName(), FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir()));
    }
    Context->SetObjectField(TEXT("plugins"), Plugins);
    Context->SetStringField(TEXT("rhi"), GUsingNullRHI ? TEXT("null") : TEXT("other"));
    return Write(MakeShared<FJsonValueObject>(Context));
}

extern bool BeginAtelierReadRecording();
extern TArray<FString> EndAtelierReadRecording();

bool UAtelierBuildWorkerLibrary::BeginReadRecording()
{
    return BeginAtelierReadRecording();
}

FString UAtelierBuildWorkerLibrary::EndReadRecording()
{
    const TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    Report->SetNumberField(TEXT("version"), 1);
    Report->SetBoolField(TEXT("best_effort"), true);
    Report->SetField(TEXT("files"), Strings(EndAtelierReadRecording()));
    return Write(MakeShared<FJsonValueObject>(Report));
}

void UAtelierBuildWorkerLibrary::BeginSaveRecording()
{
    GSaved.Reset();
    GBefore.Reset();
    if (!GPreSaveHandle.IsValid())
    {
        GPreSaveHandle = UPackage::PreSavePackageWithContextEvent.AddStatic(&OnPackagePreSave);
    }
    if (!GSaveHandle.IsValid())
    {
        GSaveHandle = UPackage::PackageSavedWithContextEvent.AddStatic(&OnPackageSaved);
    }
}

FString UAtelierBuildWorkerLibrary::EndSaveRecording()
{
    if (GPreSaveHandle.IsValid())
    {
        UPackage::PreSavePackageWithContextEvent.Remove(GPreSaveHandle);
        GPreSaveHandle.Reset();
    }
    if (GSaveHandle.IsValid())
    {
        UPackage::PackageSavedWithContextEvent.Remove(GSaveHandle);
        GSaveHandle.Reset();
    }
    GBefore.Reset();
    TArray<TSharedPtr<FJsonValue>> Items;
    for (const FSaved& Saved : GSaved)
    {
        const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
        Item->SetStringField(TEXT("package"), Saved.Package);
        Item->SetStringField(TEXT("filename"), Saved.Filename);
        const TSharedRef<FJsonObject> Files = MakeShared<FJsonObject>();
        for (const TPair<FString, FString>& File : Saved.Files)
        {
            Files->SetStringField(File.Key, File.Value);
        }
        Item->SetObjectField(TEXT("files"), Files);
        Items.Add(MakeShared<FJsonValueObject>(Item));
    }
    GSaved.Reset();
    return Write(MakeShared<FJsonValueArray>(Items));
}

void UAtelierBuildWorkerLibrary::FinishBackgroundWork()
{
    FAssetCompilingManager::Get().FinishAllCompilation();
    if (GShaderCompilingManager)
    {
        GShaderCompilingManager->FinishAllCompilation();
    }
    FlushAsyncLoading();
}

TArray<FString> UAtelierBuildWorkerLibrary::DirtyPackageNames()
{
    TArray<FString> Names;
    for (TObjectIterator<UPackage> It; It; ++It)
    {
        if (IsValid(*It) && It->IsDirty())
        {
            Names.Add(It->GetName());
        }
    }
    Names.Sort();
    return Names;
}

TArray<FString> UAtelierBuildWorkerLibrary::LoadedPackageNames(const FString& Prefix)
{
    TArray<FString> Names;
    for (TObjectIterator<UPackage> It; It; ++It)
    {
        if (IsValid(*It) && It->GetName().StartsWith(Prefix))
        {
            Names.Add(It->GetName());
        }
    }
    Names.Sort();
    return Names;
}

FString UAtelierBuildWorkerLibrary::PackageImports(const FString& Filename)
{
    // The saved file's own import table, in table order: never the asset registry's dependencies.
    TArray<FObjectImport> Imports;
    if (!ReadImportTable(Filename, Imports))
    {
        return FString();  // the worker fails the job closed
    }
    TArray<FString> Paths;
    Paths.SetNum(Imports.Num());
    TFunction<FString(int32)> PathOf = [&Imports, &Paths, &PathOf](int32 Index) -> FString
    {
        if (!Paths[Index].IsEmpty())
        {
            return Paths[Index];
        }
        const FObjectImport& Import = Imports[Index];
        FString Path = Import.ObjectName.ToString();
        if (Import.OuterIndex.IsImport())
        {
            // As Unreal writes object paths: `.` after the package, `:` only at the first
            // subobject boundary (an outer that is a top-level asset), `.` for deeper nesting.
            const int32 Outer = Import.OuterIndex.ToImport();
            const FPackageIndex OuterOfOuter = Imports[Outer].OuterIndex;
            const bool bOuterIsAsset = OuterOfOuter.IsImport() && Imports[OuterOfOuter.ToImport()].OuterIndex.IsNull();
            Path = PathOf(Outer) + (bOuterIsAsset ? TEXT(":") : TEXT(".")) + Path;
        }
        Paths[Index] = Path;
        return Path;
    };
    TArray<TSharedPtr<FJsonValue>> Items;
    for (int32 Index = 0; Index < Imports.Num(); ++Index)
    {
        const FObjectImport& Import = Imports[Index];
        const FString Class = Import.ClassPackage.ToString() + TEXT(".") + Import.ClassName.ToString();
        Items.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueString>(PathOf(Index)), MakeShared<FJsonValueString>(Class)}));
    }
    return Write(MakeShared<FJsonValueArray>(Items));
}

FString UAtelierBuildWorkerLibrary::ConfigValue(const FString& File, const FString& Section, const FString& Key)
{
    FString Value;
    const bool bFound = GConfig && GConfig->GetString(*Section, *Key, Value, GConfig->GetConfigFilename(*File));
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("found"), bFound);
    Result->SetStringField(TEXT("value"), Value);
    return Write(MakeShared<FJsonValueObject>(Result));
}

FString UAtelierBuildWorkerLibrary::DdcGraph()
{
    FDerivedDataCacheInterface& Cache = GetDerivedDataCacheRef();
    const TSharedRef<FJsonObject> Graph = MakeShared<FJsonObject>();
    Graph->SetStringField(TEXT("graph"), Cache.GetGraphName());
    TArray<TSharedPtr<FJsonValue>> Nodes;
    PRAGMA_DISABLE_DEPRECATION_WARNINGS
    const TSharedRef<FDerivedDataCacheStatsNode> Stats = Cache.GatherUsageStats();
    PRAGMA_ENABLE_DEPRECATION_WARNINGS
    Stats->ForEachDescendant([&Nodes](TSharedRef<const FDerivedDataCacheStatsNode> Node)
        {
            // The hierarchy and async wrappers carry neither a type nor a path; every store does.
            if (Node->GetCacheType().IsEmpty() && Node->GetCacheName().IsEmpty())
            {
                return;
            }
            const TSharedRef<FJsonObject> Entry = MakeShared<FJsonObject>();
            Entry->SetStringField(TEXT("kind"), Node->GetCacheType());
            Entry->SetStringField(TEXT("path"), Node->GetCacheName().IsEmpty() ? FString() : FPaths::ConvertRelativePathToFull(Node->GetCacheName()));
            Entry->SetBoolField(TEXT("local"), Node->IsLocal());
            Entry->SetStringField(TEXT("status"), Node->GetCacheStatusText());
            Nodes.Add(MakeShared<FJsonValueObject>(Entry));
        });
    Graph->SetArrayField(TEXT("nodes"), Nodes);
    return Write(MakeShared<FJsonValueObject>(Graph));
}

FString UAtelierBuildWorkerLibrary::SettingsSnapshot()
{
    const TSharedRef<FJsonObject> Snapshot = MakeShared<FJsonObject>();
    IConsoleManager::Get().ForEachConsoleObjectThatStartsWith(FConsoleObjectVisitor::CreateLambda(
        [&Snapshot](const TCHAR* Name, IConsoleObject* Object)
        {
            if (IConsoleVariable* Variable = Object ? Object->AsVariable() : nullptr)
            {
                const EConsoleVariableFlags SetBy = EConsoleVariableFlags(Variable->GetFlags() & ECVF_SetByMask);
                Snapshot->SetField(Name, MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{
                    MakeShared<FJsonValueString>(Variable->GetString()), MakeShared<FJsonValueString>(GetConsoleVariableSetByName(SetBy))}));
            }
        }));
    return Write(MakeShared<FJsonValueObject>(Snapshot));
}

void UAtelierBuildWorkerLibrary::CollectGarbageNow()
{
    CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS, true);
}

FString UAtelierBuildWorkerLibrary::ReferenceChains(const FString& PackageName)
{
    const TSharedRef<FJsonObject> Chains = MakeShared<FJsonObject>();
    if (UPackage* Package = FindPackage(nullptr, *PackageName))
    {
        TArray<UObject*> Objects;
        GetObjectsWithPackage(Package, Objects, EGetObjectsFlags::None);
        Objects.Add(Package);
        for (UObject* Object : Objects)
        {
            FReferenceChainSearch Search(Object, EReferenceChainSearchMode::Shortest);
            Chains->SetStringField(Object->GetPathName(), Search.GetRootPath());
        }
    }
    return Write(MakeShared<FJsonValueObject>(Chains));
}

bool UAtelierBuildWorkerLibrary::ReleaseEditorState(const FString& Which)
{
    if (Which == TEXT("transactions") && GEditor)
    {
        GEditor->ResetTransaction(NSLOCTEXT("AtelierBuildWorker", "ResetTransaction", "Build worker reset"));
        return true;
    }
    if (Which == TEXT("selection") && GEditor)
    {
        GEditor->SelectNone(false, true, false);
        GEditor->GetSelectedObjects()->DeselectAll();
        GEditor->GetSelectedActors()->DeselectAll();
        GEditor->GetSelectedComponents()->DeselectAll();
        return true;
    }
    if (Which == TEXT("interchange"))
    {
        // No public way to drop Interchange's own state: report whether any import is still active.
        return !UInterchangeManager::GetInterchangeManager().IsInterchangeActive();
    }
    return false;
}

void UAtelierBuildWorkerLibrary::BeginEnsureCount()
{
    GEnsures = 0;
    if (!GEnsureHandle.IsValid())
    {
        GEnsureHandle = FCoreDelegates::OnEnsureFailed.AddLambda(
            [](const ANSICHAR*, const ANSICHAR*, int32, const TCHAR*, const TCHAR*) { ++GEnsures; });
    }
}

int32 UAtelierBuildWorkerLibrary::EnsureCount()
{
    return GEnsures;
}

void UAtelierBuildWorkerLibrary::ForgetFiles(const TArray<FString>& Files)
{
    IAssetRegistry::GetChecked().ScanModifiedAssetFiles(Files);
}
