#include "SkateRuntimeData.h"
#include "SkateRuntimeAdapter.h"
#include "SkateMotionAdapter.h"
#include "SkateDataLibrary.h"
#include "SkateAssetPackages.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "Misc/SecureHash.h"
#include "UObject/StrongObjectPtr.h"
#include "Misc/PackageName.h"
#include "Engine/StreamableManager.h"
#include "Async/Async.h"
#include "Tasks/Task.h"
#include <cstring>
#include <map>
#include <type_traits>
#include <utility>

namespace skate = atelier::skate;
namespace
{
// The runtime files in their wire formats: little-endian words, length-prefixed UTF-8 strings, no padding.
constexpr const char* SettingsFile="settings.skate";
constexpr const char* ActionGraphFile="action.graph";
constexpr const char* MotionGraphFile="motion.graph";
constexpr const char* CameraGraphFile="camera.graph";
constexpr const char* CameraFile="camera.skate";
constexpr const char* GesturesFile="gestures.skate";
constexpr const char* PhysicsFile="physics-skeletons.skate";
constexpr const char* RuntimeFiles[]={SettingsFile,ActionGraphFile,MotionGraphFile,CameraGraphFile,CameraFile,GesturesFile,PhysicsFile};
constexpr int32 PhysicalBoneWords=28;

std::string Utf8(const FString& Value)
{
    const FTCHARToUTF8 Converted(*Value,Value.Len());return std::string(Converted.Get(),Converted.Length());
}
FString FromUtf8(const std::string& Value)
{
    const FUTF8ToTCHAR Converted(Value.data(),int32(Value.size()));return FString(Converted.Length(),Converted.Get());
}

struct FWriter
{
    std::vector<uint8> Bytes;
    explicit FWriter(const char* Magic):Bytes(Magic,Magic+8){}
    void Word(uint32 Value){for(int32 I=0;I<4;++I)Bytes.push_back(uint8(Value>>(8*I)));}
    void Wide(uint64 Value){Word(uint32(Value));Word(uint32(Value>>32));}
    void Raw(const std::string& Value){Bytes.insert(Bytes.end(),Value.begin(),Value.end());}
    void Text(const std::string& Value){Word(uint32(Value.size()));Raw(Value);}
    void Text(const FString& Value){Text(Utf8(Value));}
    void Words(const TArray<uint32>& Values){for(const uint32 Value:Values)Word(Value);}
};
struct FReader
{
    const std::vector<uint8>& Bytes;std::size_t At=8;bool bOk;
    FReader(const std::vector<uint8>& InBytes,const char* Magic)
        :Bytes(InBytes),bOk(InBytes.size()>=8 && std::memcmp(InBytes.data(),Magic,8)==0){}
    bool Need(std::size_t Count){bOk=bOk && Count<=Bytes.size()-At;return bOk;}
    uint32 Word()
    {
        if(!Need(4))return 0;
        const uint32 Value=uint32(Bytes[At])|(uint32(Bytes[At+1])<<8)|(uint32(Bytes[At+2])<<16)|(uint32(Bytes[At+3])<<24);
        At+=4;return Value;
    }
    uint64 Wide(){const uint64 Low=Word();return Low|(uint64(Word())<<32);}
    std::string Raw(std::size_t Count)
    {
        if(!Need(Count))return {};
        std::string Value(reinterpret_cast<const char*>(Bytes.data()+At),Count);At+=Count;return Value;
    }
    FString Text(){return FromUtf8(Raw(Word()));}
    void Words(TArray<uint32>& Values,std::size_t Count)
    {
        Values.Reset();if(!Need(Count*4))return;
        for(std::size_t I=0;I<Count;++I)Values.Add(Word());
    }
    bool End() const {return bOk && At==Bytes.size();}
};
// A string table: every distinct string, sorted by its UTF-8 bytes.
struct FStrings
{
    std::map<std::string,uint32> Index;
    void Add(const FString& Value){Index.emplace(Utf8(Value),0);}
    void Number(){uint32 Next=0;for(auto& Pair:Index)Pair.second=Next++;}
    uint32 operator[](const FString& Value) const {return Index.at(Utf8(Value));}
    void Write(FWriter& Out) const {for(const auto& Pair:Index)Out.Text(Pair.first);}
};
bool Table(FReader& In,uint32 Count,std::vector<FString>& Out)
{
    Out.clear();if(!In.Need(std::size_t(Count)*4))return false;
    for(uint32 I=0;I<Count && In.bOk;++I)Out.push_back(In.Text());
    return In.bOk;
}
bool Entry(FReader& In,const std::vector<FString>& Strings,FString& Out)
{
    const uint32 Index=In.Word();if(!In.bOk || Index>=Strings.size())return In.bOk=false;
    Out=Strings[Index];return true;
}

// ------------------------------------------------------------------ settings (ATATTR01)
bool DecodeSettings(const std::vector<uint8>& Bytes,TArray<FSkateSettingRecord>& Out)
{
    FReader In(Bytes,"ATATTR01");std::vector<FString> Strings;
    const uint32 StringCount=In.Word(),RecordCount=In.Word();
    if(!Table(In,StringCount,Strings) || !In.Need(std::size_t(RecordCount)*16))return false;
    Out.Reset();
    for(uint32 R=0;R<RecordCount && In.bOk;++R)
    {
        FSkateSettingRecord& Record=Out.AddDefaulted_GetRef();
        if(!Entry(In,Strings,Record.Category) || !Entry(In,Strings,Record.Key) || !Entry(In,Strings,Record.Parent))return false;
        const uint32 FieldCount=In.Word();if(!In.Need(std::size_t(FieldCount)*16))return false;
        for(uint32 F=0;F<FieldCount && In.bOk;++F)
        {
            FSkateSettingField& Field=Record.Fields.AddDefaulted_GetRef();
            if(!Entry(In,Strings,Field.Name) || !Entry(In,Strings,Field.Type))return false;
            const uint32 Encoding=In.Word(),Size=In.Word();
            if(Encoding>1 || Size>uint32(MAX_int32))return false;
            Field.bText=Encoding==1;
            if(Field.bText)Field.Text=FromUtf8(In.Raw(Size));
            else {Field.Bytes=int32(Size);In.Words(Field.Words,(std::size_t(Size)+3)/4);}
        }
    }
    return In.End();
}
bool EncodeSettings(const TArray<FSkateSettingRecord>& Records,std::vector<uint8>& Out,std::string& Error)
{
    FStrings Strings;
    for(const auto& Record:Records)
    {
        Strings.Add(Record.Category);Strings.Add(Record.Key);Strings.Add(Record.Parent);
        for(const auto& Field:Record.Fields){Strings.Add(Field.Name);Strings.Add(Field.Type);}
    }
    Strings.Number();
    FWriter W("ATATTR01");W.Word(uint32(Strings.Index.size()));W.Word(uint32(Records.Num()));Strings.Write(W);
    for(const auto& Record:Records)
    {
        W.Word(Strings[Record.Category]);W.Word(Strings[Record.Key]);W.Word(Strings[Record.Parent]);W.Word(uint32(Record.Fields.Num()));
        for(const auto& Field:Record.Fields)
        {
            W.Word(Strings[Field.Name]);W.Word(Strings[Field.Type]);W.Word(Field.bText ? 1 : 0);
            if(Field.bText)
            {
                if(Field.Bytes!=0 || !Field.Words.IsEmpty()){Error="Settings text field "+Utf8(Field.Name)+" holds words";return false;}
                const std::string Text=Utf8(Field.Text);W.Word(uint32(Text.size()));W.Raw(Text);
            }
            else
            {
                if(Field.Bytes<0 || Field.Words.Num()!=(Field.Bytes+3)/4 || !Field.Text.IsEmpty())
                {Error="Settings field "+Utf8(Field.Name)+" words differ from its byte count";return false;}
                W.Word(uint32(Field.Bytes));W.Words(Field.Words);
            }
        }
    }
    Out=MoveTemp(W.Bytes);return true;
}

// ------------------------------------------------------------------ graphs (ATGRPH01)
bool DecodeGraph(const std::vector<uint8>& Bytes,FSkateGraph& Out)
{
    FReader In(Bytes,"ATGRPH01");std::vector<FString> Strings;
    const uint32 StringCount=In.Word(),ElementCount=In.Word();
    if(!Table(In,StringCount,Strings) || !In.Need(std::size_t(ElementCount)*16))return false;
    Out.Elements.Reset();
    for(uint32 E=0;E<ElementCount && In.bOk;++E)
    {
        FSkateGraphElement& Element=Out.Elements.AddDefaulted_GetRef();
        Element.SourceOffset=In.Word();
        if(!Entry(In,Strings,Element.Tag))return false;
        const uint32 AttributeCount=In.Word(),ChildCount=In.Word();
        if(!In.Need(std::size_t(AttributeCount)*16+std::size_t(ChildCount)*4))return false;
        for(uint32 A=0;A<AttributeCount;++A)
        {
            FSkateGraphAttribute& Attribute=Element.Attributes.AddDefaulted_GetRef();
            if(!Entry(In,Strings,Attribute.Name) || !Entry(In,Strings,Attribute.Text))return false;
            Attribute.Number=In.Word();const uint32 Flag=In.Word();
            if(Flag>1)return false;
            Attribute.bTrue=Flag==1;
        }
        for(uint32 C=0;C<ChildCount;++C)
        {const uint32 Child=In.Word();if(Child>=ElementCount)return false;Element.Children.Add(int32(Child));}
    }
    return In.End();
}
bool EncodeGraph(const FSkateGraph& Graph,std::vector<uint8>& Out,std::string& Error)
{
    FStrings Strings;
    for(const auto& Element:Graph.Elements)
    {
        Strings.Add(Element.Tag);
        for(const auto& Attribute:Element.Attributes){Strings.Add(Attribute.Name);Strings.Add(Attribute.Text);}
    }
    Strings.Number();
    FWriter W("ATGRPH01");W.Word(uint32(Strings.Index.size()));W.Word(uint32(Graph.Elements.Num()));Strings.Write(W);
    for(const auto& Element:Graph.Elements)
    {
        W.Word(Element.SourceOffset);W.Word(Strings[Element.Tag]);
        W.Word(uint32(Element.Attributes.Num()));W.Word(uint32(Element.Children.Num()));
        for(const auto& Attribute:Element.Attributes)
        {W.Word(Strings[Attribute.Name]);W.Word(Strings[Attribute.Text]);W.Word(Attribute.Number);W.Word(Attribute.bTrue ? 1 : 0);}
        for(const int32 Child:Element.Children)
        {
            if(Child<0 || Child>=Graph.Elements.Num()){Error="Graph child index out of range in "+Utf8(Element.Tag);return false;}
            W.Word(uint32(Child));
        }
    }
    Out=MoveTemp(W.Bytes);return true;
}

// ------------------------------------------------------------------ camera (ATCAM001)
// A shot's words in file order: a uint32 field, or a fixed-size array.
template<class Shot,class Visit> void ShotWords(Shot& S,Visit&& Field)
{
    Field(S.Distance,1);Field(S.LensLength,1);Field(S.Smoothing,4);Field(S.ReferenceWeights,10);Field(S.BoardOffset,1);
    Field(S.PositionHeading,1);Field(S.PositionElevation,1);Field(S.Framing,3);Field(S.FollowSubjectInAir,1);
    Field(S.MirrorForStance,1);Field(S.SnapToReferencePoint,1);Field(S.UsePreviousShot,1);Field(S.UseDropPredictor,1);
    Field(S.UseFreeCameraStick,1);Field(S.AvoidanceOverride,1);Field(S.Blur,1);Field(S.TransitionBlur,1);
    Field(S.SubjectOpacity,1);Field(S.CollisionHint,1);Field(S.Anchor,1);Field(S.CompassNorth,1);Field(S.WorldHeading,1);
    Field(S.ArmOrientation,4);Field(S.CameraOrientation,4);
}
template<class T> constexpr bool IsWord=std::is_same_v<std::decay_t<T>,uint32>;
bool DecodeCamera(const std::vector<uint8>& Bytes,USkateRuntimeData& Out)
{
    FReader In(Bytes,"ATCAM001");
    Out.CameraSource=In.Text();
    const uint32 ShotCount=In.Word();if(!In.Need(std::size_t(ShotCount)*4))return false;
    Out.CameraShots.Reset();
    for(uint32 I=0;I<ShotCount && In.bOk;++I)
    {
        FSkateCameraShot& Shot=Out.CameraShots.AddDefaulted_GetRef();
        Shot.Name=In.Text();Shot.ShotType=In.Word();
        ShotWords(Shot,[&](auto& Value,int32 Count){if constexpr(IsWord<decltype(Value)>)Value=In.Word();else In.Words(Value,Count);});
        Shot.TransitionTime=In.Word();Shot.TransitionUnits=In.Word();
        for(int32 Slot=0;Slot<3;++Slot)
        {
            const uint32 Present=In.Word();
            // Children fill the slots from the first.
            if(Present>1 || (Present && Shot.Children.Num()!=Slot))return false;
            if(Present)Shot.Children.Add(In.Text());
        }
        In.Words(Shot.BlendPoints,3);Shot.BlendValue=In.Word();Shot.BlendType=In.Word();Shot.BlendSmoothing=In.Word();
    }
    Out.CameraShakes.Reset();
    for(int32 I=0;I<2 && In.bOk;++I)
    {
        FSkateCameraShake& Shake=Out.CameraShakes.AddDefaulted_GetRef();
        const uint32 Samples=In.Word();if(!In.Need(std::size_t(Samples)*32))return false;
        for(uint32 S=0;S<Samples;++S)
        {
            for(int32 L=0;L<4;++L)Shake.Rotations.Add(In.Word());
            for(int32 L=0;L<4;++L)Shake.Translations.Add(In.Word());
        }
    }
    return In.End();
}
bool EncodeCamera(const USkateRuntimeData& Data,std::vector<uint8>& Out,std::string& Error)
{
    FWriter W("ATCAM001");W.Text(Data.CameraSource);W.Word(uint32(Data.CameraShots.Num()));
    for(const auto& Shot:Data.CameraShots)
    {
        W.Text(Shot.Name);W.Word(Shot.ShotType);bool bSized=true;
        ShotWords(Shot,[&](const auto& Value,int32 Count)
        {
            if constexpr(IsWord<decltype(Value)>)W.Word(Value);
            else {bSized&=Value.Num()==Count;W.Words(Value);}
        });
        if(!bSized || Shot.BlendPoints.Num()!=3 || Shot.Children.Num()>3)
        {Error="Camera shot "+Utf8(Shot.Name)+" has a wrong number of values";return false;}
        W.Word(Shot.TransitionTime);W.Word(Shot.TransitionUnits);
        for(int32 Slot=0;Slot<3;++Slot)
        {
            W.Word(Slot<Shot.Children.Num() ? 1 : 0);
            if(Slot<Shot.Children.Num())W.Text(Shot.Children[Slot]);
        }
        W.Words(Shot.BlendPoints);W.Word(Shot.BlendValue);W.Word(Shot.BlendType);W.Word(Shot.BlendSmoothing);
    }
    if(Data.CameraShakes.Num()!=2){Error="Camera data has two shakes";return false;}
    for(const auto& Shake:Data.CameraShakes)
    {
        if(Shake.Rotations.Num()!=Shake.Translations.Num() || Shake.Rotations.Num()%4)
        {Error="A camera shake has four rotation and four translation words per sample";return false;}
        W.Word(uint32(Shake.Rotations.Num()/4));
        for(int32 S=0;S<Shake.Rotations.Num();S+=4)
        {
            for(int32 L=0;L<4;++L)W.Word(Shake.Rotations[S+L]);
            for(int32 L=0;L<4;++L)W.Word(Shake.Translations[S+L]);
        }
    }
    Out=MoveTemp(W.Bytes);return true;
}

// ------------------------------------------------------------------ gestures (ATGEST01)
bool DecodeGestures(const std::vector<uint8>& Bytes,TArray<FSkateGestureSet>& Out)
{
    FReader In(Bytes,"ATGEST01");
    const uint32 SetCount=In.Word();if(!In.Need(std::size_t(SetCount)*12))return false;
    Out.Reset();
    for(uint32 I=0;I<SetCount && In.bOk;++I)
    {
        FSkateGestureSet& Set=Out.AddDefaulted_GetRef();
        Set.Name=In.Text();Set.Stick=In.Word();
        const uint32 PatternCount=In.Word();if(!In.Need(std::size_t(PatternCount)*12))return false;
        for(uint32 P=0;P<PatternCount && In.bOk;++P)
        {
            FSkateGesturePattern& Pattern=Set.Patterns.AddDefaulted_GetRef();
            Pattern.Name=In.Text();Pattern.ToleranceSquared=In.Word();
            const uint32 Points=In.Word();In.Words(Pattern.Points,std::size_t(Points)*2);
        }
    }
    return In.End();
}
bool EncodeGestures(const TArray<FSkateGestureSet>& Sets,std::vector<uint8>& Out,std::string& Error)
{
    FWriter W("ATGEST01");W.Word(uint32(Sets.Num()));
    for(const auto& Set:Sets)
    {
        W.Text(Set.Name);W.Word(Set.Stick);W.Word(uint32(Set.Patterns.Num()));
        for(const auto& Pattern:Set.Patterns)
        {
            if(Pattern.Points.Num()%2){Error="Gesture "+Utf8(Pattern.Name)+" points are x and y pairs";return false;}
            W.Text(Pattern.Name);W.Word(Pattern.ToleranceSquared);W.Word(uint32(Pattern.Points.Num()/2));W.Words(Pattern.Points);
        }
    }
    Out=MoveTemp(W.Bytes);return true;
}

// ------------------------------------------------------------------ physical skeletons (ATPHYS01)
bool DecodePhysics(const std::vector<uint8>& Bytes,USkateRuntimeData& Out)
{
    FReader In(Bytes,"ATPHYS01");
    Out.PhysicalSource=In.Text();
    const uint32 SkeletonCount=In.Word();if(!In.Need(std::size_t(SkeletonCount)*16))return false;
    Out.PhysicalSkeletons.Reset();
    for(uint32 I=0;I<SkeletonCount && In.bOk;++I)
    {
        FSkatePhysicalSkeleton& Skeleton=Out.PhysicalSkeletons.AddDefaulted_GetRef();
        Skeleton.Name=In.Text();Skeleton.SourceOffset=In.Wide();
        const uint32 BoneCount=In.Word();if(!In.Need(std::size_t(BoneCount)*(16+PhysicalBoneWords*4)))return false;
        for(uint32 B=0;B<BoneCount && In.bOk;++B)
        {
            FSkatePhysicalBone& Bone=Skeleton.Bones.AddDefaulted_GetRef();
            Bone.Name=In.Text();Bone.SourceOffset=In.Wide();In.Words(Bone.Words,PhysicalBoneWords);
        }
    }
    return In.End();
}
bool EncodePhysics(const USkateRuntimeData& Data,std::vector<uint8>& Out,std::string& Error)
{
    FWriter W("ATPHYS01");W.Text(Data.PhysicalSource);W.Word(uint32(Data.PhysicalSkeletons.Num()));
    for(const auto& Skeleton:Data.PhysicalSkeletons)
    {
        W.Text(Skeleton.Name);W.Wide(Skeleton.SourceOffset);W.Word(uint32(Skeleton.Bones.Num()));
        for(const auto& Bone:Skeleton.Bones)
        {
            if(Bone.Words.Num()!=PhysicalBoneWords){Error="Physical bone "+Utf8(Bone.Name)+" has 28 words";return false;}
            W.Text(Bone.Name);W.Wide(Bone.SourceOffset);W.Words(Bone.Words);
        }
    }
    Out=MoveTemp(W.Bytes);return true;
}

FString Sha1(const std::vector<uint8>& Bytes){return FSHA1::HashBuffer(Bytes.data(),Bytes.size()).ToString();}
bool EncodeFiles(const USkateRuntimeData& Data,skate::RuntimePayloads& Out,std::string& Error)
{
    Out.clear();
    return EncodeSettings(Data.Settings,Out[SettingsFile],Error) && EncodeGraph(Data.ActionGraph,Out[ActionGraphFile],Error)
        && EncodeGraph(Data.MotionGraph,Out[MotionGraphFile],Error) && EncodeGraph(Data.CameraGraph,Out[CameraGraphFile],Error)
        && EncodeCamera(Data,Out[CameraFile],Error) && EncodeGestures(Data.Gestures,Out[GesturesFile],Error)
        && EncodePhysics(Data,Out[PhysicsFile],Error);
}
}

bool EncodeSkateRuntime(const USkateRuntimeData& Data,skate::RuntimePayloads& Out,std::string& Error)
{
    if(Data.SchemaVersion!=USkateRuntimeData::CurrentSchema)
    {Error="Invalid skate runtime data schema; rerun the runtime import";return false;}
    if(!EncodeFiles(Data,Out,Error))return false;
    if(Data.Digests.Num()!=int32(Out.size())){Error="Skate runtime data has no digest for every file";return false;}
    for(const auto& Digest:Data.Digests)
    {
        const auto Found=Out.find(Utf8(Digest.File));
        if(Found==Out.end() || int64(Found->second.size())!=Digest.Bytes || Sha1(Found->second)!=Digest.Sha1)
        {Error="Skate runtime file differs from its recorded digest: "+Utf8(Digest.File);return false;}
    }
    Error.clear();return true;
}

namespace
{
// One process-wide load per runtime asset, as for motion (SkateMotionData.cpp). Game-thread state, except the promise,
// which the encode task fulfils.
struct FRuntimeLoad
{
    std::promise<FSkateRuntimeLoad> Promise;FSkateRuntimeFuture Future;
    TSharedPtr<FStreamableHandle> Handle;bool bEncoding=false,bDone=false;
};
TMap<FSoftObjectPath,TSharedRef<FRuntimeLoad>>& RuntimeLoads(){static TMap<FSoftObjectPath,TSharedRef<FRuntimeLoad>> Loads;return Loads;}
void ReleaseRuntime(const FSoftObjectPath& Path,const TSharedRef<FRuntimeLoad>& Load,bool bForget)
{
    check(IsInGameThread());
    if(Load->Handle){Load->Handle->ReleaseHandle();Load->Handle.Reset();}
    const auto* Current=RuntimeLoads().Find(Path);
    if(bForget && Current && &Current->Get()==&Load.Get())RuntimeLoads().Remove(Path);
}
void EncodeRuntime(const FSoftObjectPath& Path,const TSharedRef<FRuntimeLoad>& Load)
{
    if(Load->bDone||Load->bEncoding)return;
    const auto* Data=Cast<USkateRuntimeData>(Path.ResolveObject());
    if(!Data)
    {
        Load->bDone=true;Load->Promise.set_value({nullptr,"Skate runtime asset is missing: "+Utf8(Path.ToString())});
        ReleaseRuntime(Path,Load,true);return;
    }
    Load->bEncoding=true;
    // The streamable handle keeps the package loaded until the task hands the result back to the game thread.
    UE::Tasks::Launch(UE_SOURCE_LOCATION,[Path,Load,Data]()
    {
        FSkateRuntimeLoad Result;auto Payloads=std::make_shared<skate::RuntimePayloads>();
        if(EncodeSkateRuntime(*Data,*Payloads,Result.Error))Result.Payloads=std::move(Payloads);
        const bool bOk=bool(Result.Payloads);
        Load->Promise.set_value(MoveTemp(Result));
        AsyncTask(ENamedThreads::GameThread,[Path,Load,bOk](){Load->bDone=true;ReleaseRuntime(Path,Load,!bOk);});
    });
}
}

FSkateRuntimeFuture RequestSkateRuntime(const FSoftObjectPath& Path)
{
    check(IsInGameThread());
    if(const auto* Found=RuntimeLoads().Find(Path))return (*Found)->Future;
    TSharedRef<FRuntimeLoad> Load=MakeShared<FRuntimeLoad>();Load->Future=Load->Promise.get_future().share();
    RuntimeLoads().Add(Path,Load);
    Load->Handle=SkateStreamer().RequestAsyncLoad(Path,FStreamableDelegate::CreateLambda([Path,Load](){EncodeRuntime(Path,Load);}));
    if(!Load->Handle)
    {
        Load->bDone=true;Load->Promise.set_value({nullptr,"Cannot request the skate runtime asset "+Utf8(Path.ToString())});
        ReleaseRuntime(Path,Load,true);
    }
    return Load->Future;
}
void CompleteSkateRuntime(const FSoftObjectPath& Path)
{
    RequestSkateRuntime(Path);
    const auto* Found=RuntimeLoads().Find(Path);if(!Found)return;
    const TSharedRef<FRuntimeLoad> Load=*Found;
    if(Load->bDone||Load->bEncoding)return;
    if(Load->Handle)Load->Handle->WaitUntilComplete();
    EncodeRuntime(Path,Load);
}

bool USkateDataLibrary::ImportRuntime(const FString& PackageFolder,const FString& AssetFolder,FString& Error)
{
    Error.Reset();
    ON_SCOPE_EXIT { if(!Error.IsEmpty())UE_LOG(LogTemp,Error,TEXT("SKATE RUNTIME IMPORT: %s"),*Error); };
#if WITH_EDITOR
    if(!FPackageName::IsValidLongPackageName(AssetFolder)) {Error=TEXT("Invalid runtime asset folder");return false;}
    skate::RuntimePayloads Files;
    for(const char* Name:RuntimeFiles)
    {
        TArray<uint8> Bytes;const FString File=PackageFolder/UTF8_TO_TCHAR(Name);
        if(!FFileHelper::LoadFileToArray(Bytes,*File)) {Error=TEXT("Cannot read ")+File;return false;}
        Files[Name].assign(Bytes.GetData(),Bytes.GetData()+Bytes.Num());
    }
    TStrongObjectPtr<USkateRuntimeData> Data(SkateAssetPackages::Asset<USkateRuntimeData>(AssetFolder/TEXT("RuntimeData")));
    Data->SchemaVersion=USkateRuntimeData::CurrentSchema;
    if(!DecodeSettings(Files[SettingsFile],Data->Settings) || !DecodeGraph(Files[ActionGraphFile],Data->ActionGraph)
        || !DecodeGraph(Files[MotionGraphFile],Data->MotionGraph) || !DecodeGraph(Files[CameraGraphFile],Data->CameraGraph)
        || !DecodeCamera(Files[CameraFile],*Data) || !DecodeGestures(Files[GesturesFile],Data->Gestures)
        || !DecodePhysics(Files[PhysicsFile],*Data))
    {Error=TEXT("A runtime file is malformed");return false;}
    // The typed records must encode back to every file byte for byte before they are saved.
    std::string Failure;skate::RuntimePayloads Encoded;
    if(!EncodeFiles(*Data,Encoded,Failure)){Error=UTF8_TO_TCHAR(Failure.c_str());return false;}
    Data->Digests.Reset();
    for(const char* Name:RuntimeFiles)
    {
        if(Encoded[Name]!=Files[Name]){Error=FString::Printf(TEXT("Typed %hs does not encode to the same bytes"),Name);return false;}
        Data->Digests.Add({UTF8_TO_TCHAR(Name),int32(Files[Name].size()),Sha1(Files[Name])});
    }
    if(!SkateAssetPackages::Save(Data.Get(),Error))return false;
    UE_LOG(LogTemp,Display,TEXT("SKATE RUNTIME IMPORT saved %d settings records, %d camera shots, %d gesture sets"),
        Data->Settings.Num(),Data->CameraShots.Num(),Data->Gestures.Num());
    Error.Reset();return true;
#else
    Error=TEXT("Runtime import requires an editor build");return false;
#endif
}
