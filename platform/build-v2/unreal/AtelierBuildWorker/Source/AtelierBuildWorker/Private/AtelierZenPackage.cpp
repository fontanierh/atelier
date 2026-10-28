#include "AtelierBuildWorkerLibrary.h"
#include "AssetRegistry/AssetRegistryState.h"
#include "CookMetadata.h"
#include "PackageStoreOptimizer.h"
#include "UObject/ICookInfo.h"
#include "UObject/NameBatchSerialization.h"
#include <CommonCrypto/CommonDigest.h>
#include "Compression/CompressedBuffer.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "IO/IoHash.h"
#include "IO/IoChunkId.h"
#include "Memory/SharedBuffer.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Serialization/BufferArchive.h"
#include "Serialization/CompactBinaryPackage.h"
#include "Serialization/CompactBinaryValidation.h"
#include "Serialization/CompactBinaryWriter.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/PackageStore.h"
#include "ZenStoreHttpClient.h"
#include "ZenServerHttp.h"

namespace
{
using FObject = TSharedPtr<FJsonObject>;

FString Encode(const FObject& Object)
{
    FString Text;
    FJsonSerializer::Serialize(Object.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    return Text;
}

bool Hex(const FString& Value, int32 Length)
{
    if (Value.Len() != Length) return false;
    for (TCHAR C : Value) if (!FChar::IsHexDigit(C)) return false;
    return true;
}

bool Namespace(const FString& Value)
{
    if (Value.IsEmpty()) return false;
    for (TCHAR C : Value)
        if (!FChar::IsAlnum(C) && C != '_' && C != '-') return false;
    return true;
}

bool Absolute(const FString& Value)
{
    return !Value.IsEmpty() && !FPaths::IsRelative(Value);
}

bool SameDirectory(FString A, FString B)
{
    if (!Absolute(A) || !Absolute(B)) return false;
    FPaths::NormalizeDirectoryName(A);
    FPaths::NormalizeDirectoryName(B);
    return FPaths::IsSamePath(A, B);
}

// A native HTTP 200 with valid CB is required before InitializeReadOnly (whose missing-project
// branch is Fatal), and before any edit-capable client is opened. Never adopt an unknown locator.
bool Metadata(UE::FZenStoreHttpClient& Client, const FString& Uri, FCbObject& Result, FString& Error)
{
    UE::Zen::FZenHttpRequest Request(Client.GetZenServiceInstance().GetEndpoint(), false, 3000, 5000);
    TArray64<uint8> Bytes;
    if (Request.PerformBlockingDownload(Uri, &Bytes, UE::Zen::EContentType::CbObject)
            != UE::Zen::FZenHttpRequest::Result::Success
        || Request.GetErrorCode() != 0 || Request.GetResponseCode() != 200 || Bytes.IsEmpty()
        || ValidateCompactBinary(MakeMemoryView(Bytes), ECbValidateMode::All) != ECbValidateError::None)
    {
        Error = FString::Printf(TEXT("metadata_http_%d_transport_%d_bytes_%lld"),
            Request.GetResponseCode(), Request.GetErrorCode(), Bytes.Num());
        return false;
    }
    Result = FCbObject(FSharedBuffer::Clone(Bytes.GetData(), Bytes.Num()));
    return true;
}

bool BindNamespace(UE::FZenStoreHttpClient& Client, const FString& Project, const FString& Oplog,
    const FString& ProjectFile, const FString& Marker, FString& Error)
{
    FCbObject Info, Log;
    if (!Metadata(Client, TEXT("/prj/") + Project, Info, Error)
        || !Metadata(Client, TEXT("/prj/") + Project + TEXT("/oplog/") + Oplog, Log, Error)) return false;
    const TArray<TPair<const TCHAR*, bool>> Checks{
        {TEXT("project_id"), FString(Info["id"].AsString()) == Project},
        {TEXT("project_file"), FPaths::IsSamePath(FString(Info["projectfile"].AsString()), ProjectFile)},
        {TEXT("project_directory"), SameDirectory(FString(Info["project"].AsString()), FPaths::GetPath(ProjectFile))},
        {TEXT("engine_directory"), SameDirectory(FString(Info["engine"].AsString()), FPaths::ConvertRelativePathToFull(FPaths::EngineDir()))},
        {TEXT("root_directory"), SameDirectory(FString(Info["root"].AsString()), FPaths::ConvertRelativePathToFull(FPaths::RootDir()))},
        {TEXT("oplog_id"), FString(Log["id"].AsString()) == Oplog},
        {TEXT("oplog_project"), FString(Log["project"].AsString()) == Project},
        {TEXT("oplog_marker"), !FString(Log["markerpath"].AsString()).IsEmpty()
            && FPaths::IsSamePath(FString(Log["markerpath"].AsString()), Marker)},
        {TEXT("marker_presence"), IFileManager::Get().FileExists(*Marker)}};
    for (const auto& Check : Checks)
        if (!Check.Value) { Error = Check.Key; return false; }
    return true;
}

FSharedBuffer Raw(const FCbAttachment& Attachment)
{
    return Attachment.IsObject() ? Attachment.AsObject().GetBuffer().ToShared()
        : Attachment.IsCompressedBinary() ? Attachment.AsCompressedBinary().Decompress() : Attachment.AsBinary();
}

constexpr const ANSICHAR* RecordSchema = "atelier-zen-package-record/1";

FCbObject NativeEntry(const FCbPackage& Package)
{
    const FCbObject Root = Package.GetObject();
    return Root["record_schema"].HasValue() ? Root["entry"].AsObject() : Root;
}

// A retained auxiliary is bound to exactly one native descriptor id in the original entry.
// It is not a claim that the recorded native dependency key has been evaluated against current source.
bool Auxiliary(const FCbPackage& Package, const FCbObject& Entry, TMap<FIoChunkId, FIoHash>& Files, FString& Error)
{
    const FCbObject Container = Package.GetObject();
    if (Container["record_schema"].HasValue())
    {
        if (Container["record_schema"].AsString() != RecordSchema || !Container["entry"].IsObject()
            || !Container["auxiliary"].IsArray())
        { Error = TEXT("invalid_auxiliary_record_schema"); return false; }
        for (FCbFieldView Field : Container)
            if (Field.GetName() != "record_schema" && Field.GetName() != "entry" && Field.GetName() != "auxiliary")
            { Error = TEXT("unknown_auxiliary_record_field"); return false; }
        for (FCbFieldView File : Container["auxiliary"].AsArrayView())
        {
            FIoChunkId Id;
            if (!File.IsObject() || !LoadFromCompactBinary(File["id"], Id) || !Id.IsValid()
                || !File["data"].IsBinaryAttachment() || !File["size"].IsInteger() || Files.Contains(Id))
            { Error = TEXT("invalid_auxiliary_binding"); return false; }
            for (FCbFieldView Field : File.AsObjectView())
                if (Field.GetName() != "id" && Field.GetName() != "data" && Field.GetName() != "size")
                { Error = TEXT("unknown_auxiliary_binding_field"); return false; }
            const FIoHash Hash = File["data"].AsAttachment();
            const FCbAttachment* Attachment = Package.FindAttachment(Hash);
            if (Hash.IsZero() || !Attachment || Raw(*Attachment).GetSize() != File["size"].AsUInt64(MAX_uint64))
            { Error = TEXT("missing_auxiliary_bytes_or_size_mismatch"); return false; }
            Files.Add(Id, Hash);
        }
    }
    if (Entry["files"].HasValue() && !Entry["files"].IsArray())
    { Error = TEXT("invalid_native_file_roster"); return false; }
    TSet<FIoChunkId> Seen;
    int32 Required = 0;
    for (FCbFieldView File : Entry["files"].AsArrayView())
    {
        FIoChunkId Id;
        if (!File.IsObject() || !LoadFromCompactBinary(File["id"], Id) || !Id.IsValid()
            || Seen.Contains(Id) || !File["clientpath"].IsString() || File["clientpath"].AsString().IsEmpty())
        { Error = TEXT("invalid_native_file_identity"); return false; }
        Seen.Add(Id);
        if (File["data"].AsHash().IsZero())
        {
            ++Required;
            if (!File["serverpath"].IsString() || File["serverpath"].AsString().IsEmpty() || !Files.Contains(Id))
            { Error = TEXT("file_backed_auxiliary_not_retained"); return false; }
        }
        else if (!File["data"].IsBinaryAttachment() || File["serverpath"].HasValue() || Files.Contains(Id))
        { Error = TEXT("ambiguous_native_file_data"); return false; }
    }
    if (Files.Num() != Required)
    { Error = TEXT("auxiliary_roster_differs_from_native_entry"); return false; }
    return true;
}

bool RetainAuxiliary(UE::FZenStoreHttpClient& Client, FCbPackage& Package, FString& Error)
{
    const FCbObject Entry = Package.GetObject();
    TArray<TPair<FIoChunkId, FCbAttachment>> Files;
    TSet<FIoChunkId> Seen;
    for (FCbFieldView File : Entry["files"].AsArrayView())
    {
        if (!File["data"].AsHash().IsZero()) continue;
        FIoChunkId Id;
        if (!LoadFromCompactBinary(File["id"], Id) || !Id.IsValid() || Seen.Contains(Id))
        { Error = TEXT("invalid_native_auxiliary_id"); return false; }
        Seen.Add(Id);
        auto Result = Client.ReadChunk(Id);
        if (!Result.IsOk()) { Error = TEXT("native_auxiliary_read_failed"); return false; }
        const FIoBuffer Bytes = Result.ConsumeValueOrDie();
        const FSharedBuffer Owned = FSharedBuffer::Clone(Bytes.GetData(), Bytes.DataSize());
        Files.Emplace(Id, FCbAttachment(FCompressedBuffer::Compress(Owned)));
    }
    if (Files.IsEmpty()) return true;
    FCbWriter Writer;
    Writer.BeginObject();
    Writer << "record_schema" << RecordSchema;
    Writer.AddObject("entry", Entry);
    Writer.BeginArray("auxiliary");
    for (const auto& File : Files)
    {
        Writer.BeginObject();
        Writer << "id" << File.Key;
        Writer << "data" << File.Value;
        Writer << "size" << Raw(File.Value).GetSize();
        Writer.EndObject();
    }
    Writer.EndArray();
    Writer.EndObject();
    FCbPackage Retained(Writer.Save().AsObject());
    for (const FCbAttachment& Attachment : Package.GetAttachments()) Retained.AddAttachment(Attachment);
    for (const auto& File : Files) Retained.AddAttachment(File.Value);
    // Source file-backed chunks can change without changing the zero-hash root. Re-read all of them
    // before publishing the retained record, rather than treating an unchanged entry as a byte witness.
    for (const auto& File : Files)
    {
        auto Current = Client.ReadChunk(File.Key);
        if (!Current.IsOk() || FIoHash::HashBuffer(Current.ConsumeValueOrDie().GetView()) != File.Value.GetHash())
        { Error = TEXT("native_auxiliary_changed_during_capture"); return false; }
    }
    Package = MoveTemp(Retained);
    return true;
}

bool Validate(const FCbPackage& Package, const FString& Name, const FString& ExpectedRoot,
    const FString& ExpectedStoredKey, FString& StoredKey, FString& Error)
{
    const FCbObject Container = Package.GetObject();
    const FCbObject Root = NativeEntry(Package);
    if (!Root || !Container || ValidateCompactBinary(Container.GetBuffer().ToShared().GetView(), ECbValidateMode::All) != ECbValidateError::None
        || Package.GetObjectHash() != Container.GetHash()
        || (!ExpectedRoot.IsEmpty() && LexToString(Root.GetHash()) != ExpectedRoot))
    { Error = TEXT("root_hash_or_compact_binary"); return false; }
    const FCbObjectView StoreObject = Root["packagestoreentry"].AsObjectView();
    if (!StoreObject) { Error = TEXT("missing_package_store_entry"); return false; }
    const FPackageStoreEntryResource Store = FPackageStoreEntryResource::FromCbObject(StoreObject);
    if (Store.PackageName.ToString() != Name || FString(Root["key"].AsString()) != Name.ToLower()
        || Store.HasCookError() || !EnumHasAnyFlags(Store.Flags, EPackageStoreEntryFlags::HasPackageData))
    { Error = TEXT("source_package_identity_or_cook_error"); return false; }
    TMap<FIoChunkId, FIoHash> Files;
    if (!Auxiliary(Package, Root, Files, Error)) return false;
    bool Complete = true;
    auto References = [&](const FCbObject& Object)
    {
        Object.IterateAttachments([&](FCbFieldView Field)
        {
            if (!Package.FindAttachment(Field.AsAttachment())) Complete = false;
        });
    };
    References(Container);
    for (const FCbAttachment& Attachment : Package.GetAttachments())
    {
        const FSharedBuffer Bytes = Raw(Attachment);
        if (!Bytes || FIoHash::HashBuffer(Bytes.GetView()) != Attachment.GetHash())
        { Error = TEXT("attachment_hash_or_decompression"); return false; }
        if (Attachment.IsObject())
        {
            if (ValidateCompactBinary(Bytes.GetView(), ECbValidateMode::All) != ECbValidateError::None)
            { Error = TEXT("attachment_compact_binary"); return false; }
            References(Attachment.AsObject());
        }
    }
    if (!Complete) { Error = TEXT("missing_referenced_attachment"); return false; }
    const FIoHash ArtifactsHash = Root["meta.cook.artifacts"].AsHash();
    const FCbAttachment* Artifacts = Package.FindAttachment(ArtifactsHash);
    if (ArtifactsHash.IsZero() || !Artifacts)
    { Error = TEXT("missing_native_dependency_artifacts"); return false; }
    const FSharedBuffer Bytes = Raw(*Artifacts);
    if (!Bytes || ValidateCompactBinary(Bytes.GetView(), ECbValidateMode::All) != ECbValidateError::None)
    { Error = TEXT("native_artifacts_compact_binary"); return false; }
    const FIoHash NativeKey = FCbObject(Bytes)["SaveBuildDependencies"]["StoredKey"].AsHash();
    StoredKey = LexToString(NativeKey);
    if (NativeKey.IsZero() || (!ExpectedStoredKey.IsEmpty() && StoredKey != ExpectedStoredKey))
    { Error = TEXT("native_stored_key_mismatch"); return false; }
    return true;
}

bool Load(const FString& Path, FCbPackage& Package, FIoHash& RecordHash)
{
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Path) || Bytes.IsEmpty()
        || ValidateCompactBinaryPackage(MakeMemoryView(Bytes), ECbValidateMode::All) != ECbValidateError::None)
        return false;
    FMemoryReader Reader(Bytes, true);
    if (!Package.TryLoad(Reader) || Reader.IsError() || Reader.Tell() != Reader.TotalSize()) return false;
    RecordHash = FIoHash::HashBuffer(MakeMemoryView(Bytes));
    return true;
}

bool Wire(const FCbPackage& Source, FCbPackage& Result)
{
    const FCbObject Entry = NativeEntry(Source);
    TMap<FIoChunkId, FIoHash> Files;
    FString Error;
    if (!Auxiliary(Source, Entry, Files, Error)) return false;
    FCbObject Installed = Entry;
    if (!Files.IsEmpty())
    {
        FCbWriter Writer;
        Writer.BeginObject();
        for (FCbFieldView Field : Entry)
        {
            if (Field.GetName() != "files") { Writer.AddField(Field.GetName(), Field); continue; }
            Writer.BeginArray("files");
            for (FCbFieldView File : Field.AsArrayView())
            {
                FIoChunkId Id;
                if (!LoadFromCompactBinary(File["id"], Id)) return false;
                const FIoHash* Hash = Files.Find(Id);
                if (!Hash) { Writer.AddField(File); continue; }
                Writer.BeginObject();
                for (FCbFieldView Value : File.AsObjectView())
                    if (Value.GetName() != "data" && Value.GetName() != "serverpath") Writer.AddField(Value.GetName(), Value);
                Writer << "data" << *Source.FindAttachment(*Hash);
                Writer.EndObject();
            }
            Writer.EndArray();
        }
        Writer.EndObject();
        Installed = Writer.Save().AsObject();
    }
    Result = FCbPackage(Installed, Installed.GetHash());
    for (const FCbAttachment& Attachment : Source.GetAttachments())
    {
        const FSharedBuffer Bytes = Raw(Attachment);
        if (!Bytes) return false;
        const FCompressedBuffer Compressed = FCompressedBuffer::Compress(Bytes);
        const FSharedBuffer Decoded = Compressed.Decompress();
        if (!Decoded || Decoded.GetSize() != Bytes.GetSize()
            || FIoHash::HashBuffer(Decoded.GetView()) != Attachment.GetHash()) return false;
        Result.AddAttachment(FCbAttachment(Compressed));
    }
    return Result.GetAttachments().Num() == Source.GetAttachments().Num();
}
}

FString UAtelierBuildWorkerLibrary::ZenPackageRequest(const FString& RequestJson)
{
    const FObject Report = MakeShared<FJsonObject>();
    Report->SetNumberField(TEXT("version"), 1);
    Report->SetStringField(TEXT("status"), TEXT("refused"));
    auto Refuse = [&](const FString& Error)
    {
        Report->SetStringField(TEXT("error"), Error);
        return Encode(Report);
    };
    FObject Request;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(RequestJson), Request) || !Request)
        return Refuse(TEXT("invalid_request_json"));
    const TArray<FString> Fields{TEXT("mode"), TEXT("project"), TEXT("oplog"), TEXT("source_package"),
        TEXT("expected_stored_key"), TEXT("expected_root_hash"), TEXT("record_path"), TEXT("project_file"),
        TEXT("marker_path"), TEXT("input_key"), TEXT("runtime_project_file")};
    double Version = 0;
    if (Request->Values.Num() != Fields.Num() + 1 || !Request->TryGetNumberField(TEXT("version"), Version) || Version != 1)
        return Refuse(TEXT("unknown_or_missing_request_fields"));
    TMap<FString, FString> Values;
    for (const FString& Field : Fields)
    {
        FString Value;
        if (!Request->TryGetStringField(Field, Value)) return Refuse(TEXT("missing_string_field"));
        Values.Add(Field, Value);
    }
    auto Get = [&](const TCHAR* Field) -> const FString& { return Values.FindChecked(Field); };
    const FString Mode = Get(TEXT("mode"));
    const FString Project = Get(TEXT("project")), Oplog = Get(TEXT("oplog"));
    const FString Name = Get(TEXT("source_package")), Record = Get(TEXT("record_path"));
    const FString ExpectedRoot = Get(TEXT("expected_root_hash")).ToLower();
    const FString ExpectedStored = Get(TEXT("expected_stored_key")).ToLower();
    const FString ProjectFile = Get(TEXT("project_file")), Marker = Get(TEXT("marker_path"));
    if ((Mode != TEXT("capture") && Mode != TEXT("verify") && Mode != TEXT("restore"))
        || !Namespace(Project) || !Namespace(Oplog) || !FPackageName::IsValidLongPackageName(Name)
        || !Absolute(Record) || !Absolute(ProjectFile) || !Absolute(Marker)
        || !Hex(Get(TEXT("input_key")), 64)
        || !(Hex(ExpectedRoot, 40) || (Mode == TEXT("capture") && ExpectedRoot.IsEmpty()))
        || !(Hex(ExpectedStored, 40) || (Mode == TEXT("capture") && ExpectedStored.IsEmpty()))
        || !Absolute(Get(TEXT("runtime_project_file")))
        || !FPaths::IsSamePath(Get(TEXT("runtime_project_file")), FPaths::ConvertRelativePathToFull(FPaths::GetProjectFilePath())))
        return Refuse(TEXT("invalid_identity_or_runtime_context"));
    UE::FZenStoreHttpClient Client;
    FString NamespaceError;
    if (!BindNamespace(Client, Project, Oplog, ProjectFile, Marker, NamespaceError))
        return Refuse(TEXT("unknown_or_changed_native_namespace:") + NamespaceError);
    FCbPackage Package;
    FIoHash RecordHash;
    FString StoredKey, Error;
    if (Mode == TEXT("capture"))
    {
        Client.InitializeReadOnly(Project, Oplog);
        auto Entries = Client.GetOplogEntries(Project, Oplog, TArray<FString>{Name.ToLower()}).Get();
        if (Entries.Num() != 1 || !Entries[0].IsOk()) return Refuse(TEXT("native_package_read_failed"));
        const FCbObject Root = Entries[0].ConsumeValueOrDie()["entry"].AsObject();
        bool Resolved = true;
        Package = FCbPackage(Root, [&](const FIoHash& Hash) -> FSharedBuffer
        {
            auto Chunk = Client.ReadChunk(Hash);
            if (!Chunk.IsOk()) { Resolved = false; return {}; }
            const FIoBuffer Bytes = Chunk.ConsumeValueOrDie();
            if (FIoHash::HashBuffer(Bytes.GetView()) != Hash) { Resolved = false; return {}; }
            return FSharedBuffer::Clone(Bytes.GetData(), Bytes.DataSize());
        });
        if (!Resolved || !RetainAuxiliary(Client, Package, Error)
            || !Validate(Package, Name, ExpectedRoot, ExpectedStored, StoredKey, Error))
            return Refuse(Error.IsEmpty() ? TEXT("native_attachment_read_failed") : Error);
        FBufferArchive Bytes;
        Package.Save(Bytes);
        // No overwrite, including a prior interrupted capture. A caller must choose a new lease path.
        const TUniquePtr<FArchive> Writer(IFileManager::Get().CreateFileWriter(*Record, FILEWRITE_NoReplaceExisting));
        if (!Writer) return Refuse(TEXT("record_path_not_fresh"));
        Writer->Serialize(Bytes.GetData(), Bytes.Num());
        if (!Writer->Close() || Writer->IsError()) return Refuse(TEXT("record_write_failed"));
        FCbPackage Readback;
        if (!Load(Record, Readback, RecordHash) || Readback != Package)
            return Refuse(TEXT("record_readback_failed"));
    }
    else
    {
        if (!Load(Record, Package, RecordHash)
            || !Validate(Package, Name, ExpectedRoot, ExpectedStored, StoredKey, Error))
            return Refuse(Error.IsEmpty() ? TEXT("invalid_record") : Error);
    }
    FIoHash InstalledRoot = NativeEntry(Package).GetHash();
    if (Mode == TEXT("restore"))
    {
        // Only an observed, already-owned namespace may be opened for writing; never create an oplog.
        if (!Client.TryCreateProject(Project, FStringView(), Oplog,
                FPaths::ConvertRelativePathToFull(FPaths::RootDir()),
                FPaths::ConvertRelativePathToFull(FPaths::EngineDir()), FPaths::GetPath(ProjectFile), ProjectFile)
            || !BindNamespace(Client, Project, Oplog, ProjectFile, Marker, NamespaceError))
            return Refuse(TEXT("destination_binding_failed"));
        FCbPackage Encoded;
        if (!Wire(Package, Encoded)) return Refuse(TEXT("wire_compression_verification_failed"));
        InstalledRoot = Encoded.GetObjectHash();
        auto Appended = Client.AppendOp(MoveTemp(Encoded));
        if (!Appended.IsOk()) return Refuse(TEXT("append_failed_destination_uncertain"));
        auto Readback = Client.GetOplogEntries(Project, Oplog, TArray<FString>{Name.ToLower()}).Get();
        if (Readback.Num() != 1 || !Readback[0].IsOk()
            || Readback[0].ConsumeValueOrDie()["entry"].AsObject().GetHash() != InstalledRoot)
            return Refuse(TEXT("append_readback_failed_destination_uncertain"));
        for (const FCbAttachment& Attachment : Package.GetAttachments())
        {
            auto Chunk = Client.ReadChunk(Attachment.GetHash());
            if (!Chunk.IsOk() || FIoHash::HashBuffer(Chunk.ConsumeValueOrDie().GetView()) != Attachment.GetHash())
                return Refuse(TEXT("restored_attachment_readback_failed_destination_uncertain"));
        }
    }
    const FTCHARToUTF8 RequestBytes(*RequestJson);
    Report->SetStringField(TEXT("request_io_hash"), LexToString(FIoHash::HashBuffer(MakeMemoryView(RequestBytes.Get(), RequestBytes.Length()))));
    for (const TCHAR* Field : {TEXT("mode"), TEXT("project"), TEXT("oplog"), TEXT("source_package"), TEXT("input_key"), TEXT("runtime_project_file")})
        Report->SetStringField(Field, Get(Field));
    Report->SetStringField(TEXT("root_hash"), LexToString(NativeEntry(Package).GetHash()));
    Report->SetStringField(TEXT("installed_root_hash"), Mode == TEXT("restore") ? LexToString(InstalledRoot) : FString());
    Report->SetStringField(TEXT("source_dependency_evaluation"), TEXT("recorded_only"));
    Report->SetStringField(TEXT("native_stored_key"), StoredKey);
    Report->SetStringField(TEXT("record_io_hash"), LexToString(RecordHash));
    Report->SetNumberField(TEXT("attachments"), Package.GetAttachments().Num());
    Report->SetStringField(TEXT("status"), Mode == TEXT("restore") ? TEXT("restored") : TEXT("verified"));
    return Encode(Report);
}

namespace
{
FString SHA256Bytes(TConstArrayView<uint8> Bytes)
{
    uint8 Digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(Bytes.GetData(), CC_LONG(Bytes.Num()), Digest);
    FString Text;
    for (uint8 Byte : Digest) Text += FString::Printf(TEXT("%02x"), Byte);
    return Text;
}

bool ExactFields(const FObject& Object, std::initializer_list<const TCHAR*> Fields)
{
    if (!Object || Object->Values.Num() != int32(Fields.size())) return false;
    for (const TCHAR* Field : Fields) if (!Object->HasField(Field)) return false;
    return true;
}

FString StringField(const FObject& Object, const TCHAR* Field)
{
    FString Value;
    if (Object) Object->TryGetStringField(Field, Value);
    return Value;
}

bool ClientFilePath(const FString& Path)
{
    FString Relative;
    if (Path.StartsWith(TEXT("/{project}/"))) Relative = Path.Mid(11);
    else if (Path.StartsWith(TEXT("/{engine}/"))) Relative = Path.Mid(10);
    else return false;
    if (Relative.IsEmpty() || Relative.Contains(TEXT("\\"))) return false;
    for (TCHAR C : Path) if (C < 32) return false;
    TArray<FString> Parts; Relative.ParseIntoArray(Parts, TEXT("/"), false);
    for (const FString& Part : Parts) if (Part.IsEmpty() || Part == TEXT(".") || Part == TEXT("..")) return false;
    return true;
}

bool SavePackageNoReplace(const FString& Path, const FCbPackage& Package)
{
    FBufferArchive Bytes; Package.Save(Bytes);
    const TUniquePtr<FArchive> Writer(IFileManager::Get().CreateFileWriter(*Path, FILEWRITE_NoReplaceExisting));
    if (!Writer) return false;
    Writer->Serialize(Bytes.GetData(), Bytes.Num());
    if (Writer->IsError() || !Writer->Close()) return false;
    FCbPackage Readback; FIoHash Hash;
    return Load(Path, Readback, Hash) && Readback == Package;
}

bool ScriptObjectsValid(const FIoBuffer& Buffer, int32& Count)
{
    if (Buffer.DataSize() > MAX_int32 || Buffer.DataSize() == 0) return false;
    TArray<uint8> Bytes; Bytes.Append(Buffer.Data(), int32(Buffer.DataSize()));
    FMemoryReader Reader(Bytes, true);
    const TArray<FDisplayNameEntryId> Names = LoadNameBatch(Reader);
    Reader << Count;
    if (Reader.IsError() || Count < 0 || int64(Count) > (Reader.TotalSize() - Reader.Tell()) / 32) return false;
    TSet<FPackageObjectIndex> Ids;
    TArray<FScriptObjectEntry> Entries; Entries.Reserve(Count);
    for (int32 Index = 0; Index < Count; ++Index)
    {
        FScriptObjectEntry Entry{}; Reader << Entry;
        if (Reader.IsError() || !Names.IsValidIndex(Entry.Mapped.GetIndex()) || !Entry.GlobalIndex.IsScriptImport()
            || Ids.Contains(Entry.GlobalIndex)) return false;
        Ids.Add(Entry.GlobalIndex); Entries.Add(Entry);
    }
    if (Reader.Tell() != Reader.TotalSize()) return false;
    for (const FScriptObjectEntry& Entry : Entries)
        if ((!Entry.OuterIndex.IsNull() && !Ids.Contains(Entry.OuterIndex))
            || (!Entry.CDOClassIndex.IsNull() && !Ids.Contains(Entry.CDOClassIndex))) return false;
    return true;
}

struct FNativeGlobalFile
{
    FString ClientPath;
    FString Path;
    FString SHA256;
    FIoChunkId Id;
    FCbAttachment Attachment;
};
}

FString UAtelierBuildWorkerLibrary::ZenEndCookRequest(const FString& RequestJson)
{
    const FObject Report = MakeShared<FJsonObject>();
    Report->SetNumberField(TEXT("version"), 1);
    Report->SetStringField(TEXT("status"), TEXT("refused"));
    auto Fail = [&](const FString& Error) { Report->SetStringField(TEXT("error"), Error); return Encode(Report); };
    FObject Request;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(RequestJson), Request)
        || !ExactFields(Request, {TEXT("version"), TEXT("project"), TEXT("oplog"), TEXT("project_file"),
            TEXT("marker_path"), TEXT("runtime_project_file"), TEXT("input_key"), TEXT("packages"), TEXT("globals"), TEXT("output_dir"), TEXT("source_files")}))
        return Fail(TEXT("unknown_or_missing_endcook_fields"));
    double Version = 0;
    const FString Project = StringField(Request, TEXT("project")), Oplog = StringField(Request, TEXT("oplog"));
    const FString ProjectFile = StringField(Request, TEXT("project_file")), Marker = StringField(Request, TEXT("marker_path"));
    const FString RuntimeProject = StringField(Request, TEXT("runtime_project_file")), Output = StringField(Request, TEXT("output_dir"));
    const TArray<TSharedPtr<FJsonValue>>* Packages = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* GlobalSpecs = nullptr;
    if (!Request->TryGetNumberField(TEXT("version"), Version) || Version != 1 || !Namespace(Project) || Oplog != TEXT("Mac")
        || !Absolute(ProjectFile) || !Absolute(Marker) || !Absolute(Output) || !Absolute(RuntimeProject)
        || !FPaths::IsSamePath(RuntimeProject, FPaths::ConvertRelativePathToFull(FPaths::GetProjectFilePath()))
        || !Hex(StringField(Request, TEXT("input_key")), 64) || IFileManager::Get().DirectoryExists(*Output)
        || IFileManager::Get().FileExists(*Output) || !Request->TryGetArrayField(TEXT("packages"), Packages) || Packages->IsEmpty()
        || !Request->TryGetArrayField(TEXT("globals"), GlobalSpecs) || GlobalSpecs->IsEmpty())
        return Fail(TEXT("invalid_endcook_identity_roster_or_output"));
    UE::FZenStoreHttpClient Client;
    FString Error;
    if (!BindNamespace(Client, Project, Oplog, ProjectFile, Marker, Error)) return Fail(TEXT("unknown_namespace:") + Error);
    Client.InitializeReadOnly(Project, Oplog);
    TMap<FName, FString> ExpectedRoots;
    TMap<FIoChunkId, FIoHash> Chunks;
    TMap<FIoChunkId, FString> FilePaths;
    const TArray<TSharedPtr<FJsonValue>>* SourceFiles = nullptr;
    if (!Request->TryGetArrayField(TEXT("source_files"), SourceFiles) || SourceFiles->Num() > 32768)
        return Fail(TEXT("invalid_source_file_ledger"));
    for (const auto& Value : *SourceFiles)
    {
        const FObject File = Value->AsObject();
        if (!ExactFields(File, {TEXT("id"), TEXT("clientpath")})) return Fail(TEXT("invalid_source_file_ledger_row"));
        const FString Path = StringField(File, TEXT("clientpath"));
        const FIoChunkId Id = CreateExternalFileChunkId(Path);
        if (!ClientFilePath(Path) || LexToString(Id) != StringField(File, TEXT("id")) || FilePaths.Contains(Id))
            return Fail(TEXT("invalid_or_duplicate_source_file_ledger_identity"));
        // Membership comes only from the certified source cook's frozen zenfs ledger.
        // Runtime loose bytes are separately supplied as hashed semantic Globals.
        FilePaths.Add(Id, Path);
    }
    TArray<FPackageStoreEntryResource> Stores;
    TSet<FPackageId> PackageIds;
    int32 Done = 0;
    for (const auto& Value : *Packages)
    {
        const FObject Spec = Value->AsObject();
        if (!ExactFields(Spec, {TEXT("name"), TEXT("installed_root_hash")})) return Fail(TEXT("unknown_package_roster_fields"));
        const FString Name = StringField(Spec, TEXT("name")), Hash = StringField(Spec, TEXT("installed_root_hash")).ToLower();
        const FName Key(*Name);
        if (!FPackageName::IsValidLongPackageName(Name) || !Hex(Hash, 40) || ExpectedRoots.Contains(Key))
            return Fail(TEXT("invalid_or_duplicate_package_roster"));
        auto Entries = Client.GetOplogEntries(Project, Oplog, TArray<FString>{Name.ToLower()}).Get();
        if (Entries.Num() != 1 || !Entries[0].IsOk()) return Fail(TEXT("chosen_native_package_missing"));
        const FCbObject Entry = Entries[0].ConsumeValueOrDie()["entry"].AsObject();
        if (!Entry || LexToString(Entry.GetHash()) != Hash) return Fail(TEXT("chosen_native_package_root_changed"));
        bool Resolved = true;
        FCbPackage Package(Entry, [&](const FIoHash& Blob) -> FSharedBuffer
        {
            auto Bytes = Client.ReadChunk(Blob);
            if (!Bytes.IsOk()) { Resolved = false; return {}; }
            const FIoBuffer Data = Bytes.ConsumeValueOrDie();
            if (FIoHash::HashBuffer(Data.GetView()) != Blob) { Resolved = false; return {}; }
            return FSharedBuffer::Clone(Data.GetData(), Data.DataSize());
        });
        FString StoredKey;
        if (!Resolved || !Validate(Package, Name, Hash, FString(), StoredKey, Error))
            return Fail(TEXT("chosen_native_package_incomplete:") + Error);
        if (!Entry["packagedata"].IsArray() || Entry["packagedata"].AsArrayView().Num() == 0)
            return Fail(TEXT("chosen_package_has_no_native_payload"));
        for (const ANSICHAR* Group : {"packagedata", "bulkdata", "files"})
        {
            if (Entry[Group].HasValue() && !Entry[Group].IsArray()) return Fail(TEXT("invalid_native_chunk_roster"));
            for (FCbFieldView Chunk : Entry[Group].AsArrayView())
            {
                FIoChunkId Id;
                if (!Chunk.IsObject() || !LoadFromCompactBinary(Chunk["id"], Id) || !Id.IsValid()
                    || !Chunk["data"].IsBinaryAttachment()) return Fail(TEXT("unretained_or_invalid_native_chunk"));
                const FIoHash Blob = Chunk["data"].AsAttachment();
                const FCbAttachment* Attachment = Package.FindAttachment(Blob);
                if (!Attachment || Blob.IsZero()) return Fail(TEXT("native_chunk_attachment_missing"));
                const FIoHash* Prior = Chunks.Find(Id);
                if (Prior && *Prior != Blob) return Fail(TEXT("chosen_native_chunk_ownership_conflict"));
                const FSharedBuffer Bytes = Raw(*Attachment);
                if (Chunk["rawsize"].HasValue() && (!Chunk["rawsize"].IsInteger()
                    || Chunk["rawsize"].AsUInt64(MAX_uint64) != Bytes.GetSize())) return Fail(TEXT("native_chunk_size_mismatch"));
                auto ById = Client.ReadChunk(Id);
                if (!ById.IsOk() || FIoHash::HashBuffer(ById.ConsumeValueOrDie().GetView()) != Blob)
                    return Fail(TEXT("native_chunk_id_mapping_changed"));
                Chunks.Add(Id, Blob);
                if (Chunk["clientpath"].HasValue())
                {
                    const FString Path(Chunk["clientpath"].AsString());
                    if (!ClientFilePath(Path) || CreateExternalFileChunkId(Path) != Id) return Fail(TEXT("native_file_id_path_mismatch"));
                    FilePaths.Add(Id, Path);
                }
            }
        }
        FPackageStoreEntryResource Store = FPackageStoreEntryResource::FromCbObject(Entry["packagestoreentry"].AsObjectView());
        PackageIds.Add(Store.PackageId); Stores.Add(MoveTemp(Store)); ExpectedRoots.Add(Key, Hash);
        UE_LOG(LogTemp, Display, TEXT("Atelier EndCook: verified package %d/%d %s"), ++Done, Packages->Num(), *Name);
    }
    for (const FPackageStoreEntryResource& Store : Stores)
    {
        for (FPackageId Id : Store.ImportedPackageIds) if (!PackageIds.Contains(Id)) return Fail(TEXT("chosen_imported_package_missing"));
        for (FPackageId Id : Store.OptionalSegmentImportedPackageIds) if (!PackageIds.Contains(Id)) return Fail(TEXT("chosen_optional_imported_package_missing"));
    }
    const FString ReferencedClient = TEXT("/{project}/Metadata/") + FString(UE::Cook::GetReferencedSetFilename());
    TArray<FNativeGlobalFile> Globals;
    TSet<FString> ClientNames;
    TMap<FString, int32> GlobalIndexes;
    for (const auto& Value : *GlobalSpecs)
    {
        const FObject Spec = Value->AsObject();
        if (!ExactFields(Spec, {TEXT("clientpath"), TEXT("path"), TEXT("sha256")})) return Fail(TEXT("unknown_global_file_fields"));
        FNativeGlobalFile File;
        File.ClientPath = StringField(Spec, TEXT("clientpath")); File.Path = StringField(Spec, TEXT("path"));
        File.SHA256 = StringField(Spec, TEXT("sha256")).ToLower();
        if (!ClientFilePath(File.ClientPath) || !Absolute(File.Path) || !Hex(File.SHA256, 64)
            || File.ClientPath == ReferencedClient || ClientNames.Contains(File.ClientPath)) return Fail(TEXT("invalid_global_file_identity"));
        File.Id = CreateExternalFileChunkId(File.ClientPath);
        TArray<uint8> Bytes;
        if (!FFileHelper::LoadFileToArray(Bytes, *File.Path) || SHA256Bytes(Bytes) != File.SHA256)
            return Fail(TEXT("declared_global_file_hash_changed"));
        File.Attachment = FCbAttachment(FCompressedBuffer::Compress(FSharedBuffer::Clone(Bytes.GetData(), Bytes.Num())));
        const FIoHash* Prior = Chunks.Find(File.Id);
        if (Prior && *Prior != File.Attachment.GetHash()) return Fail(TEXT("global_and_package_file_conflict"));
        if (FilePaths.Contains(File.Id) && FilePaths[File.Id] != File.ClientPath) return Fail(TEXT("global_file_alias"));
        Chunks.Add(File.Id, File.Attachment.GetHash()); FilePaths.Add(File.Id, File.ClientPath);
        ClientNames.Add(File.ClientPath); GlobalIndexes.Add(File.ClientPath, Globals.Num()); Globals.Add(MoveTemp(File));
        UE_LOG(LogTemp, Display, TEXT("Atelier EndCook: verified global file %d/%d"), Globals.Num(), GlobalSpecs->Num());
    }
    const int32* Development = GlobalIndexes.Find(TEXT("/{project}/Metadata/DevelopmentAssetRegistry.bin"));
    const int32* Runtime = GlobalIndexes.Find(TEXT("/{project}/AssetRegistry.bin"));
    const int32* Metadata = GlobalIndexes.Find(TEXT("/{project}/Metadata/") + UE::Cook::GetCookMetadataFilename());
    if (!Development || !Runtime || !Metadata) return Fail(TEXT("required_global_registry_or_metadata_missing"));
    FAssetRegistryState Registry;
    TArray<uint8> RegistryBytes;
    const FSharedBuffer DevelopmentBytes = Raw(Globals[*Development].Attachment);
    RegistryBytes.Append(static_cast<const uint8*>(DevelopmentBytes.GetData()), DevelopmentBytes.GetSize());
    FMemoryReader RegistryReader(RegistryBytes, true);
    FAssetRegistryLoadOptions Options; Options.ParallelWorkers = 3;
    if (!Registry.Load(RegistryReader, Options) || RegistryReader.IsError() || RegistryReader.Tell() != RegistryReader.TotalSize())
        return Fail(TEXT("development_registry_decode_failed"));
    TSet<FName> RegistryPackages;
    for (const auto& Pair : Registry.GetAssetPackageDataMap())
    {
        if (Pair.Key.ToString().StartsWith(TEXT("/Script/"))) continue;
        if (!ExpectedRoots.Contains(Pair.Key)) return Fail(TEXT("global_registry_contains_unchosen_package"));
        RegistryPackages.Add(Pair.Key);
    }
    if (RegistryPackages.Num() != ExpectedRoots.Num()) return Fail(TEXT("global_registry_omits_chosen_package"));
    FAssetRegistryState RuntimeRegistry;
    const FSharedBuffer RuntimeBytes = Raw(Globals[*Runtime].Attachment);
    TArray<uint8> RuntimeArray; RuntimeArray.Append(static_cast<const uint8*>(RuntimeBytes.GetData()), RuntimeBytes.GetSize());
    FMemoryReader RuntimeReader(RuntimeArray, true);
    if (!RuntimeRegistry.Load(RuntimeReader, Options) || RuntimeReader.IsError() || RuntimeReader.Tell() != RuntimeReader.TotalSize())
        return Fail(TEXT("runtime_registry_decode_failed"));
    TArray<FAssetData> RuntimeAssets; RuntimeRegistry.GetAllAssets(TSet<FName>(), RuntimeAssets, false);
    for (const FAssetData& Asset : RuntimeAssets) if (!ExpectedRoots.Contains(Asset.PackageName)) return Fail(TEXT("runtime_registry_contains_unchosen_package"));
    const FSharedBuffer MetadataBytes = Raw(Globals[*Metadata].Attachment);
    TArray<uint8> MetadataArray; MetadataArray.Append(static_cast<const uint8*>(MetadataBytes.GetData()), MetadataBytes.GetSize());
    FMemoryReader MetadataReader(MetadataArray, true);
    UE::Cook::FCookMetadataState CookMetadata;
    if (!CookMetadata.Serialize(MetadataReader) || MetadataReader.IsError() || MetadataReader.Tell() != MetadataReader.TotalSize()
        || !CookMetadata.IsValid() || CookMetadata.GetPlatform() != Oplog
        || CookMetadata.GetAssociatedDevelopmentAssetRegistryHash() != UE::Cook::FCookMetadataState::ComputeHashOfDevelopmentAssetRegistry(MakeMemoryView(RegistryBytes))
        || CookMetadata.GetAssociatedDevelopmentAssetRegistryHashPostWriteback() != 0) return Fail(TEXT("global_metadata_registry_linkage_failed"));
    TArray<FName> Names; ExpectedRoots.GetKeys(Names); Names.Sort(FNameLexicalLess());
    FString Referenced = TEXT("# Version 1");
    for (FName Name : Names) Referenced += FString(LINE_TERMINATOR) + Name.ToString().ToLower();
    const FTCHARToUTF8 ReferencedUTF8(*Referenced);
    const FSharedBuffer ReferencedRaw = FSharedBuffer::Clone(ReferencedUTF8.Get(), ReferencedUTF8.Length());
    const FCbAttachment ReferencedBytes(FCompressedBuffer::Compress(ReferencedRaw));
    const TConstArrayView<uint8> ReferencedView(static_cast<const uint8*>(ReferencedRaw.GetData()), ReferencedRaw.GetSize());
    const FString ReferencedSHA = SHA256Bytes(ReferencedView);
    // Zen's local ReferencedSet filter reads the stock file-backed descriptor. Keep its immutable
    // bytes with the durable namespace marker, never in the removable worker/job directory.
    const FString ReferencedFile = Marker + TEXT(".referencedset-") + ReferencedSHA + TEXT(".txt");
    if (!IFileManager::Get().FileExists(*ReferencedFile))
    {
        const TUniquePtr<FArchive> Writer(IFileManager::Get().CreateFileWriter(*ReferencedFile, FILEWRITE_NoReplaceExisting));
        if (!Writer) return Fail(TEXT("durable_referenced_set_not_fresh"));
        Writer->Serialize(const_cast<void*>(ReferencedRaw.GetData()), ReferencedRaw.GetSize());
        if (!Writer->Close() || Writer->IsError()) return Fail(TEXT("durable_referenced_set_write_failed"));
    }
    TArray<uint8> ReferencedReadback;
    if (!FFileHelper::LoadFileToArray(ReferencedReadback, *ReferencedFile) || SHA256Bytes(ReferencedReadback) != ReferencedSHA)
        return Fail(TEXT("durable_referenced_set_readback_failed"));
    FString ReferencedServerPath = ReferencedFile;
    if (!FPaths::MakePathRelativeTo(ReferencedServerPath, *FPaths::ConvertRelativePathToFull(FPaths::RootDir())))
        return Fail(TEXT("durable_referenced_set_server_path_failed"));
    const FIoChunkId ReferencedId = CreateExternalFileChunkId(ReferencedClient);
    FCbWriter ReferencedWriter; ReferencedWriter.BeginObject();
    ReferencedWriter << "key" << UE::Cook::GetReferencedSetOpName();
    ReferencedWriter.BeginArray("files"); ReferencedWriter.BeginObject();
    ReferencedWriter << "id" << ReferencedId << "clientpath" << ReferencedClient << "data" << FIoHash::Zero
        << "serverpath" << ReferencedServerPath;
    ReferencedWriter.EndObject(); ReferencedWriter.EndArray(); ReferencedWriter.EndObject();
    FCbPackage ReferencedPackage(ReferencedWriter.Save().AsObject()); ReferencedPackage.AddAttachment(ReferencedBytes);
    FPackageStoreOptimizer Optimizer; Optimizer.Initialize();
    const FIoBuffer Script = Optimizer.CreateScriptObjectsBuffer();
    int32 ScriptCount = 0;
    if (!ScriptObjectsValid(Script, ScriptCount)) return Fail(TEXT("native_script_objects_decode_failed"));
    const FCbAttachment ScriptBytes(FCompressedBuffer::Compress(FSharedBuffer::Clone(Script.GetData(), Script.DataSize())));
    const FIoChunkId ScriptId = CreateIoChunkId(0, 0, EIoChunkType::ScriptObjects);
    FCbWriter EndWriter; EndWriter.BeginObject(); EndWriter << "key" << "EndCook";
    EndWriter.BeginArray("files");
    for (const FNativeGlobalFile& File : Globals)
    {
        EndWriter.BeginObject(); EndWriter << "id" << File.Id << "clientpath" << File.ClientPath << "data" << File.Attachment;
        EndWriter.EndObject();
    }
    EndWriter.EndArray(); EndWriter.BeginArray("meta"); EndWriter.BeginObject();
    EndWriter << "id" << ScriptId << "name" << "ScriptObjects" << "data" << ScriptBytes;
    EndWriter.EndObject(); EndWriter.EndArray(); EndWriter.EndObject();
    FCbPackage EndPackage(EndWriter.Save().AsObject()); EndPackage.AddAttachment(ScriptBytes);
    for (const FNativeGlobalFile& File : Globals) EndPackage.AddAttachment(File.Attachment);
    if (!IFileManager::Get().MakeDirectory(*Output, true)
        || !SavePackageNoReplace(Output / TEXT("ReferencedSet.cb"), ReferencedPackage)
        || !SavePackageNoReplace(Output / TEXT("EndCook.cb"), EndPackage)
        || !FFileHelper::SaveStringToFile(Referenced, *(Output / UE::Cook::GetReferencedSetFilename()), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)
        || !FFileHelper::SaveStringToFile(RequestJson, *(Output / TEXT("namespace.pending.json")))) return Fail(TEXT("namespace_journal_write_failed"));
    if (!Client.TryCreateProject(Project, FStringView(), Oplog, FPaths::ConvertRelativePathToFull(FPaths::RootDir()),
            FPaths::ConvertRelativePathToFull(FPaths::EngineDir()), FPaths::GetPath(ProjectFile), ProjectFile)
        || !BindNamespace(Client, Project, Oplog, ProjectFile, Marker, Error)) return Fail(TEXT("namespace_changed_before_finalise"));
    if (!Client.AppendOp(ReferencedPackage).IsOk()) return Fail(TEXT("referenced_set_append_failed_namespace_uncertain"));
    if (!Client.EndBuildPass(EndPackage).IsOk()) return Fail(TEXT("endcook_append_failed_namespace_uncertain"));
    auto Roots = Client.GetOplogEntries(Project, Oplog, TArray<FString>{UE::Cook::GetReferencedSetOpName(), TEXT("EndCook")}).Get();
    if (Roots.Num() != 2 || !Roots[0].IsOk() || !Roots[1].IsOk()
        || Roots[0].ConsumeValueOrDie()["entry"].AsObject().GetHash() != ReferencedPackage.GetObjectHash()
        || Roots[1].ConsumeValueOrDie()["entry"].AsObject().GetHash() != EndPackage.GetObjectHash()) return Fail(TEXT("finalised_root_readback_failed_namespace_uncertain"));
    Chunks.Add(ReferencedId, ReferencedBytes.GetHash()); Chunks.Add(ScriptId, ScriptBytes.GetHash());
    FilePaths.Add(ReferencedId, ReferencedClient);
    for (const auto& Chunk : Chunks)
    {
        auto Bytes = Client.ReadChunk(Chunk.Key);
        if (!Bytes.IsOk() || FIoHash::HashBuffer(Bytes.ConsumeValueOrDie().GetView()) != Chunk.Value)
            return Fail(TEXT("finalised_chunk_readback_failed_namespace_uncertain"));
    }
    auto Active = Client.GetOplog(true).Get();
    if (!Active.IsOk()) return Fail(TEXT("referenced_package_roster_unavailable"));
    TSet<FName> ActiveNames;
    const FCbObject ActiveObject = Active.ConsumeValueOrDie();
    for (FCbFieldView Entry : ActiveObject["entries"].AsArrayView())
    {
        if (!Entry["packagestoreentry"].HasValue()) continue;
        const FString Name = FPackageStoreEntryResource::FromCbObject(Entry["packagestoreentry"].AsObjectView()).PackageName.ToString();
        const FString* Hash = ExpectedRoots.Find(FName(*Name));
        if (!Hash || ActiveNames.Contains(FName(*Name)) || LexToString(Entry.AsObjectView().GetHash()) != *Hash)
        {
            UE_LOG(LogTemp, Error, TEXT("Atelier EndCook active roster mismatch name=%s actual=%s expected=%s duplicate=%d"),
                *Name, *LexToString(Entry.AsObjectView().GetHash()), Hash ? **Hash : TEXT("unchosen"), ActiveNames.Contains(FName(*Name)));
            return Fail(TEXT("referenced_package_roster_differs"));
        }
        ActiveNames.Add(FName(*Name));
    }
    if (ActiveNames.Num() != ExpectedRoots.Num()) return Fail(TEXT("referenced_package_roster_incomplete"));
    auto Files = Client.GetFiles().Get();
    if (!Files.IsOk()) return Fail(TEXT("finalised_file_manifest_unavailable"));
    TSet<FIoChunkId> ActualFiles;
    const FCbObject FileObject = Files.ConsumeValueOrDie();
    for (FCbFieldView File : FileObject["files"].AsArrayView())
    {
        FIoChunkId Id;
        if (!LoadFromCompactBinary(File["id"], Id) || !FilePaths.Contains(Id) || ActualFiles.Contains(Id)
            || FString(File["clientpath"].AsString()) != FilePaths[Id])
        {
            UE_LOG(LogTemp, Error, TEXT("Atelier EndCook file mismatch id=%s actual=%s expected=%s duplicate=%d"),
                *LexToString(Id), *FString(File["clientpath"].AsString()),
                FilePaths.Contains(Id) ? *FilePaths[Id] : TEXT("unchosen"), ActualFiles.Contains(Id));
            return Fail(TEXT("finalised_file_manifest_differs"));
        }
        ActualFiles.Add(Id);
    }
    if (ActualFiles.Num() != FilePaths.Num()) return Fail(TEXT("finalised_file_manifest_incomplete"));
    for (const FNativeGlobalFile& File : Globals)
    {
        TArray<uint8> Current;
        if (!FFileHelper::LoadFileToArray(Current, *File.Path) || SHA256Bytes(Current) != File.SHA256)
            return Fail(TEXT("global_input_changed_during_finalise"));
    }
    const FTCHARToUTF8 RequestBytes(*RequestJson);
    Report->SetStringField(TEXT("request_io_hash"), LexToString(FIoHash::HashBuffer(MakeMemoryView(RequestBytes.Get(), RequestBytes.Length()))));
    Report->SetStringField(TEXT("project"), Project); Report->SetStringField(TEXT("oplog"), Oplog);
    Report->SetStringField(TEXT("input_key"), StringField(Request, TEXT("input_key")));
    Report->SetStringField(TEXT("referenced_set_root_hash"), LexToString(ReferencedPackage.GetObjectHash()));
    Report->SetStringField(TEXT("endcook_root_hash"), LexToString(EndPackage.GetObjectHash()));
    Report->SetStringField(TEXT("referenced_set_data_hash"), LexToString(ReferencedBytes.GetHash()));
    Report->SetStringField(TEXT("referenced_set_path"), ReferencedFile);
    Report->SetStringField(TEXT("referenced_set_sha256"), ReferencedSHA);
    Report->SetStringField(TEXT("script_objects_hash"), LexToString(ScriptBytes.GetHash()));
    Report->SetNumberField(TEXT("script_objects"), ScriptCount); Report->SetNumberField(TEXT("packages"), ExpectedRoots.Num());
    Report->SetNumberField(TEXT("chunks"), Chunks.Num()); Report->SetNumberField(TEXT("files"), FilePaths.Num());
    Report->SetStringField(TEXT("scope"), TEXT("zen_namespace"));
    Report->SetStringField(TEXT("source_dependency_evaluation"), TEXT("recorded_only"));
    Report->SetStringField(TEXT("status"), TEXT("finalized"));
    if (!FFileHelper::SaveStringToFile(Encode(Report), *(Output / TEXT("namespace.finalized.json"))))
    {
        Report->SetStringField(TEXT("status"), TEXT("refused"));
        return Fail(TEXT("namespace_receipt_write_failed_namespace_uncertain"));
    }
    return Encode(Report);
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Guid.h"
#include "Misc/Parse.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAtelierZenPackageRoundTrip,
    "Atelier.Build.ZenPackage.RoundTrip", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAtelierZenPackageRoundTrip::RunTest(const FString&)
{
    FString Fixture;
    if (!FParse::Value(FCommandLine::Get(), TEXT("AtelierZenFixture="), Fixture) || !Absolute(Fixture))
    {
        AddError(TEXT("An explicit retained native package fixture is required; no production acceptance implied"));
        return false;
    }
    FCbPackage Package;
    FIoHash RecordHash;
    if (!Load(Fixture, Package, RecordHash)) { AddError(TEXT("Invalid native fixture record")); return false; }
    const FString Name = FPackageStoreEntryResource::FromCbObject(NativeEntry(Package)["packagestoreentry"].AsObjectView()).PackageName.ToString();
    FString StoredKey, Error;
    if (!Validate(Package, Name, FString(), FString(), StoredKey, Error)) { AddError(Error); return false; }
    const FString Project = TEXT("AtelierV2_NativeTest_") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FString Oplog = TEXT("Mac");
    const FString Folder = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / Project);
    const FString Marker = Folder / TEXT("lifetime");
    IFileManager::Get().MakeDirectory(*Folder, true);
    if (!FFileHelper::SaveStringToFile(TEXT("Owned native Zen round-trip test; preserve evidence.\n"), *Marker)) return false;
    const FString ProjectFile = FPaths::ConvertRelativePathToFull(FPaths::GetProjectFilePath());
    UE::FZenStoreHttpClient Client;
    if (!Client.TryCreateProject(Project, FStringView(), Oplog,
            FPaths::ConvertRelativePathToFull(FPaths::RootDir()), FPaths::ConvertRelativePathToFull(FPaths::EngineDir()),
            FPaths::GetPath(ProjectFile), ProjectFile)
        || !Client.TryCreateOplog(Project, Oplog, Marker))
    { AddError(TEXT("Could not create this test's fresh owned native namespace")); return false; }
    const FObject Request = MakeShared<FJsonObject>();
    Request->SetNumberField(TEXT("version"), 1);
    for (const auto& Pair : TArray<TPair<FString, FString>>{
        {TEXT("mode"), TEXT("restore")}, {TEXT("project"), Project}, {TEXT("oplog"), Oplog},
        {TEXT("source_package"), Name}, {TEXT("expected_stored_key"), StoredKey},
        {TEXT("expected_root_hash"), LexToString(NativeEntry(Package).GetHash())}, {TEXT("record_path"), Fixture},
        {TEXT("project_file"), ProjectFile}, {TEXT("marker_path"), Marker},
        {TEXT("input_key"), FString::ChrN(64, '1')}, {TEXT("runtime_project_file"), ProjectFile}})
        Request->SetStringField(Pair.Key, Pair.Value);
    const FObject Results = MakeShared<FJsonObject>();
    auto Call = [&](const TCHAR* Label, const TCHAR* ExpectedStatus) -> FObject
    {
        FObject Response;
        const FString Text = UAtelierBuildWorkerLibrary::ZenPackageRequest(Encode(Request));
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Response) || !Response)
        { AddError(TEXT("Invalid native response")); return {}; }
        Results->SetObjectField(Label, Response);
        FFileHelper::SaveStringToFile(Encode(Results), *(Folder / TEXT("results.json")));
        FString Status;
        if (!Response->TryGetStringField(TEXT("status"), Status) || Status != ExpectedStatus)
        { AddError(FString(Label) + TEXT(": ") + Text); return {}; }
        return Response;
    };
    if (!Call(TEXT("restore"), TEXT("restored"))) return false;
    Request->SetStringField(TEXT("mode"), TEXT("capture"));
    Request->SetStringField(TEXT("record_path"), Folder / TEXT("capture.cb"));
    if (!Call(TEXT("capture"), TEXT("verified"))) return false;
    Request->SetStringField(TEXT("mode"), TEXT("verify"));
    if (!Call(TEXT("verify"), TEXT("verified"))) return false;
    Request->SetStringField(TEXT("expected_stored_key"), FString::ChrN(40, '0'));
    if (!Call(TEXT("wrong_key"), TEXT("refused"))) return false;
    Request->SetStringField(TEXT("expected_stored_key"), StoredKey);
    Request->SetStringField(TEXT("expected_root_hash"), FString::ChrN(40, '0'));
    if (!Call(TEXT("wrong_root"), TEXT("refused"))) return false;
    Request->SetStringField(TEXT("expected_root_hash"), LexToString(NativeEntry(Package).GetHash()));
    Request->SetStringField(TEXT("source_package"), Name + TEXT("_Wrong"));
    if (!Call(TEXT("wrong_package"), TEXT("refused"))) return false;
    Request->SetStringField(TEXT("source_package"), Name);
    Request->SetStringField(TEXT("project"), Project + TEXT("_Missing"));
    if (!Call(TEXT("unknown_namespace"), TEXT("refused"))) return false;
    Request->SetStringField(TEXT("project"), Project);
    TArray<uint8> Truncated;
    if (!FFileHelper::LoadFileToArray(Truncated, *Fixture) || Truncated.IsEmpty()) return false;
    Truncated.Pop();
    const FString BrokenPath = Folder / TEXT("truncated.cb");
    if (!FFileHelper::SaveArrayToFile(Truncated, *BrokenPath)) return false;
    Request->SetStringField(TEXT("record_path"), BrokenPath);
    if (!Call(TEXT("truncated"), TEXT("refused"))) return false;
    AddInfo(TEXT("Native restore/capture/verify and identity/truncation negatives passed; fixture-only hook proof at ") + Folder);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAtelierZenAuxiliaryRoundTrip,
    "Atelier.Build.ZenPackage.AuxiliaryRoundTrip", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAtelierZenAuxiliaryRoundTrip::RunTest(const FString&)
{
    FString Fixture;
    if (!FParse::Value(FCommandLine::Get(), TEXT("AtelierZenFixture="), Fixture) || !Absolute(Fixture))
    { AddError(TEXT("An explicit retained native package fixture is required")); return false; }
    FCbPackage Original;
    FIoHash RecordHash;
    if (!Load(Fixture, Original, RecordHash)) return false;
    const FCbObject OriginalEntry = NativeEntry(Original);
    const FString Name = FPackageStoreEntryResource::FromCbObject(OriginalEntry["packagestoreentry"].AsObjectView()).PackageName.ToString();
    FString StoredKey, Error;
    if (!Validate(Original, Name, FString(), FString(), StoredKey, Error)) { AddError(Error); return false; }
    const FString Project = TEXT("AtelierV2_AuxTest_") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FString Folder = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / Project);
    const FString Marker = Folder / TEXT("lifetime"), AuxiliaryPath = Folder / TEXT("auxiliary.bin");
    IFileManager::Get().MakeDirectory(*Folder, true);
    if (!FFileHelper::SaveStringToFile(TEXT("Owned native auxiliary round-trip test.\n"), *Marker)
        || !FFileHelper::SaveStringToFile(TEXT("Retained zero-hash native file bytes: ") + Project, *AuxiliaryPath)) return false;
    TArray<uint8> ExpectedBytes;
    if (!FFileHelper::LoadFileToArray(ExpectedBytes, *AuxiliaryPath)) return false;
    const FIoHash ExpectedHash = FIoHash::HashBuffer(MakeMemoryView(ExpectedBytes));
    const FString ProjectFile = FPaths::ConvertRelativePathToFull(FPaths::GetProjectFilePath());
    UE::FZenStoreHttpClient Client;
    if (!Client.TryCreateProject(Project, FStringView(), TEXT("Mac"),
            FPaths::ConvertRelativePathToFull(FPaths::RootDir()), FPaths::ConvertRelativePathToFull(FPaths::EngineDir()),
            FPaths::GetPath(ProjectFile), ProjectFile)
        || !Client.TryCreateOplog(Project, TEXT("Mac"), Marker)) return false;
    const FString ClientPath = TEXT("/{project}/Metadata/AtelierAuxiliary.bin");
    const FIoChunkId Id = CreateExternalFileChunkId(ClientPath);
    FString ServerPath = AuxiliaryPath;
    if (!FPaths::MakePathRelativeTo(ServerPath, *FPaths::ConvertRelativePathToFull(FPaths::RootDir()))) return false;
    FCbWriter EntryWriter;
    EntryWriter.BeginObject();
    for (FCbFieldView Field : OriginalEntry) if (Field.GetName() != "files") EntryWriter.AddField(Field.GetName(), Field);
    EntryWriter.BeginArray("files");
    EntryWriter.BeginObject();
    EntryWriter << "id" << Id;
    EntryWriter << "data" << FIoHash::Zero;
    EntryWriter << "serverpath" << ServerPath;
    EntryWriter << "clientpath" << ClientPath;
    EntryWriter.EndObject(); EntryWriter.EndArray(); EntryWriter.EndObject();
    const FCbObject SourceEntry = EntryWriter.Save().AsObject();
    FCbPackage Source(SourceEntry, SourceEntry.GetHash());
    for (const FCbAttachment& Attachment : Original.GetAttachments())
        Source.AddAttachment(FCbAttachment(FCompressedBuffer::Compress(Raw(Attachment))));
    if (!Client.AppendOp(MoveTemp(Source)).IsOk()) { AddError(TEXT("Could not append owned file-backed fixture")); return false; }
    auto Before = Client.ReadChunk(Id);
    if (!Before.IsOk() || FIoHash::HashBuffer(Before.ConsumeValueOrDie().GetView()) != ExpectedHash)
    { AddError(TEXT("Native source-file id does not read the owned fixture bytes")); return false; }
    const FObject Request = MakeShared<FJsonObject>();
    Request->SetNumberField(TEXT("version"), 1);
    const FString Capture = Folder / TEXT("capture.cb");
    for (const auto& Pair : TArray<TPair<FString, FString>>{
        {TEXT("mode"), TEXT("capture")}, {TEXT("project"), Project}, {TEXT("oplog"), TEXT("Mac")},
        {TEXT("source_package"), Name}, {TEXT("expected_stored_key"), StoredKey},
        {TEXT("expected_root_hash"), LexToString(SourceEntry.GetHash())}, {TEXT("record_path"), Capture},
        {TEXT("project_file"), ProjectFile}, {TEXT("marker_path"), Marker},
        {TEXT("input_key"), FString::ChrN(64, '1')}, {TEXT("runtime_project_file"), ProjectFile}})
        Request->SetStringField(Pair.Key, Pair.Value);
    const FObject Results = MakeShared<FJsonObject>();
    auto Call = [&](const TCHAR* Label, const TCHAR* ExpectedStatus) -> FObject
    {
        FObject Response;
        const FString Text = UAtelierBuildWorkerLibrary::ZenPackageRequest(Encode(Request));
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Response) || !Response) return {};
        Results->SetObjectField(Label, Response);
        FFileHelper::SaveStringToFile(Encode(Results), *(Folder / TEXT("results.json")));
        if (Response->GetStringField(TEXT("status")) != ExpectedStatus)
        { AddError(FString(Label) + TEXT(": ") + Text); return {}; }
        return Response;
    };
    const FObject CapturedReport = Call(TEXT("capture_file_backed"), TEXT("verified"));
    if (!CapturedReport || !CapturedReport->GetStringField(TEXT("installed_root_hash")).IsEmpty())
    { AddError(TEXT("Capture must not claim a remote installation")); return false; }
    FCbPackage Captured;
    if (!Load(Capture, Captured, RecordHash)) return false;
    TMap<FIoChunkId, FIoHash> Files;
    if (!Auxiliary(Captured, NativeEntry(Captured), Files, Error) || Files.Num() != 1 || Files.FindChecked(Id) != ExpectedHash)
    { AddError(TEXT("Retained native auxiliary binding differs")); return false; }
    Request->SetStringField(TEXT("mode"), TEXT("restore"));
    const FObject Restored = Call(TEXT("restore_retained"), TEXT("restored"));
    if (!Restored || Restored->GetStringField(TEXT("root_hash")) != LexToString(SourceEntry.GetHash())
        || Restored->GetStringField(TEXT("installed_root_hash")) == LexToString(SourceEntry.GetHash())) return false;
    // Change only this test's generated source file. Readback must still return the retained attachment.
    if (!FFileHelper::SaveStringToFile(TEXT("Changed after restore; must not be read"), *AuxiliaryPath)) return false;
    auto After = Client.ReadChunk(Id);
    if (!After.IsOk() || FIoHash::HashBuffer(After.ConsumeValueOrDie().GetView()) != ExpectedHash)
    { AddError(TEXT("Restored native id still depends on its old file-backed path")); return false; }
    Results->SetStringField(TEXT("readback_auxiliary_hash"), LexToString(ExpectedHash));
    Request->SetStringField(TEXT("mode"), TEXT("verify"));
    const FObject VerifiedReport = Call(TEXT("verify_retained"), TEXT("verified"));
    if (!VerifiedReport || !VerifiedReport->GetStringField(TEXT("installed_root_hash")).IsEmpty()
        || VerifiedReport->GetStringField(TEXT("source_dependency_evaluation")) != TEXT("recorded_only"))
    { AddError(TEXT("Record verification must not claim install or current dependency evaluation")); return false; }
    Captured.RemoveAttachment(ExpectedHash);
    FBufferArchive Broken;
    Captured.Save(Broken);
    const FString BrokenPath = Folder / TEXT("missing-auxiliary.cb");
    if (!FFileHelper::SaveArrayToFile(Broken, *BrokenPath)) return false;
    Request->SetStringField(TEXT("record_path"), BrokenPath);
    if (!Call(TEXT("missing_auxiliary"), TEXT("refused"))) return false;
    AddInfo(TEXT("Native zero-hash auxiliary capture/replay and missing-byte refusal passed at ") + Folder);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAtelierZenEndCookRoundTrip,
    "Atelier.Build.ZenPackage.EndCookRoundTrip", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAtelierZenEndCookRoundTrip::RunTest(const FString&)
{
    FString FixtureA, FixtureB, GlobalsRequest;
    if (!FParse::Value(FCommandLine::Get(), TEXT("AtelierZenFixtureA="), FixtureA)
        || !FParse::Value(FCommandLine::Get(), TEXT("AtelierZenFixtureB="), FixtureB)
        || !FParse::Value(FCommandLine::Get(), TEXT("AtelierZenGlobals="), GlobalsRequest))
    { AddError(TEXT("Explicit retained package and native global fixture inputs required")); return false; }
    FCbPackage A, B; FIoHash Hash;
    if (!Load(FixtureA, A, Hash) || !Load(FixtureB, B, Hash)) return false;
    const FString NameA = FPackageStoreEntryResource::FromCbObject(NativeEntry(A)["packagestoreentry"].AsObjectView()).PackageName.ToString();
    const FString NameB = FPackageStoreEntryResource::FromCbObject(NativeEntry(B)["packagestoreentry"].AsObjectView()).PackageName.ToString();
    FString KeyA, KeyB, Error;
    if (NameA == NameB || !Validate(A, NameA, FString(), FString(), KeyA, Error)
        || !Validate(B, NameB, FString(), FString(), KeyB, Error)) return false;
    const FString Project = TEXT("AtelierV2_EndCookTest_") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FString Folder = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / Project);
    const FString Marker = Folder / TEXT("lifetime");
    IFileManager::Get().MakeDirectory(*Folder, true);
    if (!FFileHelper::SaveStringToFile(TEXT("Owned EndCook namespace proof; preserve evidence"), *Marker)) return false;
    const FString ProjectFile = FPaths::ConvertRelativePathToFull(FPaths::GetProjectFilePath());
    UE::FZenStoreHttpClient Client;
    if (!Client.TryCreateProject(Project, FStringView(), TEXT("Mac"), FPaths::ConvertRelativePathToFull(FPaths::RootDir()),
            FPaths::ConvertRelativePathToFull(FPaths::EngineDir()), FPaths::GetPath(ProjectFile), ProjectFile)
        || !Client.TryCreateOplog(Project, TEXT("Mac"), Marker)) return false;
    const FObject Results = MakeShared<FJsonObject>();
    auto Keep = [&](const TCHAR* Label, const FString& Text, const TCHAR* Status) -> FObject
    {
        FObject Response;
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Response) || !Response) return {};
        Results->SetObjectField(Label, Response);
        FFileHelper::SaveStringToFile(Encode(Results), *(Folder / TEXT("results.json")));
        if (Response->GetStringField(TEXT("status")) != Status)
        { AddError(FString(Label) + TEXT(": ") + Text); return {}; }
        return Response;
    };
    FObject AResult;
    for (int32 Index = 0; Index < 2; ++Index)
    {
        const FObject Request = MakeShared<FJsonObject>(); Request->SetNumberField(TEXT("version"), 1);
        for (const auto& Pair : TArray<TPair<FString, FString>>{
            {TEXT("mode"), TEXT("restore")}, {TEXT("project"), Project}, {TEXT("oplog"), TEXT("Mac")},
            {TEXT("source_package"), Index == 0 ? NameA : NameB}, {TEXT("expected_stored_key"), Index == 0 ? KeyA : KeyB},
            {TEXT("expected_root_hash"), LexToString(NativeEntry(Index == 0 ? A : B).GetHash())},
            {TEXT("record_path"), Index == 0 ? FixtureA : FixtureB}, {TEXT("project_file"), ProjectFile},
            {TEXT("marker_path"), Marker}, {TEXT("input_key"), FString::ChrN(64, '1')}, {TEXT("runtime_project_file"), ProjectFile}})
            Request->SetStringField(Pair.Key, Pair.Value);
        const FObject Response = Keep(Index == 0 ? TEXT("restore_chosen") : TEXT("restore_stale"),
            UAtelierBuildWorkerLibrary::ZenPackageRequest(Encode(Request)), TEXT("restored"));
        if (!Response) return false;
        if (Index == 0) AResult = Response;
    }
    FString GlobalsText;
    if (!FFileHelper::LoadFileToString(GlobalsText, *GlobalsRequest)) return false;
    const FObject Composed = Keep(TEXT("compose_chosen_globals"), UAtelierBuildWorkerLibrary::ZenFinaliseRequest(GlobalsText), TEXT("composed"));
    if (!Composed) return false;
    FObject GlobalInput;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(GlobalsText), GlobalInput)) return false;
    const FString GlobalRoot = GlobalInput->GetStringField(TEXT("output_dir"));
    const FObject Request = MakeShared<FJsonObject>(); Request->SetNumberField(TEXT("version"), 1);
    for (const auto& Pair : TArray<TPair<FString, FString>>{
        {TEXT("project"), Project}, {TEXT("oplog"), TEXT("Mac")}, {TEXT("project_file"), ProjectFile},
        {TEXT("marker_path"), Marker}, {TEXT("runtime_project_file"), ProjectFile},
        {TEXT("input_key"), FString::ChrN(64, '1')}, {TEXT("output_dir"), Folder / TEXT("finalized")}})
        Request->SetStringField(Pair.Key, Pair.Value);
    const FObject Package = MakeShared<FJsonObject>(); Package->SetStringField(TEXT("name"), NameA);
    Package->SetStringField(TEXT("installed_root_hash"), AResult->GetStringField(TEXT("installed_root_hash")));
    Request->SetArrayField(TEXT("packages"), TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueObject>(Package)});
    TArray<TSharedPtr<FJsonValue>> Globals;
    for (const auto& Value : Composed->GetArrayField(TEXT("files")))
    {
        const FObject File = Value->AsObject(), Spec = MakeShared<FJsonObject>();
        const FString Relative = File->GetStringField(TEXT("path"));
        Spec->SetStringField(TEXT("clientpath"), TEXT("/{project}/") + Relative);
        Spec->SetStringField(TEXT("path"), GlobalRoot / Relative);
        Spec->SetStringField(TEXT("sha256"), File->GetStringField(TEXT("sha256")));
        Globals.Add(MakeShared<FJsonValueObject>(Spec));
    }
    Request->SetArrayField(TEXT("globals"), Globals);
    Request->SetArrayField(TEXT("source_files"), TArray<TSharedPtr<FJsonValue>>());
    // A declared-hash mismatch must refuse before either namespace root is published.
    const FString Saved = Globals[0]->AsObject()->GetStringField(TEXT("sha256"));
    Globals[0]->AsObject()->SetStringField(TEXT("sha256"), FString::ChrN(64, '0'));
    if (!Keep(TEXT("wrong_global_hash"), UAtelierBuildWorkerLibrary::ZenEndCookRequest(Encode(Request)), TEXT("refused"))) return false;
    Globals[0]->AsObject()->SetStringField(TEXT("sha256"), Saved);
    if (!Keep(TEXT("finalize_chosen"), UAtelierBuildWorkerLibrary::ZenEndCookRequest(Encode(Request)), TEXT("finalized"))) return false;
    auto Raw = Client.GetOplog(false).Get();
    if (!Raw.IsOk()) return false;
    bool StaleKept = false;
    const FCbObject RawObject = Raw.ConsumeValueOrDie();
    for (FCbFieldView Entry : RawObject["entries"].AsArrayView())
        if (Entry["packagestoreentry"].HasValue()
            && FPackageStoreEntryResource::FromCbObject(Entry["packagestoreentry"].AsObjectView()).PackageName.ToString() == NameB) StaleKept = true;
    if (!StaleKept) { AddError(TEXT("Finalise deleted the unselected retained package instead of trimming its reference")); return false; }
    Results->SetBoolField(TEXT("unselected_raw_package_preserved"), true);
    FFileHelper::SaveStringToFile(Encode(Results), *(Folder / TEXT("results.json")));
    AddInfo(TEXT("Exact referenced package roster, all native chunks/globals and stale-package preservation verified at ") + Folder);
    return true;
}

#endif
