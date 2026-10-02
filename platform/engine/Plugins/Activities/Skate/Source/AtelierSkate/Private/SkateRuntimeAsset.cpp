// SPDX-License-Identifier: Apache-2.0
#include "SkateRuntimeAsset.h"

#include "Native/GameplayRuntime.h"
#include "Native/CameraSettings.h"
#include "Async/Async.h"
#include <cfenv>
#include <cstring>
#if WITH_EDITOR
#include "Native/GameplaySession.h"
#include "UObject/UObjectGlobals.h"
#endif
#include "Containers/StringConv.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#if WITH_EDITOR
#include "Serialization/JsonWriter.h"
#endif

namespace
{
class FScopedResourceFloatEnvironment
{
public:
    FScopedResourceFloatEnvironment()
    {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
        bSaved=std::fegetenv(&Saved)==0;
        bReady=bSaved && std::fesetenv(FE_DFL_ENV)==0;
    }
    ~FScopedResourceFloatEnvironment()
    {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
        if(bSaved)std::fesetenv(&Saved);
    }
    FScopedResourceFloatEnvironment(const FScopedResourceFloatEnvironment&)=delete;
    FScopedResourceFloatEnvironment& operator=(const FScopedResourceFloatEnvironment&)=delete;
    bool IsReady() const {return bReady;}
private:
    std::fenv_t Saved{};
    bool bSaved=false,bReady=false;
};
// SHA-256 uses unsigned integer words only. Core's generic platform SHA-256
// entry point is not implemented on every target supported by this plugin.
uint32 RotateRight(uint32 Value,uint32 Amount)
{return (Value>>Amount)|(Value<<(32-Amount));}

void HashBlock(const uint8* Block,uint32* State)
{
    static constexpr uint32 K[64]={
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32 W[64];
    for(uint32 I=0;I<16;++I)
        W[I]=(uint32(Block[I*4])<<24)|(uint32(Block[I*4+1])<<16)
            |(uint32(Block[I*4+2])<<8)|uint32(Block[I*4+3]);
    for(uint32 I=16;I<64;++I)
    {
        const uint32 S0=RotateRight(W[I-15],7)^RotateRight(W[I-15],18)^(W[I-15]>>3);
        const uint32 S1=RotateRight(W[I-2],17)^RotateRight(W[I-2],19)^(W[I-2]>>10);
        W[I]=W[I-16]+S0+W[I-7]+S1;
    }
    uint32 A=State[0],B=State[1],C=State[2],D=State[3];
    uint32 E=State[4],F=State[5],G=State[6],H=State[7];
    for(uint32 I=0;I<64;++I)
    {
        const uint32 S1=RotateRight(E,6)^RotateRight(E,11)^RotateRight(E,25);
        const uint32 T1=H+S1+((E&F)^((~E)&G))+K[I]+W[I];
        const uint32 S0=RotateRight(A,2)^RotateRight(A,13)^RotateRight(A,22);
        const uint32 T2=S0+((A&B)^(A&C)^(B&C));
        H=G;G=F;F=E;E=D+T1;D=C;C=B;B=A;A=T1+T2;
    }
    State[0]+=A;State[1]+=B;State[2]+=C;State[3]+=D;
    State[4]+=E;State[5]+=F;State[6]+=G;State[7]+=H;
}

// A view of owned bytes, with no per-record transport allocation or UObject
// access. The same integer implementation serves the editor and native worker.
std::string HashByteView(const std::uint8_t* Bytes,std::size_t Count)
{
    uint32 State[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    std::size_t Offset=0;
    while(Count-Offset>=64){HashBlock(Bytes+Offset,State);Offset+=64;}
    uint8 Tail[128]={};
    const std::size_t Remaining=Count-Offset;
    if(Remaining)std::memcpy(Tail,Bytes+Offset,Remaining);
    Tail[Remaining]=0x80;
    const std::size_t Size=Remaining<56?64:128;
    const uint64 Bits=static_cast<uint64>(Count)*8;
    for(std::size_t I=0;I<8;++I)Tail[Size-1-I]=static_cast<uint8>(Bits>>(I*8));
    HashBlock(Tail,State);if(Size==128)HashBlock(Tail+64,State);
    static constexpr char Hex[]="0123456789abcdef";
    std::string Result(64,'0');
    for(std::size_t Word=0;Word<8;++Word)
        for(std::size_t Digit=0;Digit<8;++Digit)
            Result[Word*8+Digit]=Hex[(State[Word]>>(28-Digit*4))&15];
    return Result;
}

bool VerifySnapshotIntegrity(const atelier::skate::GameplayResourceSnapshot& Source,std::string& Error)
{
    std::string Issues;
    auto Add=[&Issues](std::string Issue)
    {if(!Issues.empty())Issues+='\n';Issues+=std::move(Issue);};
    const auto& Manifest=Source.Manifest();
    if(HashByteView(Manifest.data(),Manifest.size())!=Source.ManifestSha256())
        Add("Source manifest SHA-256 mismatch");
    // Accumulate every independent byte mismatch before returning. No bank is
    // parsed unless the entire immutable transport passes these checks.
    for(const auto& Record:Source.Records())
        if(HashByteView(Record.bytes.data(),Record.bytes.size())!=Record.sha256)
            Add("Payload SHA-256 mismatch: "+Record.name);
    Error=std::move(Issues);return Error.empty();
}

std::vector<std::uint8_t> NativeBytes(const TArray<uint8>& Bytes)
{
    std::vector<std::uint8_t> Result;
    if(!Bytes.IsEmpty())Result.assign(Bytes.GetData(),Bytes.GetData()+Bytes.Num());
    return Result;
}

std::string NativeString(const FString& Value)
{const FTCHARToUTF8 Text(*Value,Value.Len());return std::string(Text.Get(),Text.Length());}

std::shared_ptr<const atelier::skate::GameplayResourceSnapshot> CopySnapshot(const USkateRuntimeAsset& Asset)
{
    std::vector<atelier::skate::GameplayResourceRecord> Records;
    Records.reserve(Asset.Records.Num());
    for(const auto& Record:Asset.Records)
        Records.push_back({NativeString(Record.RelativePath),NativeString(Record.Sha256),NativeBytes(Record.Payload)});
    return std::make_shared<const atelier::skate::GameplayResourceSnapshot>(std::move(Records),
        NativeBytes(Asset.ManifestBytes),NativeString(Asset.ManifestSha256),NativeString(Asset.SourceIdentity),
        VerifySnapshotIntegrity);
}

bool ManifestJson(const TArray<uint8>& Bytes,TSharedPtr<FJsonObject>& Object,TArray<FString>& Issues)
{
    if(Bytes.IsEmpty()){Issues.Add(TEXT("Source manifest is empty"));return false;}
    // The native package manifest is ASCII JSON (Unicode is escaped by its
    // authoring tool). Reject lossy UTF-8 conversion and embedded NUL bytes.
    for(uint8 Byte:Bytes)if(Byte==0 || Byte>127)
    {Issues.Add(TEXT("Source manifest must contain ASCII JSON without NUL bytes"));return false;}
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Bytes.GetData()),Bytes.Num());
    const FString Json(Text.Length(),Text.Get());
    auto Reader=TJsonReaderFactory<>::Create(Json);
    struct FScope {bool bObject=false;TSet<FString> Keys;};
    TArray<FScope> Scopes;
    EJsonNotation Notation;
    while(Reader->ReadNext(Notation))
    {
        const bool bEnd=Notation==EJsonNotation::ObjectEnd || Notation==EJsonNotation::ArrayEnd;
        if(!bEnd && !Scopes.IsEmpty() && Scopes.Last().bObject)
        {
            const FString Key=Reader->GetIdentifier();
            if(Scopes.Last().Keys.Contains(Key))Issues.Add(TEXT("Duplicate source manifest key: ")+Key);
            Scopes.Last().Keys.Add(Key);
        }
        if(Notation==EJsonNotation::ObjectStart || Notation==EJsonNotation::ArrayStart)
        {FScope Scope;Scope.bObject=Notation==EJsonNotation::ObjectStart;Scopes.Add(MoveTemp(Scope));}
        else if(bEnd && !Scopes.IsEmpty())Scopes.Pop();
    }
    if(!Reader->GetErrorMessage().IsEmpty())
    {Issues.Add(TEXT("Invalid source manifest JSON: ")+Reader->GetErrorMessage());return false;}
    Reader=TJsonReaderFactory<>::Create(Json);
    if(!FJsonSerializer::Deserialize(Reader,Object) || !Object.IsValid())
    {Issues.Add(TEXT("Source manifest must be a JSON object"));return false;}
    return true;
}

bool IntegerField(const FJsonObject& Object,const TCHAR* Name,int64& Value,TArray<FString>& Issues)
{
    double Number=0;
    if(!Object.TryGetNumberField(Name,Number) || !FMath::IsFinite(Number) || Number<0
        || Number>9007199254740991.0 || Number!=FMath::FloorToDouble(Number))
    {Issues.Add(FString::Printf(TEXT("Invalid nonnegative source manifest integer: %s"),Name));return false;}
    Value=static_cast<int64>(Number);return true;
}

void CheckDecoded(const atelier::skate::GameplayResourceSnapshot& Source,FSkateRuntimeAssetValidationReport& Report)
{
    using namespace atelier::skate;
    std::string Error;
    int64 Frames=0;
    int32 MetadataBanks=0,Patterns=0;
    AnimationMetadata Bank0;
    bool bBank0=false;
    // Decode every independent member, even after a previous member fails.
    for(const auto& Record:Source.Records())
    {
        const auto& Bytes=Record.bytes;
        const auto& Name=Record.name;
        bool bOkay=true;
        Error.clear();
        if(Name=="settings.skate") {SettingsDatabase Data;bOkay=Data.Load(Bytes,Error);}
        else if(Name=="metadata/bank-0.skate" || Name=="metadata/bank-1.skate")
        {
            AnimationMetadata Data;bOkay=Data.Load(Bytes,Error);
            if(bOkay){++MetadataBanks;if(Name=="metadata/bank-0.skate"){Bank0=std::move(Data);bBank0=true;}}
        }
        else if(Name=="animation/rig.skate") {AnimationRig Data;bOkay=Data.Load(Bytes,Error);}
        else if(Name.compare(0,16,"animation/clips/")==0)
        {AnimationClipSamples Data;bOkay=Data.Load(Bytes,Error);if(bOkay)Frames+=Data.frame_count;}
        else if(Name=="action.graph" || Name=="motion.graph" || Name=="camera.graph")
        {Graph Data;bOkay=Data.Load(Bytes,Error);}
        else if(Name=="camera.skate") {camera::CameraData Data;bOkay=Data.Load(Bytes,Error);}
        else if(Name=="gestures.skate")
        {
            std::vector<GestureSet> Data;bOkay=LoadGestureData(Bytes,Data,Error);
            if(bOkay)for(const auto& Set:Data)Patterns+=static_cast<int32>(Set.patterns.size());
        }
        else if(Name=="physics-skeletons.skate")
        {PhysicsSkeletons Data;bOkay=Data.Load(Bytes,Source.SourceIdentity(),Error);}
        else if(Name=="custom/climbing.skate") {ClimbingClipFile Data;bOkay=ReadClimbingClipFile(Bytes,Data,Error);}
        else if(Name=="custom/crouch-treflip.json")
        {AuthoredAnimationDocument Data;bOkay=ParseAuthoredAnimationDocument(std::string(Bytes.begin(),Bytes.end()),Data,Error);}
        else
        {bOkay=false;Error="Unknown native resource path";}
        if(!bOkay)Report.Issues.Add(FString(UTF8_TO_TCHAR(Name.c_str()))+TEXT(": ")+UTF8_TO_TCHAR(Error.c_str()));
    }
    if(bBank0)
    {
        if(Bank0.source_sha256!=Source.SourceIdentity())
            Report.Issues.Add(TEXT("Metadata bank-0 source identity differs from the source manifest"));
    }
    TSharedPtr<FJsonObject> Manifest;
    TArray<FString> JsonIssues;
    TArray<uint8> ManifestBytes;
    ManifestBytes.Append(Source.Manifest().data(),static_cast<int32>(Source.Manifest().size()));
    if(ManifestJson(ManifestBytes,Manifest,JsonIssues))
    {
        for(const auto& Measurement:TArray<TPair<FString,int64>>{
            {TEXT("animation_frames"),Frames},{TEXT("metadata_banks"),MetadataBanks},{TEXT("patterns"),Patterns}})
        {
            int64 Expected=0;
            if(IntegerField(*Manifest,*Measurement.Key,Expected,Report.Issues) && Expected!=Measurement.Value)
                Report.Issues.Add(TEXT("Decoded resource count differs from source manifest: ")+Measurement.Key);
        }
    }
    std::shared_ptr<const GameplayResources> Resources;
    Report.bSemanticLoadSucceeded=LoadGameplayResources(Source,Resources,Error);
    Report.bSnapshotIntegrityVerified=Report.bSemanticLoadSucceeded;
    if(!Report.bSemanticLoadSucceeded)
        Report.Issues.Add(TEXT("Native resource loader: ")+FString(UTF8_TO_TCHAR(Error.c_str())));
}
}

FString USkateRuntimeAsset::HashPayload(const TArray<uint8>& Bytes)
{
    const auto Hash=HashByteView(Bytes.GetData(),static_cast<std::size_t>(Bytes.Num()));
    return FString(UTF8_TO_TCHAR(Hash.c_str()));
}

bool USkateRuntimeAsset::IsValidRelativePath(const FString& Path)
{return atelier::skate::IsGameplayResourcePath(NativeString(Path));}

bool USkateRuntimeAsset::IsSha256(const FString& Value)
{
    if(Value.Len()!=64)return false;
    for(TCHAR Char:Value)if(!((Char>='0' && Char<='9') || (Char>='a' && Char<='f')))return false;
    return true;
}

FSkateRuntimeAssetValidationReport USkateRuntimeAsset::Validate(bool bCheckDecodedPayloads) const
{return ValidateInternal(bCheckDecodedPayloads);}

FSkateRuntimeAssetValidationReport USkateRuntimeAsset::ValidateInternal(bool bCheckDecodedPayloads,
    bool bCheckPayloadHashes) const
{
    FSkateRuntimeAssetValidationReport Report;
    if(!IsInGameThread()){Report.Issues.Add(TEXT("Runtime asset validation requires the game thread"));return Report;}
    Report.AssetPath=GetPathName();Report.ManifestSha256=ManifestSha256;Report.SourceIdentity=SourceIdentity;
    Report.RecordCount=Records.Num();
    if(Version!=1)Report.Issues.Add(TEXT("Unsupported runtime asset version"));
    if(ExpectedRecordCount<=0 || Records.Num()!=ExpectedRecordCount)
        Report.Issues.Add(TEXT("Runtime asset record count differs from the expected package count"));
    if(!IsSha256(ManifestSha256) || (bCheckPayloadHashes && HashPayload(ManifestBytes)!=ManifestSha256))
        Report.Issues.Add(TEXT("Source manifest SHA-256 mismatch"));
    if(!IsSha256(SourceIdentity))Report.Issues.Add(TEXT("Invalid source identity SHA-256"));
    TSet<FString> Names,FoldedNames;
    FString Previous;
    for(const auto& Record:Records)
    {
        const auto& Path=Record.RelativePath;
        if(!IsValidRelativePath(Path))Report.Issues.Add(TEXT("Unsafe native resource path: ")+Path);
        if(Names.Contains(Path))Report.Issues.Add(TEXT("Duplicate native resource path: ")+Path);
        if(FoldedNames.Contains(Path.ToLower()))Report.Issues.Add(TEXT("Case-colliding native resource path: ")+Path);
        if(!Previous.IsEmpty() && Previous.Compare(Path,ESearchCase::CaseSensitive)>=0)
            Report.Issues.Add(TEXT("Native resource records are not strictly ordered: ")+Path);
        Names.Add(Path);FoldedNames.Add(Path.ToLower());Previous=Path;
        Report.PayloadBytes+=Record.Payload.Num();
        if(Path.StartsWith(TEXT("animation/clips/"),ESearchCase::CaseSensitive)
            && Path.EndsWith(TEXT(".skate"),ESearchCase::CaseSensitive))++Report.ClipCount;
        if(!IsSha256(Record.Sha256) || (bCheckPayloadHashes && HashPayload(Record.Payload)!=Record.Sha256))
            Report.Issues.Add(TEXT("Payload SHA-256 mismatch: ")+Path);
    }
    static const TCHAR* Required[]={TEXT("settings.skate"),TEXT("metadata/bank-0.skate"),
        TEXT("metadata/bank-1.skate"),TEXT("physics-skeletons.skate"),TEXT("animation/rig.skate"),
        TEXT("action.graph"),TEXT("motion.graph"),TEXT("camera.graph"),TEXT("camera.skate"),TEXT("gestures.skate")};
    for(const TCHAR* Name:Required)
        if(!Records.ContainsByPredicate([Name](const auto& Record)
            {return Record.RelativePath.Equals(Name,ESearchCase::CaseSensitive);}))
            Report.Issues.Add(TEXT("Missing native resource: ")+FString(Name));
    if(Report.ClipCount==0)Report.Issues.Add(TEXT("Runtime asset contains no animation clips"));
    TSharedPtr<FJsonObject> Manifest;
    if(ManifestJson(ManifestBytes,Manifest,Report.Issues))
    {
        int64 ManifestVersion=0,ManifestBytesCount=0,ManifestClips=0;
        if(IntegerField(*Manifest,TEXT("version"),ManifestVersion,Report.Issues) && ManifestVersion!=1)
            Report.Issues.Add(TEXT("Unsupported source manifest version"));
        if(IntegerField(*Manifest,TEXT("bytes"),ManifestBytesCount,Report.Issues) && ManifestBytesCount!=Report.PayloadBytes)
            Report.Issues.Add(TEXT("Native payload byte count differs from source manifest"));
        if(IntegerField(*Manifest,TEXT("clips"),ManifestClips,Report.Issues) && ManifestClips!=Report.ClipCount)
            Report.Issues.Add(TEXT("Native clip count differs from source manifest"));
        FString Identity;
        if(!Manifest->TryGetStringField(TEXT("source_identity"),Identity) || Identity!=SourceIdentity)
            Report.Issues.Add(TEXT("Runtime asset source identity differs from source manifest"));
        const TSharedPtr<FJsonObject>* Files=nullptr;
        if(!Manifest->TryGetObjectField(TEXT("files"),Files))Report.Issues.Add(TEXT("Source manifest has no files object"));
        else
        {
            if((*Files)->Values.Num()!=Records.Num())Report.Issues.Add(TEXT("Manifest file count differs from serialized record count"));
            for(const auto& Pair:(*Files)->Values)
            {
                const FString Path=FString::ConstructFromPtrSize(*Pair.Key,Pair.Key.Len());
                if(!IsValidRelativePath(Path) || !Names.Contains(Path))
                    Report.Issues.Add(TEXT("Manifest path is unsafe or missing from the asset: ")+Path);
            }
            for(const auto& Record:Records)
            {
                const TSharedPtr<FJsonValue> Spec=(*Files)->TryGetField(Record.RelativePath);
                const TSharedPtr<FJsonObject> Object=Spec.IsValid() && Spec->Type==EJson::Object?Spec->AsObject():nullptr;
                if(!Object.IsValid()){Report.Issues.Add(TEXT("Missing manifest record: ")+Record.RelativePath);continue;}
                FString Hash;int64 ByteCount=0;
                if(!Object->TryGetStringField(TEXT("sha256"),Hash) || Hash!=Record.Sha256)
                    Report.Issues.Add(TEXT("Manifest SHA-256 differs from serialized record: ")+Record.RelativePath);
                if(IntegerField(*Object,TEXT("bytes"),ByteCount,Report.Issues) && ByteCount!=Record.Payload.Num())
                    Report.Issues.Add(TEXT("Manifest byte count differs from serialized record: ")+Record.RelativePath);
            }
        }
    }
    if(bCheckDecodedPayloads)
    {
        // Capture all UObject state here. Native decoding and constructors need
        // the same large stack and default floating-point environment as play.
        const auto Source=CopySnapshot(*this);
        Report=AsyncThread([Source,Report=MoveTemp(Report)]() mutable
        {
            FScopedResourceFloatEnvironment FloatEnvironment;
            if(!FloatEnvironment.IsReady())Report.Issues.Add(TEXT("Native resource floating-point environment setup failed"));
            else CheckDecoded(*Source,Report);
            return Report;
        },32*1024*1024).Get();
    }
    Report.bValid=Report.Issues.IsEmpty();
    return Report;
}

bool USkateRuntimeAsset::CreateSnapshot(std::shared_ptr<const atelier::skate::GameplayResourceSource>& Output,
    FString& Error) const
{
    const auto Report=ValidateInternal(false,false);
    if(!Report.bValid){Error=FString::Join(Report.Issues,TEXT("\n"));return false;}
    Output=CopySnapshot(*this);Error.Reset();return true;
}

#if WITH_EDITOR
namespace
{
void IntegrityCheck(FSkateRuntimeAssetValidationReport& Report,bool bPassed,const TCHAR* Name)
{
    ++Report.IntegrityChecks;
    if(bPassed)++Report.IntegrityChecksPassed;
    else Report.Issues.Add(FString(TEXT("Snapshot integrity check failed: "))+Name);
}

struct FIntegrityFixtures
{
    std::shared_ptr<const atelier::skate::GameplayResourceSnapshot> Captured,Payload,Manifest,Combined;
    bool bAuthoringMutated=false,bMalformedOutputRetained=false;
};

// A few dozen dummy bytes exercise capture and integrity without decoding a
// second animation bank or copying the production bundle for each negative case.
FIntegrityFixtures PrepareIntegrityFixtures(FSkateRuntimeAssetValidationReport& Report)
{
    using namespace atelier::skate;
    FIntegrityFixtures Fixtures;
    USkateRuntimeAsset* Asset=NewObject<USkateRuntimeAsset>(GetTransientPackage());
    Asset->SourceIdentity=FString::ChrN(64,TEXT('a'));
    TArray<FString> Paths={TEXT("action.graph"),TEXT("animation/clips/0/fixture.skate"),TEXT("animation/rig.skate"),
        TEXT("camera.graph"),TEXT("camera.skate"),TEXT("gestures.skate"),TEXT("metadata/bank-0.skate"),
        TEXT("metadata/bank-1.skate"),TEXT("motion.graph"),TEXT("physics-skeletons.skate"),TEXT("settings.skate")};
    Paths.Sort();Asset->ExpectedRecordCount=Paths.Num();
    auto Files=MakeShared<FJsonObject>();
    for(const FString& Path:Paths)
    {
        auto& Record=Asset->Records.AddDefaulted_GetRef();
        Record.RelativePath=Path;Record.Payload={uint8('a'),uint8('b'),uint8('c')};
        Record.Sha256=USkateRuntimeAsset::HashPayload(Record.Payload);
        auto Spec=MakeShared<FJsonObject>();
        Spec->SetStringField(TEXT("sha256"),Record.Sha256);Spec->SetNumberField(TEXT("bytes"),Record.Payload.Num());
        Files->SetObjectField(Path,Spec);
    }
    auto Manifest=MakeShared<FJsonObject>();
    Manifest->SetNumberField(TEXT("version"),1);Manifest->SetNumberField(TEXT("bytes"),Asset->Records.Num()*3);
    Manifest->SetNumberField(TEXT("clips"),1);Manifest->SetStringField(TEXT("source_identity"),Asset->SourceIdentity);
    Manifest->SetObjectField(TEXT("files"),Files);
    FString Json;auto Writer=TJsonWriterFactory<>::Create(&Json);FJsonSerializer::Serialize(Manifest,Writer);
    const FTCHARToUTF8 Text(*Json,Json.Len());
    Asset->ManifestBytes.Append(reinterpret_cast<const uint8*>(Text.Get()),Text.Length());
    Asset->ManifestSha256=USkateRuntimeAsset::HashPayload(Asset->ManifestBytes);
    auto Capture=[Asset,&Report](const TCHAR* Name)
    {
        std::shared_ptr<const GameplayResourceSource> Source;FString Error;
        const bool bOkay=Asset->CreateSnapshot(Source,Error);
        IntegrityCheck(Report,bOkay && Source!=nullptr,Name);
        // This function owns the implementation that CreateSnapshot constructs.
        return bOkay?std::static_pointer_cast<const GameplayResourceSnapshot>(Source):nullptr;
    };
    Fixtures.Captured=Capture(TEXT("structural capture"));
    Asset->Records[0].Payload[0]^=1;
    Fixtures.Payload=Capture(TEXT("payload checksum deferred to loader"));
    Asset->ManifestBytes.Add(uint8(' ')); // Still well-formed JSON; its bytes and checksum disagree.
    Fixtures.Combined=Capture(TEXT("combined checksums deferred to loader"));
    Asset->Records[0].Payload[0]^=1;
    Fixtures.Manifest=Capture(TEXT("manifest checksum deferred to loader"));
    std::shared_ptr<const GameplayResourceSource> Cached=Fixtures.Captured;
    const auto Before=Cached;FString Error;
    Asset->Version=0;
    Fixtures.bMalformedOutputRetained=!Asset->CreateSnapshot(Cached,Error) && Cached==Before
        && Error.Contains(TEXT("Unsupported runtime asset version"));
    IntegrityCheck(Report,Fixtures.bMalformedOutputRetained,TEXT("malformed capture preserves cached output"));
    // Keep none of the authoring state equal to the original receipt. Worker
    // verification must depend entirely on its own bytes and checksum strings.
    Asset->SourceIdentity=FString::ChrN(64,TEXT('b'));Asset->ManifestBytes.Reset();Asset->ManifestSha256.Reset();
    Asset->Records[0].Payload.Reset();Asset->Records[0].Sha256.Reset();
    Fixtures.bAuthoringMutated=true;
    return Fixtures;
}

class FIntegrityAuditSource final : public atelier::skate::GameplayResourceSource
{
public:
    explicit FIntegrityAuditSource(const atelier::skate::GameplayResourceSnapshot& Source):Source_(Source) {}
    bool VerifyIntegrity(std::string& Error) const override
    {++Verifications;return Source_.VerifyIntegrity(Error);}
    bool Read(std::string_view Name,std::vector<std::uint8_t>& Bytes,std::string& Error) const override
    {++Reads;return Source_.Read(Name,Bytes,Error);}
    bool EnumerateClips(std::vector<std::string>& Names,std::string& Error) const override
    {++Enumerations;return Source_.EnumerateClips(Names,Error);}
    bool Exists(std::string_view Name,bool& bExists,std::string& Error) const override
    {++ExistenceChecks;return Source_.Exists(Name,bExists,Error);}
    std::string_view ExpectedSourceIdentity() const override {return Source_.ExpectedSourceIdentity();}
    mutable int32 Verifications=0,Reads=0,Enumerations=0,ExistenceChecks=0;
private:
    const atelier::skate::GameplayResourceSnapshot& Source_;
};

void CheckIntegrityFixtures(const FIntegrityFixtures& Fixtures,FSkateRuntimeAssetValidationReport& Report)
{
    using namespace atelier::skate;
    const std::vector<std::uint8_t> Empty,Abc={'a','b','c'},Block(64,'a');
    IntegrityCheck(Report,HashByteView(Empty.data(),Empty.size())==
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",TEXT("SHA-256 empty vector"));
    IntegrityCheck(Report,HashByteView(Abc.data(),Abc.size())==
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",TEXT("SHA-256 short vector"));
    IntegrityCheck(Report,HashByteView(Block.data(),Block.size())==
        "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb",TEXT("SHA-256 complete block"));
    std::string Error;
    const bool bOwned=Fixtures.Captured && Fixtures.bAuthoringMutated
        && Fixtures.Captured->SourceIdentity()==std::string(64,'a')
        && Fixtures.Captured->Records()[0].bytes==Abc && Fixtures.Captured->VerifyIntegrity(Error);
    Report.bSnapshotImmutable=bOwned;
    IntegrityCheck(Report,bOwned,TEXT("captured bytes outlive authoring mutation"));
    Report.bSnapshotOutputRetained=Fixtures.bMalformedOutputRetained;
    auto Reject=[&Report](const std::shared_ptr<const GameplayResourceSnapshot>& Source,
        bool bExpectPayload,bool bExpectManifest,const TCHAR* Name)
    {
        bool bRejected=false,bRetained=false,bNoDecode=false;
        if(Source)
        {
            FIntegrityAuditSource Audit(*Source);
            const auto Cached=std::make_shared<const GameplayResources>();
            std::shared_ptr<const GameplayResources> Output=Cached;std::string Failure;
            bRejected=!LoadGameplayResources(Audit,Output,Failure)
                && (!bExpectPayload || Failure.find("Payload SHA-256 mismatch: action.graph")!=std::string::npos)
                && (!bExpectManifest || Failure.find("Source manifest SHA-256 mismatch")!=std::string::npos);
            bRetained=Output==Cached;
            bNoDecode=Audit.Verifications==1 && Audit.Reads==0 && Audit.Enumerations==0 && Audit.ExistenceChecks==0;
        }
        IntegrityCheck(Report,bRejected,Name);
        IntegrityCheck(Report,bNoDecode,TEXT("checksum failure precedes every resource read"));
        IntegrityCheck(Report,bRetained,TEXT("checksum failure preserves decoded resource output"));
        Report.bSnapshotOutputRetained=Report.bSnapshotOutputRetained && bRetained;
        return bRejected && bNoDecode;
    };
    const bool bPayload=Reject(Fixtures.Payload,true,false,TEXT("corrupt payload rejected"));
    const bool bManifest=Reject(Fixtures.Manifest,false,true,TEXT("corrupt manifest rejected"));
    const bool bCombined=Reject(Fixtures.Combined,true,true,TEXT("independent corruptions accumulated"));
    Report.bChecksumCorruptionRejected=bPayload && bManifest && bCombined;
}

// Explicit little-endian words, never C++ object bytes or struct padding.
struct FSessionWords
{
    TArray<uint8> Bytes;
    void Word(uint32 Value)
    {for(uint32 I=0;I<4;++I)Bytes.Add(static_cast<uint8>(Value>>(I*8)));}
    void Float(float Value)
    {uint32 Bits;std::memcpy(&Bits,&Value,4);Word(Bits);}
    void String(const std::string& Value)
    {Word(static_cast<uint32>(Value.size()));for(unsigned char Char:Value)Bytes.Add(Char);}
    void Vector(const atelier::skate::Vec3& Value)
    {Float(Value.x);Float(Value.y);Float(Value.z);}
    void Vector(const std::array<float,3>& Value)
    {for(float Lane:Value)Float(Lane);}
    void Vector(const atelier::skate::Vec4& Value)
    {for(float Lane:Value)Float(Lane);}
    void Matrix(const atelier::skate::Mat4& Value)
    {for(const auto& Column:Value)Vector(Column);}
    void Basis(const atelier::skate::Basis3& Value)
    {for(const auto& Column:Value.columns)Vector(Column);}
    void Session(const atelier::skate::GameplaySession& Session)
    {
        const auto Pose=Session.Pose();
        Word(static_cast<uint32>(Pose.tick));Word(static_cast<uint32>(Pose.tick>>32));String(Pose.state);
        Float(Session.Period());Matrix(Pose.root);Vector(Pose.velocity);
        Word(static_cast<uint32>(Pose.bones.size()));for(const auto& Bone:Pose.bones)Matrix(Bone);
        Word(static_cast<uint32>(Pose.names.size()));for(const auto& Name:Pose.names)String(Name);
        Word(Pose.camera.has_value());
        if(Pose.camera)
        {
            const auto& Camera=*Pose.camera;
            Basis(Camera.basis);Vector(Camera.position);Basis(Camera.previous_basis);Vector(Camera.previous_position);
            Vector(Camera.linear_velocity);Vector(Camera.angular_velocity);Vector(Camera.shake_translation);
            Word(Camera.discontinuity);Float(Camera.field_of_view_degrees);Float(Camera.opacity);Float(Camera.blur);
        }
        const auto& Score=Session.gameplay->scoring;
        const auto& Holder=Score.session.holder.State();
        const auto& Snapshot=Holder.snapshot;
        Float(Snapshot.completed_lines);Float(Snapshot.line);Float(Snapshot.accumulated);Float(Snapshot.last_reward);
        Float(Snapshot.general_pending);Float(Snapshot.fingerflip_pending);Float(Snapshot.grind_reward);
        for(auto Value:Holder.repetitions)Word(static_cast<uint32>(static_cast<int32>(Value)));
        for(auto Value:Holder.sequence_history)Word(static_cast<uint32>(static_cast<int32>(Value)));
        for(auto Value:Holder.type_history)Word(static_cast<uint32>(static_cast<int32>(Value)));
        Word(Holder.pending_sequence);Word(Holder.suppressed);
        Float(Score.session.combo.timer.points);Word(Score.session.combo.timer.expired);
        Float(Score.session.combo.multiplier);Float(Score.session.line.points);Word(Score.session.line.expired);
        String(Score.CurrentTrick());
    }
};

bool SessionHistory(std::shared_ptr<const atelier::skate::GameplayResources> Resources,
    int32 TicksPerStance,FSessionWords& Words,int32& ComparedTicks,std::string& Error)
{
    using namespace atelier::skate;
    GameplayWorldSnapshot Floor;
    Floor.triangles.push_back({Vec3{-100,0,-100},Vec3{-100,0,100},Vec3{100,0,100}});
    Floor.triangles.push_back({Vec3{-100,0,-100},Vec3{100,0,100},Vec3{100,0,-100}});
    for(uint32 Stance=0;Stance<2;++Stance)
    {
        Words.Word(Stance);
        std::unique_ptr<GameplaySession> Session;
        if(!GameplaySession::Create(Resources,Floor,{0,0,0},0,Session,Error)
            || !Session->Configure("easy",Stance!=0,0.5f,Error)
            || !Session->Tune(1,1,1,1,0,Error) || !Session->Activate({0,0,0},0,Error))return false;
        std::vector<Mat4> Reference;
        if(!Session->ReferencePose(Reference,Error))return false;
        Words.Word(static_cast<uint32>(Reference.size()));for(const auto& Bone:Reference)Words.Matrix(Bone);
        Words.Session(*Session);
        for(int32 Tick=0;Tick<TicksPerStance;++Tick)
        {
            XboxState Pad;
            if(Tick>=16 && Tick<80)Pad.buttons=0x1000;
            if(Tick>=40 && Tick<70)Pad.left[0]=8192;
            if(Tick>=80 && Tick<90)Pad.right[1]=-28000;
            if(Tick==90)Pad.right[1]=28000;
            if(!Session->Tick(Pad,Error) || !Session->CheckPublishedPose(Error))return false;
            Words.Session(*Session);++ComparedTicks;
        }
    }
    return true;
}
}

FSkateRuntimeAssetValidationReport USkateRuntimeAsset::ValidateSourceEquivalence(const FString& BundleDirectory,
    int32 TicksPerStance) const
{
    auto Report=Validate(true);
    if(!Report.bValid)return Report;
    if(TicksPerStance<1 || TicksPerStance>1200)
    {Report.Issues.Add(TEXT("Resource equivalence ticks per stance must be in 1..1200"));Report.bValid=false;return Report;}
    using namespace atelier::skate;
    const auto Source=CopySnapshot(*this);
    const auto Fixtures=PrepareIntegrityFixtures(Report);
    const auto Directory=NativeString(BundleDirectory);
    return AsyncThread([Source,Fixtures,Directory,TicksPerStance,Report=MoveTemp(Report)]() mutable
    {
    FScopedResourceFloatEnvironment FloatEnvironment;
    if(!FloatEnvironment.IsReady())
    {Report.Issues.Add(TEXT("Native resource floating-point environment setup failed"));Report.bValid=false;return Report;}
    CheckIntegrityFixtures(Fixtures,Report);
    std::shared_ptr<const GameplayResources> FileResources,AssetResources;
    std::string Error;
    if(!LoadGameplayResources(std::filesystem::u8path(Directory),FileResources,Error))
        Report.Issues.Add(TEXT("File resource loader: ")+FString(UTF8_TO_TCHAR(Error.c_str())));
    FIntegrityAuditSource AuditSource(*Source);
    const bool bLoadedAsset=LoadGameplayResources(AuditSource,AssetResources,Error);
    Report.bSnapshotIntegrityVerified=bLoadedAsset && AuditSource.Verifications==1 && AuditSource.Reads>0;
    IntegrityCheck(Report,Report.bSnapshotIntegrityVerified,TEXT("production loader verifies once before decoding"));
    if(!Report.bSnapshotIntegrityVerified)
        Report.Issues.Add(TEXT("Asset resource loader: ")+FString(UTF8_TO_TCHAR(Error.c_str())));
    if(FileResources && AssetResources)
    {
        FSessionWords FileWords,AssetWords;
        int32 FileTicks=0,AssetTicks=0;
        if(!SessionHistory(FileResources,TicksPerStance,FileWords,FileTicks,Error))
            Report.Issues.Add(TEXT("File resource session: ")+FString(UTF8_TO_TCHAR(Error.c_str())));
        if(!SessionHistory(AssetResources,TicksPerStance,AssetWords,AssetTicks,Error))
            Report.Issues.Add(TEXT("Asset resource session: ")+FString(UTF8_TO_TCHAR(Error.c_str())));
        Report.FileWordSha256=HashPayload(FileWords.Bytes);Report.AssetWordSha256=HashPayload(AssetWords.Bytes);
        Report.ComparedTicks=FMath::Min(FileTicks,AssetTicks);
        if(FileWords.Bytes!=AssetWords.Bytes)Report.Issues.Add(TEXT("File and asset session pose/camera/score words differ"));
        Report.bFileAssetEquivalent=Report.Issues.IsEmpty() && FileWords.Bytes==AssetWords.Bytes
            && FileTicks==TicksPerStance*2 && AssetTicks==FileTicks;
    }
    Report.bValid=Report.Issues.IsEmpty();return Report;
    },32*1024*1024).Get();
}
#endif
