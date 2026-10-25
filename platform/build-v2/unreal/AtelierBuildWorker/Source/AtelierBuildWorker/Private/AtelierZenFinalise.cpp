#include "AtelierZenFinalise.h"
#include "AssetRegistry/AssetRegistryState.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "CookMetadata.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Interfaces/ITargetPlatformManagerModule.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Serialization/BufferArchive.h"
#include "Serialization/CompactBinaryWriter.h"
#include "Serialization/CompactBinaryPackage.h"
#include "Serialization/CompactBinaryValidation.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/PackageStore.h"
#include "ShaderLibrary/EditorShaderCodeArchive.h"
#include "UObject/PackageFileSummary.h"
#include <CommonCrypto/CommonDigest.h>
#include <sys/stat.h>

namespace
{
using FObject = TSharedPtr<FJsonObject>;
using FMembership = TMap<FName, TSet<FString>>;
using ESource = ShaderCodeArchive::ECookShaderLibrarySource;

FString Encode(const FObject& Object)
{
    FString Text;
    FJsonSerializer::Serialize(Object.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    return Text;
}
FString SHA(TConstArrayView<uint8> Bytes)
{
    uint8 Digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(Bytes.GetData(), CC_LONG(Bytes.Num()), Digest);
    FString Result;
    for (uint8 Byte : Digest) Result += FString::Printf(TEXT("%02x"), Byte);
    return Result;
}
FString Text(const FObject& Object, const TCHAR* Field)
{
    FString Value;
    if (Object) Object->TryGetStringField(Field, Value);
    return Value;
}
bool Fields(const FObject& Object, std::initializer_list<const TCHAR*> Names)
{
    if (!Object || Object->Values.Num() != int32(Names.size())) return false;
    for (const TCHAR* Name : Names) if (!Object->HasField(Name)) return false;
    return true;
}
bool Token(const FString& Value)
{
    if (Value.IsEmpty()) return false;
    for (TCHAR C : Value) if (!FChar::IsAlnum(C) && C != '_' && C != '-') return false;
    return true;
}
bool ShaderFormatAndPlatform(const FString& Value)
{
    // UE 5.8 FEditorShaderCodeArchive takes the compound format-platform name.
    TArray<FString> Parts;
    Value.ParseIntoArray(Parts, TEXT("-"), false);
    return Parts.Num() == 2 && Token(Parts[0]) && Token(Parts[1]);
}
bool SameOwnedDirectory(const FString& Actual, const FString& Expected)
{
    // Metal's stock writer lowercases the complete .metalmap filename. A case alias
    // is accepted only for this exact parent and the same physical, no-link directory.
    if (!Actual.Equals(Expected, ESearchCase::IgnoreCase)) return false;
    auto Directory = [](const FString& Path, struct stat& Result)
    {
        if (FPaths::IsRelative(Path)) return false;
        TArray<FString> Parts; Path.ParseIntoArray(Parts, TEXT("/"), true);
        FString Current = TEXT("/");
        for (const FString& Part : Parts)
        {
            if (Part == TEXT(".") || Part == TEXT("..")) return false;
            Current /= Part;
            if (lstat(TCHAR_TO_UTF8(*Current), &Result) != 0 || !S_ISDIR(Result.st_mode)) return false;
        }
        return !Parts.IsEmpty();
    };
    struct stat Left{}, Right{};
    return Directory(Actual, Left) && Directory(Expected, Right)
        && Left.st_dev == Right.st_dev && Left.st_ino == Right.st_ino;
}
bool Pinned(const FObject& Spec, TArray<uint8>& Bytes)
{
    if (!Fields(Spec, {TEXT("path"), TEXT("sha256")})) return false;
    const FString Path = Text(Spec, TEXT("path"));
    const int64 Size = IFileManager::Get().FileSize(*Path);
    return !FPaths::IsRelative(Path) && Size > 0 && Size <= 512ll * 1024 * 1024
        && Text(Spec, TEXT("sha256")).Len() == 64 && FFileHelper::LoadFileToArray(Bytes, *Path)
        && SHA(Bytes) == Text(Spec, TEXT("sha256"));
}
FObject Child(const FObject& Parent, const TCHAR* Field)
{
    const FObject* Value = nullptr;
    return Parent && Parent->TryGetObjectField(Field, Value) ? *Value : nullptr;
}
struct FHistory
{
    FAssetRegistryState Registry;
    UE::Cook::FCookMetadataState Metadata;
    FObject Files;
    FString Content;
    TSet<FName> Packages;
    TMap<FName, TArray<FShaderHash>> PackageShaders;
};
bool RecordShaders(const FObject& Spec, const FString& Name, const FString& RootHash, TArray<FShaderHash>& Hashes)
{
    TArray<uint8> Bytes;
    if (!Pinned(Spec, Bytes) || ValidateCompactBinaryPackage(MakeMemoryView(Bytes), ECbValidateMode::All) != ECbValidateError::None)
        return false;
    FMemoryReader Reader(Bytes, true); FCbPackage Package;
    if (!Package.TryLoad(Reader) || Reader.IsError() || Reader.Tell() != Reader.TotalSize()) return false;
    const FCbObject Container = Package.GetObject();
    if (!Container || Package.GetObjectHash() != Container.GetHash()) return false;
    const bool Retained = Container["record_schema"].HasValue();
    if (Retained && Container["record_schema"].AsString() != "atelier-zen-package-record/1") return false;
    const FCbObject Entry = Retained ? Container["entry"].AsObject() : Container;
    if (!Entry || RootHash != LexToString(Entry.GetHash()) || !Entry["packagestoreentry"].IsObject()) return false;
    const FPackageStoreEntryResource Store = FPackageStoreEntryResource::FromCbObject(Entry["packagestoreentry"].AsObjectView());
    if (Store.PackageName.ToString() != Name || Store.HasCookError()
        || !EnumHasAnyFlags(Store.Flags, EPackageStoreEntryFlags::HasPackageData)) return false;
    Hashes = Store.ShaderMapHashes;
    return true;
}
bool ShaderFile(const FHistory& History, const FString& Relative, TArray<uint8>& Bytes)
{
    FString Expected;
    const FString Path = History.Content / Relative;
    const int64 Size = IFileManager::Get().FileSize(*Path);
    return History.Files->TryGetStringField(Relative, Expected) && Expected.Len() == 64
        && Size > 0 && Size <= 512ll * 1024 * 1024 && FFileHelper::LoadFileToArray(Bytes, *Path)
        && SHA(Bytes) == Expected;
}
bool Membership(const FHistory& History, const FString& Library, const FString& Format,
    FMembership& Assets, TArray<FShaderHash>& NativeHashes, bool GlobalLibrary = false)
{
    const FString Stem = TEXT("-") + Library + TEXT("-") + Format;
    TArray<uint8> Info, Code, Types;
    if (!ShaderFile(History, TEXT("ShaderAssetInfo") + Stem + TEXT(".assetinfo.json"), Info)
        || !ShaderFile(History, TEXT("ShaderArchive") + Stem + TEXT(".ushaderbytecode"), Code)
        || !ShaderFile(History, TEXT("ShaderTypeInfo") + Stem + TEXT(".stinfo"), Types)) return false;
    FObject Object;
    const FString Json(FUTF8ToTCHAR(reinterpret_cast<const ANSICHAR*>(Info.GetData()), Info.Num()));
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Object) || !Object
        || !Object->TryGetArrayField(TEXT("ShaderCodeToAssets"), Rows)) return false;
    TSet<FString> Declared;
    for (const auto& RowValue : *Rows)
    {
        const FObject Row = RowValue->AsObject();
        const FString Hash = Text(Row, TEXT("ShaderMapHash"));
        const TArray<TSharedPtr<FJsonValue>>* Names = nullptr;
        if (Hash.Len() != 16 || Declared.Contains(Hash) || !Row->TryGetArrayField(TEXT("Assets"), Names)
            || (!GlobalLibrary && Names->IsEmpty())) return false;
        Declared.Add(Hash);
        for (const auto& Value : *Names)
        {
            const FString Name = Value->AsString();
            // An unassociated/global map requires its own explicit global-library producer.
            // Never smuggle it into every package or merge the whole historical archive.
            if (GlobalLibrary)
            {
                if (!Name.IsEmpty() && !FName(*Name).IsNone()) return false;
            }
            else
            {
                if (!FPackageName::IsValidLongPackageName(Name)) return false;
                Assets.FindOrAdd(FName(*Name)).Add(Hash);
            }
        }
    }
    FMemoryReader Reader(Code, true);
    if (!FSerializedShaderArchive::SerializeHeaderVersion(Reader)) return false;
    FSerializedShaderArchive Archive;
    Reader << Archive;
    if (Reader.IsError() || (!GlobalLibrary && Archive.ShaderMapHashes.Num() != Declared.Num())) return false;
    TSet<FString> NativeSet;
    for (const FShaderHash& Hash : Archive.ShaderMapHashes)
    {
        if (NativeSet.Contains(Hash.ToString()) || (!GlobalLibrary && !Declared.Contains(Hash.ToString()))) return false;
        NativeSet.Add(Hash.ToString()); NativeHashes.Add(Hash);
    }
    for (const FString& Hash : Declared) if (!NativeSet.Contains(Hash)) return false;
    return true;
}
bool SameMembership(const FMembership& A, const FMembership& B)
{
    if (A.Num() != B.Num()) return false;
    for (const auto& Pair : A)
    {
        const TSet<FString>* Other = B.Find(Pair.Key);
        if (!Other || Other->Num() != Pair.Value.Num()) return false;
        for (const FString& Hash : Pair.Value) if (!Other->Contains(Hash)) return false;
    }
    return true;
}
TArray<FString> Edges(const FAssetRegistryState& State, const FAssetIdentifier& Id,
    TArray<FAssetDependency>* Native = nullptr)
{
    TArray<FAssetDependency> Dependencies;
    State.GetDependencies(Id, Dependencies);
    TArray<FString> Result;
    for (const FAssetDependency& D : Dependencies)
        Result.Add(FString::Printf(TEXT("%s|%u|%u"), *D.AssetId.ToString(), uint32(D.Category), uint32(D.Properties)));
    Result.Sort();
    if (Native) *Native = MoveTemp(Dependencies);
    return Result;
}
FIoHash PackageSignature(const FAssetPackageData& Data)
{
    FAssetPackageData Canonical = Data;
    Canonical.ChunkHashes.KeySort([](const FIoChunkId& A, const FIoChunkId& B) { return A < B; });
    FCbWriter Writer;
    Writer.BeginObject();
    Writer.SetName("package");
    Canonical.NetworkWrite(Writer);
    Writer.EndObject();
    return Writer.Save().AsObject().GetHash();
}
FIoHash AssetSignature(const FAssetData& Asset)
{
    FCbWriter Writer;
    Writer.BeginObject();
    Writer << "flags" << Asset.PackageFlags;
    Writer.SetName("asset");
    Asset.NetworkWrite(Writer, true);
    Writer.EndObject();
    return Writer.Save().AsObject().GetHash();
}
bool CanonicalizeMetadata(UE::Cook::FCookMetadataState& Metadata)
{
    // Native indices and array order encode a graph, not plugin identity. Retain
    // every node/type/size/custom value and edge (including multiplicity), but
    // rewrite all indices into one name-ordered representation before comparing.
    static_assert(UE::Cook::ECookMetadataStateVersion::LatestVersion == UE::Cook::ECookMetadataStateVersion::AdjustCustomFieldLayout,
        "Review all native metadata fields and index remapping for a new format");
    const auto& Original = Metadata.GetPluginHierarchy();
    const int32 Count = Original.PluginsEnabledAtCook.Num();
    const int32 FieldCount = Original.CustomFieldEntries.Num();
    if (Count > 65536 || FieldCount > 256) return false;
    TArray<int32> Order, Fields;
    for (int32 I = 0; I < Count; ++I) Order.Add(I);
    for (int32 I = 0; I < FieldCount; ++I) Fields.Add(I);
    Order.Sort([&](int32 A, int32 B) { return Original.PluginsEnabledAtCook[A].Name < Original.PluginsEnabledAtCook[B].Name; });
    Fields.Sort([&](int32 A, int32 B) { return Original.CustomFieldEntries[A].Name < Original.CustomFieldEntries[B].Name; });
    TArray<uint16> Remap; Remap.SetNum(Count);
    TArray<uint8> FieldRemap; FieldRemap.SetNum(FieldCount);
    for (int32 I = 0; I < Count; ++I)
    {
        const FString& Name = Original.PluginsEnabledAtCook[Order[I]].Name;
        if (Name.IsEmpty() || (I > 0 && Name == Original.PluginsEnabledAtCook[Order[I - 1]].Name)) return false;
        Remap[Order[I]] = uint16(I);
    }
    for (int32 I = 0; I < FieldCount; ++I)
    {
        const FString& Name = Original.CustomFieldEntries[Fields[I]].Name;
        if (Name.IsEmpty() || (I > 0 && Name == Original.CustomFieldEntries[Fields[I - 1]].Name)) return false;
        FieldRemap[Fields[I]] = uint8(I);
    }
    UE::Cook::FCookMetadataPluginHierarchy Canonical = Original;
    Canonical.PluginsEnabledAtCook.Empty(); Canonical.PluginDependencies.Empty();
    Canonical.RootPlugins.Empty(); Canonical.CustomFieldEntries.Empty();
    for (int32 Old : Fields) Canonical.CustomFieldEntries.Add(Original.CustomFieldEntries[Old]);
    TArray<uint8> UsedDependencies; UsedDependencies.Init(0, Original.PluginDependencies.Num());
    for (int32 Old : Order)
    {
        UE::Cook::FCookMetadataPluginEntry Entry = Original.PluginsEnabledAtCook[Old];
        if (Entry.DependencyIndexStart > Entry.DependencyIndexEnd || Entry.DependencyIndexEnd > uint32(Original.PluginDependencies.Num())) return false;
        TArray<uint16> Children;
        for (uint32 I = Entry.DependencyIndexStart; I < Entry.DependencyIndexEnd; ++I)
        {
            if (UsedDependencies[I] != 0) return false;
            UsedDependencies[I] = 1;
            const uint16 Child = Original.PluginDependencies[I];
            if (!Remap.IsValidIndex(Child)) return false;
            Children.Add(Remap[Child]);
        }
        Children.Sort();
        Entry.DependencyIndexStart = Canonical.PluginDependencies.Num();
        Canonical.PluginDependencies.Append(Children);
        Entry.DependencyIndexEnd = Canonical.PluginDependencies.Num();
        const auto Values = Entry.CustomFields; Entry.CustomFields.Empty();
        for (const auto& Pair : Values)
        {
            if (!FieldRemap.IsValidIndex(Pair.Key)) return false;
            Entry.CustomFields.Add(FieldRemap[Pair.Key], Pair.Value);
        }
        Entry.CustomFields.KeySort([](uint8 A, uint8 B) { return A < B; });
        Canonical.PluginsEnabledAtCook.Add(MoveTemp(Entry));
    }
    if (UsedDependencies.Contains(0)) return false;
    for (uint16 Root : Original.RootPlugins)
    {
        if (!Remap.IsValidIndex(Root)) return false;
        Canonical.RootPlugins.Add(Remap[Root]);
    }
    Canonical.RootPlugins.Sort();
    Metadata.SetPluginHierarchyInfo(MoveTemp(Canonical));
    return true;
}
bool SaveRegistry(FAssetRegistryState& State, const FString& Path,
    const FAssetRegistrySerializationOptions& Options)
{
    const TUniquePtr<FArchive> Writer(IFileManager::Get().CreateFileWriter(*Path, FILEWRITE_NoReplaceExisting));
    return Writer && State.Save(*Writer, Options) && Writer->Close() && !Writer->IsError();
}
}

FString AtelierZenFinaliseRequest(const FString& RequestJson)
{
    const FObject Report = MakeShared<FJsonObject>();
    Report->SetNumberField(TEXT("version"), 1);
    Report->SetStringField(TEXT("status"), TEXT("refused"));
    auto Fail = [&](const TCHAR* Why) { Report->SetStringField(TEXT("error"), Why); return Encode(Report); };
    FObject Request;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(RequestJson), Request) || !Request)
        return Fail(TEXT("invalid_request_json"));
    double Version = 0;
    bool GlobalLibrary = false, NativeLibraries = false;
    if (!Request->TryGetNumberField(TEXT("version"), Version)) return Fail(TEXT("missing_request_version"));
    if (Version == 1)
    {
        if (!Fields(Request, {TEXT("version"), TEXT("library"), TEXT("formats"), TEXT("histories"), TEXT("output_dir")}))
            return Fail(TEXT("unknown_or_missing_request_fields"));
    }
    else if (Version == 2)
    {
        if (!Fields(Request, {TEXT("version"), TEXT("library"), TEXT("formats"), TEXT("histories"), TEXT("output_dir"), TEXT("global_library"), TEXT("native_libraries")})
            || !Request->TryGetBoolField(TEXT("global_library"), GlobalLibrary)
            || !Request->TryGetBoolField(TEXT("native_libraries"), NativeLibraries))
            return Fail(TEXT("missing_explicit_shader_library_policy"));
    }
    else return Fail(TEXT("unsupported_request_version"));
    const FString Library = Text(Request, TEXT("library")), Output = Text(Request, TEXT("output_dir"));
    const TArray<TSharedPtr<FJsonValue>>* Formats = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Specs = nullptr;
    if (!Token(Library)
        || FPaths::IsRelative(Output) || IFileManager::Get().DirectoryExists(*Output)
        || !Request->TryGetArrayField(TEXT("formats"), Formats) || Formats->IsEmpty() || Formats->Num() > 32
        || !Request->TryGetArrayField(TEXT("histories"), Specs) || Specs->IsEmpty() || Specs->Num() > 4096 || (GlobalLibrary && Specs->Num() != 1))
        return Fail(TEXT("invalid_bounded_request_or_output_not_fresh"));
    TSet<FString> FormatNames;
    for (const auto& Value : *Formats)
    {
        const FString Format = Value->AsString();
        if (!ShaderFormatAndPlatform(Format) || FormatNames.Contains(Format)) return Fail(TEXT("duplicate_or_invalid_shader_format"));
        FormatNames.Add(Format);
    }
    TArray<TUniquePtr<FHistory>> Histories;
    TMap<FName, int32> Owner;
    TMap<FAssetIdentifier, int32> PrimaryOwner;
    TArray<uint8> CanonicalMetadata;
    FAssetRegistryState Combined;
    for (int32 Index = 0; Index < Specs->Num(); ++Index)
    {
        const FObject Spec = (*Specs)[Index]->AsObject();
        if (GlobalLibrary
                ? !Fields(Spec, {TEXT("content_dir"), TEXT("files"), TEXT("packages")})
                : !Fields(Spec, {TEXT("registry"), TEXT("metadata"), TEXT("content_dir"), TEXT("files"), TEXT("packages")}))
            return Fail(TEXT("unknown_history_fields"));
        TUniquePtr<FHistory> H = MakeUnique<FHistory>();
        H->Content = Text(Spec, TEXT("content_dir")); H->Files = Child(Spec, TEXT("files"));
        const TArray<TSharedPtr<FJsonValue>>* Packages = nullptr;
        if (FPaths::IsRelative(H->Content) || !H->Files
            || (H->Files->Values.Num() != FormatNames.Num() * 3 && (GlobalLibrary || !H->Files->Values.IsEmpty()))
            || !Spec->TryGetArrayField(TEXT("packages"), Packages)
            || (GlobalLibrary ? !Packages->IsEmpty() : Packages->IsEmpty()))
            return Fail(TEXT("incomplete_history_roster"));
        TArray<FString> ActualContent;
        IFileManager::Get().FindFilesRecursive(ActualContent, *H->Content, TEXT("*"), true, false);
        if (ActualContent.Num() != H->Files->Values.Num()) return Fail(TEXT("unlisted_shader_or_stable_key_file"));
        for (const FString& File : ActualContent)
        {
            FString Relative = File;
            FPaths::MakePathRelativeTo(Relative, *(H->Content + TEXT("/")));
            if (!H->Files->HasField(Relative)) return Fail(TEXT("unlisted_history_file"));
        }
        if (GlobalLibrary) { Histories.Add(MoveTemp(H)); continue; }
        TArray<uint8> RegistryBytes, MetadataBytes;
        if (!Pinned(Child(Spec, TEXT("registry")), RegistryBytes) || !Pinned(Child(Spec, TEXT("metadata")), MetadataBytes))
            return Fail(TEXT("history_registry_or_metadata_hash_changed"));
        FMemoryReader RegistryReader(RegistryBytes, true), MetadataReader(MetadataBytes, true);
        FAssetRegistryLoadOptions Load; Load.ParallelWorkers = 3;
        if (!H->Registry.Load(RegistryReader, Load) || RegistryReader.IsError() || RegistryReader.Tell() != RegistryReader.TotalSize()
            || !H->Metadata.Serialize(MetadataReader) || MetadataReader.IsError() || !H->Metadata.IsValid()
            || MetadataReader.Tell() != MetadataReader.TotalSize() || H->Metadata.GetPlatform() != TEXT("Mac")
            || H->Metadata.GetSizesPresent() != UE::Cook::ECookMetadataSizesPresent::NotPresent
            || !H->Metadata.GetShaderPseudoHierarchy().ShaderAssets.IsEmpty()
            || !H->Metadata.GetShaderPseudoHierarchy().DependencyList.IsEmpty()
            || !H->Metadata.GetShaderPseudoHierarchy().PackageShaderDependencyMap.IsEmpty()
            || H->Metadata.GetAssociatedDevelopmentAssetRegistryHashPostWriteback() != 0
            || H->Metadata.GetAssociatedDevelopmentAssetRegistryHash()
                != UE::Cook::FCookMetadataState::ComputeHashOfDevelopmentAssetRegistry(MakeMemoryView(RegistryBytes)))
            return Fail(TEXT("unsupported_staged_metadata_or_broken_registry_linkage"));
        if (!CanonicalizeMetadata(H->Metadata)) return Fail(TEXT("invalid_metadata_plugin_index_graph"));
        UE::Cook::FCookMetadataState Normalized = H->Metadata;
        Normalized.SetAssociatedDevelopmentAssetRegistryHash(0);
        FBufferArchive Serialized; if (!Normalized.Serialize(Serialized)) return Fail(TEXT("metadata_normalization_failed"));
        if (Index == 0) CanonicalMetadata = Serialized;
        else if (CanonicalMetadata != Serialized) return Fail(TEXT("history_platform_plugin_metadata_differs"));
        for (const auto& Value : *Packages)
        {
            const FObject Package = Value->AsObject();
            if (!Fields(Package, {TEXT("name"), TEXT("source"), TEXT("record"), TEXT("root_hash")})) return Fail(TEXT("unknown_selected_package_fields"));
            const FString Name = Text(Package, TEXT("name"));
            const FName Key(*Name);
            if (!FPackageName::IsValidLongPackageName(Name) || Owner.Contains(Key)) return Fail(TEXT("invalid_or_duplicate_selected_package"));
            TArray<uint8> SourceBytes;
            if (!Pinned(Child(Package, TEXT("source")), SourceBytes)) return Fail(TEXT("selected_source_hash_changed"));
            FMemoryReader Reader(SourceBytes, true); FPackageFileSummary Summary; Reader << Summary;
            const FAssetPackageData* Data = H->Registry.GetAssetPackageData(Key);
            if (Reader.IsError() || !Data || Summary.GetSavedHash().IsZero() || Summary.GetSavedHash() != Data->GetPackageSavedHash())
                return Fail(TEXT("selected_registry_does_not_bind_source_package"));
            TArray<FShaderHash> ShaderMaps;
            if (!RecordShaders(Child(Package, TEXT("record")), Name, Text(Package, TEXT("root_hash")), ShaderMaps))
                return Fail(TEXT("selected_native_record_shader_binding_failed"));
            if (H->Files->Values.IsEmpty() && !ShaderMaps.IsEmpty())
                return Fail(TEXT("missing_shader_history_for_native_shader_maps"));
            H->PackageShaders.Add(Key, MoveTemp(ShaderMaps));
            Owner.Add(Key, Index); H->Packages.Add(Key);
            *Combined.CreateOrGetAssetPackageData(Key) = *Data;
        }
        TArray<FAssetData> Assets; H->Registry.GetAllAssets(TSet<FName>(), Assets, false);
        for (const FAssetData& Asset : Assets) if (H->Packages.Contains(Asset.PackageName))
        {
            Combined.AddAssetData(new FAssetData(Asset));
            const FPrimaryAssetId Primary = Asset.GetPrimaryAssetId();
            if (Primary.IsValid())
            {
                const FAssetIdentifier Id(Primary);
                if (PrimaryOwner.Contains(Id)) return Fail(TEXT("ambiguous_selected_primary_asset"));
                PrimaryOwner.Add(Id, Index);
            }
        }
        Histories.Add(MoveTemp(H));
    }
    TSet<FString> ExpectedFiles;
    TSet<FAssetIdentifier> Visited;
    if (!IFileManager::Get().MakeDirectory(*(Output / TEXT("Content")), true)
        || !IFileManager::Get().MakeDirectory(*(Output / TEXT("Metadata/ShaderLibrarySource")), true)
        || !IFileManager::Get().MakeDirectory(*(Output / TEXT("Metadata/PipelineCaches")), true))
        return Fail(TEXT("output_directory_create_failed"));
    if (!GlobalLibrary)
    {
    // Copy outgoing dependency tuples from each selected package's actual history.
    // Restoring after pruning would have lost cross-history edges, so no pruning
    // or whole-history dependency union occurs here. Referencers are native-derived.
    TArray<FAssetIdentifier> Queue;
    for (const auto& Pair : Owner) Queue.Add(FAssetIdentifier(Pair.Key));
    for (const auto& Pair : PrimaryOwner) Queue.Add(Pair.Key);
    TMap<FAssetIdentifier, TArray<FString>> ExpectedEdges;
    for (int32 Cursor = 0; Cursor < Queue.Num(); ++Cursor)
    {
        if (Queue.Num() > 1000000) return Fail(TEXT("dependency_graph_bound_exceeded"));
        const FAssetIdentifier Id = Queue[Cursor];
        if (Visited.Contains(Id)) continue;
        Visited.Add(Id);
        const int32* Index = Owner.Find(Id.PackageName);
        if (!Index) Index = PrimaryOwner.Find(Id);
        const bool Script = Id.PackageName.ToString().StartsWith(TEXT("/Script/"));
        if (!Index && !Script) return Fail(TEXT("dependency_target_missing_from_exact_selection"));
        const int32 Origin = Index ? *Index : 0;
        TArray<FAssetDependency> Native;
        const TArray<FString> Exact = Edges(Histories[Origin]->Registry, Id, &Native);
        if (Script)
        {
            const FAssetPackageData* Data = Histories[Origin]->Registry.GetAssetPackageData(Id.PackageName);
            for (const auto& H : Histories)
            {
                const FAssetPackageData* Other = H->Registry.GetAssetPackageData(Id.PackageName);
                if (Edges(H->Registry, Id) != Exact || bool(Data) != bool(Other)
                    || (Data && PackageSignature(*Data) != PackageSignature(*Other)))
                    return Fail(TEXT("script_dependency_or_package_metadata_differs_between_histories"));
            }
            if (Data) *Combined.CreateOrGetAssetPackageData(Id.PackageName) = *Data;
        }
        ExpectedEdges.Add(Id, Exact);
        Combined.SetDependencies(Id, Native);
        for (const FAssetDependency& Dependency : Native) Queue.Add(Dependency.AssetId);
    }
    const ITargetPlatform* Mac = GetTargetPlatformManagerRef().FindTargetPlatform(TEXT("Mac"));
    if (!Mac) return Fail(TEXT("native_mac_platform_unavailable"));
    FAssetRegistrySerializationOptions Dev(UE::AssetRegistry::ESerializationTarget::ForDevelopment);
    IAssetRegistry::GetChecked().InitializeSerializationOptions(Dev, Mac, UE::AssetRegistry::ESerializationTarget::ForDevelopment);
    Dev.bKeepDevelopmentAssetRegistryTags = true;
    const FString Development = Output / TEXT("Metadata/DevelopmentAssetRegistry.bin");
    if (!SaveRegistry(Combined, Development, Dev)) return Fail(TEXT("native_development_registry_save_failed"));
    TArray<uint8> RegistryBytes;
    FAssetRegistryState Readback;
    FAssetRegistryLoadOptions Load; Load.ParallelWorkers = 3;
    if (!FFileHelper::LoadFileToArray(RegistryBytes, *Development)) return Fail(TEXT("registry_readback_missing"));
    FMemoryReader RegistryReader(RegistryBytes, true);
    if (!Readback.Load(RegistryReader, Load) || RegistryReader.IsError() || RegistryReader.Tell() != RegistryReader.TotalSize())
        return Fail(TEXT("native_registry_readback_invalid"));
    if (Readback.GetNumPackages() != Combined.GetNumPackages() || Readback.GetNumAssets() != Combined.GetNumAssets())
        return Fail(TEXT("native_registry_readback_roster_differs"));
    for (const auto& Pair : Combined.GetAssetPackageDataMap())
    {
        const FAssetPackageData* Data = Readback.GetAssetPackageData(Pair.Key);
        if (!Data || PackageSignature(*Data) != PackageSignature(*Pair.Value))
            return Fail(TEXT("native_registry_package_readback_differs"));
    }
    TArray<FAssetData> Before, After;
    Combined.GetAllAssets(TSet<FName>(), Before, false); Readback.GetAllAssets(TSet<FName>(), After, false);
    TMap<FSoftObjectPath, FIoHash> ActualAssets;
    for (const FAssetData& Asset : After) ActualAssets.Add(Asset.GetSoftObjectPath(), AssetSignature(Asset));
    for (const FAssetData& Asset : Before)
    {
        const FIoHash* Hash = ActualAssets.Find(Asset.GetSoftObjectPath());
        if (!Hash || *Hash != AssetSignature(Asset)) return Fail(TEXT("native_registry_asset_readback_differs"));
    }
    for (const auto& Pair : ExpectedEdges)
        if (Edges(Readback, Pair.Key) != Pair.Value) return Fail(TEXT("native_registry_dependency_readback_differs"));
    FAssetRegistrySerializationOptions Runtime(UE::AssetRegistry::ESerializationTarget::ForGame);
    IAssetRegistry::GetChecked().InitializeSerializationOptions(Runtime, Mac, UE::AssetRegistry::ESerializationTarget::ForGame);
    if (!SaveRegistry(Combined, Output / TEXT("AssetRegistry.bin"), Runtime)) return Fail(TEXT("native_runtime_registry_save_failed"));
    // Only pre-stage cook metadata is composable here. All non-linkage bytes have
    // already been proven equal across source histories; staging computes its own
    // plugin sizes and shader pseudo-hierarchy from the exact resulting archives.
    UE::Cook::FCookMetadataState Metadata = Histories[0]->Metadata;
    const uint64 RegistryHash = UE::Cook::FCookMetadataState::ComputeHashOfDevelopmentAssetRegistry(MakeMemoryView(RegistryBytes));
    Metadata.SetAssociatedDevelopmentAssetRegistryHash(RegistryHash);
    const FString MetadataPath = Output / TEXT("Metadata") / UE::Cook::GetCookMetadataFilename();
    if (!Metadata.SaveToFile(MetadataPath)) return Fail(TEXT("native_cook_metadata_save_failed"));
    UE::Cook::FCookMetadataState MetadataReadback;
    if (!MetadataReadback.ReadFromFile(MetadataPath) || !MetadataReadback.IsValid()
        || MetadataReadback.GetAssociatedDevelopmentAssetRegistryHash() != RegistryHash
        || MetadataReadback.GetAssociatedDevelopmentAssetRegistryHashPostWriteback() != 0)
        return Fail(TEXT("native_metadata_registry_linkage_readback_failed"));
    ExpectedFiles.Add(TEXT("AssetRegistry.bin"));
    ExpectedFiles.Add(TEXT("Metadata/DevelopmentAssetRegistry.bin"));
    ExpectedFiles.Add(TEXT("Metadata/") + UE::Cook::GetCookMetadataFilename());
    }
    TMap<FName, TSet<FString>> ObservedPackageMaps;
    // A whole certified global item is current data. SDK incremental loading
    // deliberately drops NAME_None owners, whose contract is to be re-added each cook.
    const ESource SourceOrigin = GlobalLibrary ? ESource::CurrentCook : ESource::PreviousIncremental;
    for (const FString& Format : FormatNames)
    {
        FEditorShaderCodeArchive Destination{FName(*Format)};
        Destination.OpenLibrary(Library);
        FMembership Expected;
        TSet<FString> GlobalMaps;
        for (const auto& H : Histories)
        {
            // The pinned source record is authoritative even when the cooker emitted no library.
            // Registry/source-summary and CookMetadata linkage were checked above; no empty
            // archive or caller-authored shaderless assertion substitutes for these native hashes.
            if (!GlobalLibrary && H->Files->Values.IsEmpty()) continue;
            FMembership SourceMembership; TArray<FShaderHash> Native;
            if (!Membership(*H, Library, Format, SourceMembership, Native, GlobalLibrary))
                return Fail(TEXT("shader_membership_or_unassociated_global_input_unsupported"));
            if (!GlobalLibrary) for (const FName& Package : H->Packages)
            {
                const TSet<FString>* Associated = SourceMembership.Find(Package);
                if (Associated) ObservedPackageMaps.FindOrAdd(Package).Append(*Associated);
            }
            for (const auto& Pair : SourceMembership) if (H->Packages.Contains(Pair.Key)) Expected.Add(Pair.Key, Pair.Value);
            FEditorShaderCodeArchive Source{FName(*Format)}; Source.OpenLibrary(Library);
            Source.AddShaderCodeLibraryFromDirectory(H->Content, SourceOrigin);
            for (const FShaderHash& Hash : Native) if (!Source.HasShaderMap(Hash)) return Fail(TEXT("native_source_shader_map_load_incomplete"));
            TUniquePtr<FEditorShaderCodeArchive> Chunk;
            if (GlobalLibrary)
            {
                // A current global-library producer is one whole bounded item;
                // it has no package associations and is never unioned with an
                // older global archive. Keep its complete native shader roster.
                Chunk = MakeUnique<FEditorShaderCodeArchive>(FName(*Format)); Chunk->OpenLibrary(Library);
                for (int32 I = 0; I < Native.Num(); ++I)
                {
                    Chunk->AddShaderCode(I, Source, SourceOrigin);
                    GlobalMaps.Add(Native[I].ToString());
                }
            }
            else Chunk = Source.CreateNamedChunk(Library, H->Packages);
            if (!Chunk) return Fail(TEXT("native_selected_shader_chunk_failed"));
            if (!Chunk->IsEmpty())
            {
                FSerializedShaderArchive Archive; TArray<uint8> Code; bool Full = false;
                Chunk->CopyToArchiveAndClear(Archive, Code, Full, MAX_int64, MAX_int64, SourceOrigin);
                if (Full) return Fail(TEXT("native_selected_shader_chunk_exceeded_bounds"));
                // CreateNamedChunk selects code but preserves the parent's full
                // association set for shared maps. Remove unselected owners from
                // the public transfer archive before merging either history.
                for (const auto& Pair : SourceMembership)
                    if (!H->Packages.Contains(Pair.Key)) Archive.GetShaderMapAssetAssociations().RemoveAsset(Pair.Key);
                if (!Destination.AppendFromArchive(Archive, TConstArrayView64<uint8>(Code.GetData(), Code.Num()), SourceOrigin))
                    return Fail(TEXT("native_selected_shader_append_failed"));
            }
        }
        if (Destination.IsEmpty())
        {
            if (GlobalLibrary || !Expected.IsEmpty()) return Fail(TEXT("required_shader_archive_empty"));
            continue;
        }
        if (!Destination.SaveToDisk(Output / TEXT("Content"), Output / TEXT("Metadata/PipelineCaches"),
                ShaderCodeArchive::ESaveToDiskTarget::Staging, ShaderCodeArchive::ESaveToDiskSortOrder::ShaderHash))
            return Fail(TEXT("native_selected_shader_save_failed"));
        FHistory Candidate; Candidate.Content = Output / TEXT("Content"); Candidate.Files = MakeShared<FJsonObject>();
        const FString Stem = TEXT("-") + Library + TEXT("-") + Format;
        for (const FString& Name : {TEXT("ShaderAssetInfo") + Stem + TEXT(".assetinfo.json"),
                TEXT("ShaderArchive") + Stem + TEXT(".ushaderbytecode"), TEXT("ShaderTypeInfo") + Stem + TEXT(".stinfo")})
        {
            TArray<uint8> Bytes;
            const FString Path = Candidate.Content / Name;
            if (!FFileHelper::LoadFileToArray(Bytes, *Path)) return Fail(TEXT("required_shader_output_missing"));
            Candidate.Files->SetStringField(Name, SHA(Bytes));
            ExpectedFiles.Add(TEXT("Content/") + Name);
            const FString Mirror = Output / TEXT("Metadata/ShaderLibrarySource") / Name;
            TArray<uint8> MirrorBytes;
            if (!FFileHelper::LoadFileToArray(MirrorBytes, *Mirror) || MirrorBytes != Bytes)
                return Fail(TEXT("native_shader_metadata_mirror_missing_or_different"));
            ExpectedFiles.Add(TEXT("Metadata/ShaderLibrarySource/") + Name);
        }
        FMembership Actual; TArray<FShaderHash> Native;
        if (!Membership(Candidate, Library, Format, Actual, Native, GlobalLibrary) || !SameMembership(Expected, Actual))
            return Fail(TEXT("selected_shader_membership_readback_differs"));
        if (GlobalLibrary)
        {
            if (Native.Num() != GlobalMaps.Num()) return Fail(TEXT("global_shader_roster_size_differs"));
            for (const FShaderHash& Hash : Native) if (!GlobalMaps.Contains(Hash.ToString())) return Fail(TEXT("global_shader_roster_differs"));
        }
        if (NativeLibraries)
        {
            if (!Destination.SupportsShaderArchives()) return Fail(TEXT("native_shader_archive_unsupported_by_loaded_format"));
            TArray<FString> Packed;
            if (!Destination.PackageNativeShaderLibrary(Output / TEXT("Content"), &Packed) || Packed.IsEmpty())
                return Fail(TEXT("native_shader_library_packaging_failed"));
            ExpectedFiles.Remove(TEXT("Content/ShaderArchive") + Stem + TEXT(".ushaderbytecode"));
            for (const FString& File : Packed)
            {
                // Metal's stock writer lowercases the full .metalmap path. Use
                // its observed filename with the owned output directory's case;
                // do not let a case alias escape the actual output inventory.
                if (!SameOwnedDirectory(FPaths::GetPath(FPaths::ConvertRelativePathToFull(File)),
                        FPaths::ConvertRelativePathToFull(Output / TEXT("Content"))))
                    return Fail(TEXT("native_shader_library_wrote_outside_output"));
                const FString Name = FPaths::GetCleanFilename(File);
                const FString Relative = TEXT("Content/") + Name;
                if (IFileManager::Get().FileSize(*(Output / Relative)) <= 0 || ExpectedFiles.Contains(Relative))
                    return Fail(TEXT("native_shader_library_missing_empty_or_duplicate"));
                ExpectedFiles.Add(Relative);
            }
        }
    }
    // The package-store entry covers every target shader format; compare their complete union.
    if (!GlobalLibrary) for (const auto& H : Histories) for (const FName& Package : H->Packages)
    {
        TSet<FString> Required;
        for (const FShaderHash& Hash : H->PackageShaders.FindChecked(Package)) Required.Add(Hash.ToString());
        const TSet<FString>* Associated = ObservedPackageMaps.Find(Package);
        if ((Associated ? Associated->Num() : 0) != Required.Num()) return Fail(TEXT("shader_associations_differ_from_native_record"));
        if (Associated) for (const FString& Hash : *Associated) if (!Required.Contains(Hash)) return Fail(TEXT("shader_associations_differ_from_native_record"));
    }
    TArray<FString> Outputs; IFileManager::Get().FindFilesRecursive(Outputs, *Output, TEXT("*"), true, false);
    if (Outputs.Num() != ExpectedFiles.Num()) return Fail(TEXT("global_output_census_incomplete_or_contains_extra_files"));
    TArray<TSharedPtr<FJsonValue>> Manifest;
    Outputs.Sort();
    for (const FString& File : Outputs)
    {
        FString Relative = File; FPaths::MakePathRelativeTo(Relative, *(Output + TEXT("/")));
        if (!ExpectedFiles.Remove(Relative)) return Fail(TEXT("global_output_census_differs"));
        TArray<uint8> Bytes; if (!FFileHelper::LoadFileToArray(Bytes, *File)) return Fail(TEXT("global_output_readback_failed"));
        const FObject Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("path"), Relative); Row->SetStringField(TEXT("sha256"), SHA(Bytes));
        Row->SetNumberField(TEXT("bytes"), Bytes.Num()); Manifest.Add(MakeShared<FJsonValueObject>(Row));
    }
    Report->SetArrayField(TEXT("files"), Manifest);
    Report->SetBoolField(TEXT("global_library"), GlobalLibrary);
    Report->SetBoolField(TEXT("native_libraries"), NativeLibraries);
    Report->SetNumberField(TEXT("packages"), Owner.Num());
    Report->SetNumberField(TEXT("dependency_nodes"), Visited.Num());
    // Produces the exact native files; installing their EndCook descriptors remains
    // a separately verified namespace mutation, never implied by this local result.
    Report->SetStringField(TEXT("status"), TEXT("composed"));
    return Encode(Report);
}
