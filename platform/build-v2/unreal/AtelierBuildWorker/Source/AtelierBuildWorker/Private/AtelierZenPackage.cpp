#include "AtelierBuildWorkerLibrary.h"
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

#endif
