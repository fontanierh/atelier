#include "SkateMotionData.h"
#include "SkateMotionAdapter.h"
#include "Native/GameplaySession.h"
#include "Native/AnimationName.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "HAL/FileManager.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"
#include <algorithm>
#include <utility>
#include <cstring>
#include <cmath>
#if WITH_EDITOR
#include "AssetRegistry/AssetRegistryModule.h"
#include "UObject/SavePackage.h"
#include "Misc/PackageName.h"
#endif

namespace skate = atelier::skate;
namespace
{
float Float(uint32 Word) { float Value; std::memcpy(&Value, &Word, 4); return Value; }
uint32 Bits(float Value) { uint32 Word; std::memcpy(&Word, &Value, 4); return Word; }
FString Text(const std::string& Value) { return UTF8_TO_TCHAR(Value.c_str()); }
std::string String(const FString& Value) { return TCHAR_TO_UTF8(*Value); }
template<class T, class F> auto Map(const std::vector<T>& Values, F Convert)
{
    using U = decltype(Convert(std::declval<T>())); TArray<U> Out; Out.Reserve(int32(Values.size()));
    for (const auto& V : Values) Out.Add(Convert(V)); return Out;
}
template<class T, class F> auto Map(const TArray<T>& Values, F Convert)
{
    using U = decltype(Convert(std::declval<T>())); std::vector<U> Out; Out.reserve(Values.Num());
    for (const auto& V : Values) Out.push_back(Convert(V)); return Out;
}
TArray<float> Floats(const std::vector<uint32>& V) { return Map(V, [](uint32 W) { return Float(W); }); }
std::vector<uint32> Words(const TArray<float>& V) { return Map(V, [](float F) { return Bits(F); }); }
TArray<FString> Texts(const std::vector<std::string>& V) { return Map(V, [](const auto& S) { return Text(S); }); }
std::vector<std::string> Strings(const TArray<FString>& V) { return Map(V, [](const auto& S) { return String(S); }); }
TArray<uint32> Indices(const std::vector<uint32>& V) { return Map(V, [](uint32 I) { return I; }); }
std::vector<uint32> Indices(const TArray<uint32>& V) { return Map(V, [](uint32 I) { return I; }); }
TArray<FSkateFloatRow> Rows(const std::vector<std::vector<uint32>>& V)
{ return Map(V, [](const auto& R) { FSkateFloatRow Row; Row.Values=Floats(R); return Row; }); }
std::vector<std::vector<uint32>> Rows(const TArray<FSkateFloatRow>& V)
{ return Map(V, [](const auto& R) { return Words(R.Values); }); }

FSkateSample ToAsset(const skate::SampleWords& In)
{
    FSkateSample Out;
    Out.ScaleX=Float(In[0]); Out.ScaleY=Float(In[1]); Out.ScaleZ=Float(In[2]);
    Out.RotationX=Float(In[3]); Out.RotationY=Float(In[4]); Out.RotationZ=Float(In[5]); Out.RotationW=Float(In[6]);
    Out.TranslationX=Float(In[7]); Out.TranslationY=Float(In[8]); Out.TranslationZ=Float(In[9]); return Out;
}
skate::SampleWords ToNative(const FSkateSample& In)
{
    return {Bits(In.ScaleX),Bits(In.ScaleY),Bits(In.ScaleZ),Bits(In.RotationX),Bits(In.RotationY),Bits(In.RotationZ),Bits(In.RotationW),Bits(In.TranslationX),Bits(In.TranslationY),Bits(In.TranslationZ)};
}
// Attribute kinds used by the source bundle: scalar and bone contact. The importer rejects unknown payloads.
// Zero alignment padding is reconstructed, not stored as asset data.
FSkateAttribute ToAsset(const skate::ClipAttributeMetadata& In)
{
    FSkateAttribute Out; Out.Name=Text(In.name); Out.Type=In.type_id;
    Out.Begin=Float(In.begin_bits); Out.End=Float(In.end_bits); Out.SourceOffset=int64(In.source_offset);
    Out.Value=Float(In.payload_words.size()>(In.type_id==3 ? 5u : 0u) ? In.payload_words[In.type_id==3 ? 5 : 0] : 0u); return Out;
}
skate::ClipAttributeMetadata ToNative(const FSkateAttribute& In)
{
    skate::ClipAttributeMetadata Out; Out.name=String(In.Name); Out.type_id=In.Type;
    Out.begin_bits=Bits(In.Begin); Out.end_bits=Bits(In.End); Out.source_offset=uint64(In.SourceOffset);
    Out.payload_words.resize(In.Type==3 ? 8 : 4,0);
    if(In.Type==3)
    {
        const auto Name=skate::EncodeAnimationName(String(In.TargetBone));
        std::copy(Name.begin(),Name.end(),Out.payload_words.begin()); Out.payload_words[5]=Bits(In.Value);
    }
    else Out.payload_words[0]=Bits(In.Value);
    return Out;
}
#include "SkateMotionConversions.inl"

FSkateMetadataBank ToAsset(const skate::AnimationMetadata& In)
{
    FSkateMetadataBank Out; Out.SourceBank=Text(In.source_bank); Out.SourceSha256=Text(In.source_sha256);
    Out.SourceBytes=int64(In.Sources().at(0).source_bytes);
    Out.Clips=Map(In.clips,[](const auto& V){return ToAsset(V);});
    Out.PhaseBlends=Map(In.phase_blends,[](const auto& V){return ToAsset(V);});
    Out.BlendSpaces=Map(In.blend_spaces,[](const auto& V){return ToAsset(V);});
    Out.Selectors=Map(In.selectors,[](const auto& V){return ToAsset(V);});
    Out.SelectionSpaces=Map(In.selection_spaces,[](const auto& V){return ToAsset(V);});
    Out.UnsupportedTrees=Map(In.unsupported_trees,[](const auto& V){return ToAsset(V);}); return Out;
}
bool ToNative(const FSkateMetadataBank& In, const skate::AnimationRig& Rig, skate::AnimationMetadata& Out, std::string& Error)
{
    if(In.SourceBytes<48) {Error="Invalid motion provenance size";return false;}
    for(const auto& Clip:In.Clips) for(const auto& A:Clip.Attributes)
    {
        if((A.Type!=0 && A.Type!=3) || !std::isfinite(A.Value)) {Error="Unsupported or non-finite motion attribute";return false;}
        if(A.Type==3 && std::none_of(Rig.bones.begin(),Rig.bones.end(),[&](const auto& B){return Text(B.name)==A.TargetBone;}))
        {Error="Motion attribute references an unknown bone";return false;}
    }
    Out.clips=Map(In.Clips,[](const auto& V){return ToNative(V);});
    Out.phase_blends=Map(In.PhaseBlends,[](const auto& V){return ToNative(V);});
    Out.blend_spaces=Map(In.BlendSpaces,[](const auto& V){return ToNative(V);});
    Out.selectors=Map(In.Selectors,[](const auto& V){return ToNative(V);});
    Out.selection_spaces=Map(In.SelectionSpaces,[](const auto& V){return ToNative(V);});
    Out.unsupported_trees=Map(In.UnsupportedTrees,[](const auto& V){return ToNative(V);});
    return Out.InitializeBank({String(In.SourceBank),String(In.SourceSha256),uint64(In.SourceBytes)},Error);
}
using Tracks=std::vector<std::vector<uint32>>;
FSkateMotionClip ToAsset(const skate::AnimationClipSamples& In)
{
    FSkateMotionClip Out; Out.Name=Text(In.name); Out.Bank=int32(In.bank); Out.SourceRecord=int64(In.record);
    Out.FrameRate=Float(In.fps_bits); Out.FrameCount=int32(In.frame_count); Out.bChannelAnimation=In.channel_animation;
    Out.LoopTranslation={Float(In.loop_translation[0]),Float(In.loop_translation[1]),Float(In.loop_translation[2])};
    Out.LoopRotation={Float(In.loop_rotation[0]),Float(In.loop_rotation[1]),Float(In.loop_rotation[2]),Float(In.loop_rotation[3])};
    for(uint32 B=0;B<In.bone_count;++B)
    {
        FSkateBoneTracks T; T.ChannelWeight=Float(In.channel_weights[B]); const auto& V=In.Tracks(); const auto I=B*10;
        T.ScaleX=Floats(V[I]);T.ScaleY=Floats(V[I+1]);T.ScaleZ=Floats(V[I+2]);
        T.RotationX=Floats(V[I+3]);T.RotationY=Floats(V[I+4]);T.RotationZ=Floats(V[I+5]);T.RotationW=Floats(V[I+6]);
        T.TranslationX=Floats(V[I+7]);T.TranslationY=Floats(V[I+8]);T.TranslationZ=Floats(V[I+9]);Out.Bones.Add(MoveTemp(T));
    }
    return Out;
}
bool ToNative(const FSkateMotionClip& In, skate::AnimationClipSamples& Out, std::string& Error)
{
    if(In.Bank<0 || In.SourceRecord<0 || In.FrameCount<=0) {Error="Invalid motion clip identity or frame count";return false;}
    Out.name=String(In.Name);Out.bank=uint32(In.Bank);Out.record=uint64(In.SourceRecord);
    Out.fps_bits=Bits(In.FrameRate);Out.frame_count=uint32(In.FrameCount);Out.bone_count=uint32(In.Bones.Num());
    Out.channel_animation=In.bChannelAnimation;
    for(const auto& Bone:In.Bones)Out.channel_weights.push_back(Bits(Bone.ChannelWeight));
    Out.loop_translation={Bits(In.LoopTranslation.X),Bits(In.LoopTranslation.Y),Bits(In.LoopTranslation.Z)};
    Out.loop_rotation={Bits(In.LoopRotation.X),Bits(In.LoopRotation.Y),Bits(In.LoopRotation.Z),Bits(In.LoopRotation.W)};
    Tracks V;V.reserve(In.Bones.Num()*10);
    for(const auto& T:In.Bones)
        for(const auto* C:{&T.ScaleX,&T.ScaleY,&T.ScaleZ,&T.RotationX,&T.RotationY,&T.RotationZ,&T.RotationW,&T.TranslationX,&T.TranslationY,&T.TranslationZ})
            V.push_back(Words(*C));
    return Out.SetTracks(std::move(V),Error);
}
}

bool DecodeSkateMotion(const USkateMotionData& Data, std::shared_ptr<const skate::AnimationSource>& Out, std::string& Error)
{
    if(!IsInGameThread()) {Error="Motion assets must be resolved on the game thread";return false;}
    if(Data.SchemaVersion!=1 || Data.Banks.IsEmpty() || Data.Metadata.IsEmpty()) {Error="Invalid motion data schema or empty banks";return false;}
    skate::AnimationPoseFrames Frames;Frames.rig.bones=Map(Data.Bones,[](const auto& V){return ToNative(V);});
    Frames.rig.has_trajectory=Data.bHasTrajectory;
    for(const auto& Pose:Data.ReferencePoses)if(Pose.Bank<0||Pose.SourceRecord<0) {Error="Invalid reference pose identity";return false;}
    Frames.rig.poses=Map(Data.ReferencePoses,[](const auto& V){return ToNative(V);});
    if(!Frames.rig.Reindex(Error))return false;
    auto Animation=std::make_shared<skate::AnimationSource>();
    for(int32 I=0;I<Data.Metadata.Num();++I)
    {
        skate::AnimationMetadata Bank;if(!ToNative(Data.Metadata[I],Frames.rig,Bank,Error))return false;
        if(I==0)Animation->metadata=std::move(Bank);else if(!Animation->metadata.Merge(Bank,Error))return false;
    }
    for(const auto& Ref:Data.Banks)
    {
        TStrongObjectPtr<USkateMotionBank> Bank(Ref.LoadSynchronous());
        if(!Bank.IsValid()){Error="Missing motion bank "+String(Ref.ToSoftObjectPath().ToString());return false;}
        for(const auto& In:Bank->Clips)
        {
            if(In.Bones.Num()!=Data.Bones.Num()){Error="Motion clip bone count differs from rig";return false;}
            for(int32 I=0;I<In.Bones.Num();++I)if(In.Bones[I].BoneName!=Data.Bones[I].Name)
            {Error="Motion bone track name/order differs from rig";return false;}
            auto Clip=std::make_shared<skate::AnimationClipSamples>();
            if(!ToNative(In,*Clip,Error)||!Frames.RegisterClip(Clip,Error))return false;
        }
    }
    Animation->evaluator=std::make_shared<skate::AnimationPoseEvaluator>(std::move(Frames));
    Out=std::move(Animation);Error.clear();return true;
}
bool LoadSkateMotion(const FSoftObjectPath& Path, std::shared_ptr<const skate::AnimationSource>& Out, FString& Error)
{
    TStrongObjectPtr<USkateMotionData> Data(Cast<USkateMotionData>(Path.TryLoad()));std::string NativeError;
    if(!Data.IsValid()) {Error=TEXT("Skate motion asset is missing: ")+Path.ToString();return false;}
    if(!DecodeSkateMotion(*Data,Out,NativeError)) {Error=Text(NativeError);return false;}
    Error.Reset();return true;
}

#if WITH_EDITOR
namespace
{
bool ReadFile(const FString& Path,std::vector<uint8>& Out,std::string& Error)
{
    TArray<uint8> Bytes;if(!FFileHelper::LoadFileToArray(Bytes,*Path)) {Error="Cannot read "+String(Path);return false;}
    Out.assign(Bytes.GetData(),Bytes.GetData()+Bytes.Num());return true;
}
template<class T> T* Asset(const FString& PackageName)
{
    const auto Name=FPackageName::GetLongPackageAssetName(PackageName);
    if(T* Existing=LoadObject<T>(nullptr,*(PackageName+TEXT(".")+Name)))return Existing;
    T* Out=NewObject<T>(CreatePackage(*PackageName),*Name,RF_Public|RF_Standalone);
    FAssetRegistryModule::AssetCreated(Out);return Out;
}
bool Save(UObject* Object,FString& Error)
{
    Object->MarkPackageDirty();FSavePackageArgs Args;Args.TopLevelFlags=RF_Public|RF_Standalone;
    const auto File=FPackageName::LongPackageNameToFilename(Object->GetOutermost()->GetName(),FPackageName::GetAssetPackageExtension());
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(File),true);
    if(!UPackage::SavePackage(Object->GetOutermost(),Object,*File,Args)) {Error=TEXT("Cannot save ")+File;return false;}
    return true;
}
bool AttributeTargets(FSkateMetadataBank& Out,const skate::AnimationMetadata& In,const skate::AnimationRig& Rig,std::string& Error)
{
    for(int32 C=0;C<Out.Clips.Num();++C) for(int32 I=0;I<Out.Clips[C].Attributes.Num();++I)
    {
        const auto& A=In.clips[C].attributes[I];const auto& P=A.payload_words;
        if((A.type_id!=0 && A.type_id!=3) || P.size()!=(A.type_id==3 ? 8u : 4u))
        {Error="Migration does not support attribute kind/shape for "+A.name;return false;}
        for(std::size_t J=A.type_id==3 ? 6 : 1;J<P.size();++J) if(P[J]!=0)
        {Error="Migration requires zero attribute alignment padding";return false;}
        if(A.type_id==3)
        {
            const auto Found=std::find_if(Rig.bones.begin(),Rig.bones.end(),[&](const auto& B)
            {const auto Key=skate::EncodeAnimationName(B.name);return std::equal(Key.begin(),Key.end(),P.begin());});
            if(Found==Rig.bones.end()){Error="Cannot resolve attribute bone "+A.name;return false;}
            Out.Clips[C].Attributes[I].TargetBone=Text(Found->name);
        }
    }
    return true;
}
}
#endif

bool USkateMotionLibrary::ImportMotion(const FString& ReferenceFolder,const FString& AssetFolder,FString& Error)
{
    Error.Reset();
    ON_SCOPE_EXIT { if(!Error.IsEmpty())UE_LOG(LogTemp,Error,TEXT("SKATE MOTION IMPORT: %s"),*Error); };
#if WITH_EDITOR
    if(!FPackageName::IsValidLongPackageName(AssetFolder)) {Error=TEXT("Invalid motion asset folder");return false;}
    std::string NativeError;std::shared_ptr<const skate::GameplayResources> Resources;
    if(!skate::LoadGameplayResources(std::filesystem::u8path(String(ReferenceFolder)),Resources,NativeError))
    {Error=Text(NativeError);return false;}
    const auto& Frames=Resources->animation->evaluator->frames;
    TStrongObjectPtr<USkateMotionData> Data(Asset<USkateMotionData>(AssetFolder/TEXT("MotionData")));
    Data->SchemaVersion=1;Data->bHasTrajectory=Frames.rig.has_trajectory;
    Data->Bones=Map(Frames.rig.bones,[](const auto& V){return ToAsset(V);});
    Data->ReferencePoses=Map(Frames.rig.poses,[](const auto& V){return ToAsset(V);});Data->Metadata.Reset();Data->Banks.Reset();
    for(int32 B=0;B<2;++B)
    {
        skate::AnimationMetadata Bank;std::vector<uint8> Bytes;
        if(!ReadFile(ReferenceFolder/FString::Printf(TEXT("metadata/bank-%d.skate"),B),Bytes,NativeError)||!Bank.Load(Bytes,NativeError))
        {Error=Text(NativeError);return false;}
        auto Typed=ToAsset(Bank);
        if(!AttributeTargets(Typed,Bank,Frames.rig,NativeError)) {Error=Text(NativeError);return false;}
        Data->Metadata.Add(MoveTemp(Typed));
    }
    constexpr int32 ChunkSize=128;int32 Index=0,Chunk=0;USkateMotionBank* Bank=nullptr;
    for(const auto& Pair:Frames.clips)
    {
        if(Index%ChunkSize==0)
        {
            if(Bank && !Save(Bank,Error))return false;
            Bank=Asset<USkateMotionBank>(AssetFolder/FString::Printf(TEXT("Banks/Bank_%03d"),Chunk++));Bank->Clips.Reset();
            Data->Banks.Add(TSoftObjectPtr<USkateMotionBank>(Bank));
        }
        auto TypedClip=ToAsset(*Pair.second);
        for(int32 B=0;B<TypedClip.Bones.Num();++B)TypedClip.Bones[B].BoneName=Text(Frames.rig.bones[B].name);
        Bank->Clips.Add(MoveTemp(TypedClip));++Index;
        if(Index%ChunkSize==0)UE_LOG(LogTemp,Display,TEXT("SKATE MOTION IMPORT %d/%d clips"),Index,int32(Frames.clips.size()));
    }
    if(Bank && !Save(Bank,Error))return false;
    if(!Save(Data.Get(),Error))return false;
    UE_LOG(LogTemp,Display,TEXT("SKATE MOTION IMPORT saved %d clips in %d banks"),Index,Chunk);Error.Reset();return true;
#else
    Error=TEXT("Motion migration requires an editor build");return false;
#endif
}

#if WITH_EDITOR
namespace
{
#include "SkateMotionEquality.inl"
bool SameMetadata(const skate::AnimationMetadata& A,const skate::AnimationMetadata& B)
{
    if(!Same(A.source_bank,B.source_bank)||!Same(A.source_sha256,B.source_sha256)||!Same(A.Sources(),B.Sources())
        ||!Same(A.clips,B.clips)||!Same(A.phase_blends,B.phase_blends)||!Same(A.blend_spaces,B.blend_spaces)
        ||!Same(A.selectors,B.selectors)||!Same(A.selection_spaces,B.selection_spaces)||!Same(A.unsupported_trees,B.unsupported_trees))return false;
    auto origins=[&](const auto& Values)
    {
        for(const auto& V:Values)
        {const auto* X=A.SourceFor(V.name);const auto* Y=B.SourceFor(V.name);if(!X||!Y||!Same(*X,*Y))return false;}
        return true;
    };
    return origins(A.clips)&&origins(A.phase_blends)&&origins(A.blend_spaces)&&origins(A.selectors)&&origins(A.selection_spaces)&&origins(A.unsupported_trees);
}
bool CompareMotion(const skate::AnimationSource& A,const skate::AnimationSource& B,uint64& Frames,uint64& Samples,std::string& Error)
{
    if(!SameMetadata(A.metadata,B.metadata)){Error="Motion metadata differs";return false;}
    const auto& X=A.evaluator->frames;const auto& Y=B.evaluator->frames;
    if(X.rig.has_trajectory!=Y.rig.has_trajectory || !Same(X.rig.bones,Y.rig.bones) || !Same(X.rig.poses,Y.rig.poses))
    {Error="Motion rig/reference poses differ";return false;}
    for(const auto& P:X.rig.poses)
    {
        const auto* AName=X.rig.NamedPose(P.bank,P.name);const auto* BName=Y.rig.NamedPose(P.bank,P.name);
        const auto* ARecord=X.rig.Pose(P.bank,P.record);const auto* BRecord=Y.rig.Pose(P.bank,P.record);
        if(!AName||!BName||!ARecord||!BRecord||!Same(*AName,*BName)||!Same(*ARecord,*BRecord))
        {Error="Motion reference lookup differs";return false;}
    }
    if(X.clips.size()!=Y.clips.size()){Error="Motion clip count differs";return false;}
    Frames=Samples=0;
    for(const auto& Pair:X.clips)
    {
        const auto It=Y.clips.find(Pair.first);if(It==Y.clips.end()){Error="Missing motion clip "+Pair.first;return false;}
        const auto& C=*Pair.second;const auto& D=*It->second;
        if(C.name!=D.name||C.bank!=D.bank||C.record!=D.record||C.fps_bits!=D.fps_bits||C.loop_translation!=D.loop_translation
            ||C.loop_rotation!=D.loop_rotation||C.channel_animation!=D.channel_animation||C.channel_weights!=D.channel_weights
            ||C.frame_count!=D.frame_count||C.bone_count!=D.bone_count)
        {Error="Motion clip fields/tracks differ: "+Pair.first;return false;}
        if(C.Tracks().size()!=D.Tracks().size()){Error="Motion track count differs: "+Pair.first;return false;}
        for(std::size_t I=0;I<C.Tracks().size();++I)
        {
            const auto& P=C.Tracks()[I];const auto& Q=D.Tracks()[I];
            if(P.size()!=Q.size()){Error="Motion track length differs: "+Pair.first;return false;}
            for(std::size_t J=0;J<P.size();++J)if(P[J]!=Q[J])
            {Error="Motion track differs: "+Pair.first+" component "+std::to_string(I)+" key "+std::to_string(J)
                +" bits "+std::to_string(P[J])+" versus "+std::to_string(Q[J]);return false;}
        }
        for(uint32 F=0;F<C.frame_count;++F) for(uint32 Bone=0;Bone<C.bone_count;++Bone)
            if(C.Sample(F,Bone)!=D.Sample(F,Bone)) {Error="Motion sample differs: "+Pair.first;return false;}
        Frames+=C.frame_count;Samples+=uint64(C.frame_count)*C.bone_count;
        if(Frames%10000<C.frame_count)UE_LOG(LogTemp,Display,TEXT("SKATE MOTION VERIFY %llu source frames compared"),Frames);
    }
    Error.clear();return true;
}
bool SamePose(const skate::GameplaySession& A,const skate::GameplaySession& B)
{
    const auto X=A.Pose(),Y=B.Pose();
    auto matrix=[](const auto& M,const auto& N)
    {for(int I=0;I<4;++I)for(int J=0;J<4;++J)if(Bits(M[I][J])!=Bits(N[I][J]))return false;return true;};
    if(!matrix(X.root,Y.root)||X.bones.size()!=Y.bones.size()||X.names!=Y.names||X.tick!=Y.tick||X.state!=Y.state
        ||Bits(X.velocity.x)!=Bits(Y.velocity.x)||Bits(X.velocity.y)!=Bits(Y.velocity.y)||Bits(X.velocity.z)!=Bits(Y.velocity.z))return false;
    for(std::size_t I=0;I<X.bones.size();++I)if(!matrix(X.bones[I],Y.bones[I]))return false;
    if(X.camera.has_value()!=Y.camera.has_value())return false;
    if(X.camera)
    {
        const auto& C=*X.camera;const auto& D=*Y.camera;
        for(const auto Pair:{std::make_pair(C.position,D.position),std::make_pair(C.previous_position,D.previous_position),
            std::make_pair(C.linear_velocity,D.linear_velocity),std::make_pair(C.angular_velocity,D.angular_velocity),
            std::make_pair(C.shake_translation,D.shake_translation)})
            for(int I=0;I<4;++I)if(Bits(Pair.first[I])!=Bits(Pair.second[I]))return false;
        for(int I=0;I<3;++I)for(int J=0;J<3;++J)
            if(Bits(C.basis.columns[I][J])!=Bits(D.basis.columns[I][J])
                ||Bits(C.previous_basis.columns[I][J])!=Bits(D.previous_basis.columns[I][J]))return false;
        if(C.discontinuity!=D.discontinuity||Bits(C.field_of_view_degrees)!=Bits(D.field_of_view_degrees)
            ||Bits(C.opacity)!=Bits(D.opacity)||Bits(C.blur)!=Bits(D.blur))return false;
    }
    const auto& P=A.gameplay->scoring.session.holder.State().snapshot;
    const auto& Q=B.gameplay->scoring.session.holder.State().snapshot;
    return Bits(P.completed_lines)==Bits(Q.completed_lines)&&Bits(P.line)==Bits(Q.line)&&Bits(P.last_reward)==Bits(Q.last_reward)
        &&A.gameplay->scoring.CurrentTrick()==B.gameplay->scoring.CurrentTrick()
        &&Bits(A.gameplay->animation_input.fields.balance)==Bits(B.gameplay->animation_input.fields.balance);
}
bool Replays(std::shared_ptr<const skate::GameplayResources> A,std::shared_ptr<const skate::GameplayResources> B,uint64& Steps,std::string& Error)
{
    skate::GameplayWorldSnapshot World;
    World.triangles={{{{-100,0,-100},{-100,0,100},{100,0,100}}},{{{-100,0,-100},{100,0,100},{100,0,-100}}}};
    Steps=0;
    for(bool Goofy:{false,true}) for(int Scenario=0;Scenario<6;++Scenario)
    {
        std::unique_ptr<skate::GameplaySession> X,Y;
        for(auto* S:{&X,&Y})
        {
            if(!skate::GameplaySession::Create(S==&X?A:B,World,{0,0,0},0,*S,Error)
                ||!(*S)->Configure("normal",Goofy,.5f,Error)||!(*S)->Tune(1.15f,1.6f,1.15f,1.45f,1.f,Error)
                ||!(*S)->Activate({0,0,0},0,Error))return false;
            if(Scenario>=2)(*S)->Launch({0,0,5});
        }
        if(!SamePose(*X,*Y)){Error="Initial replay pose differs";return false;}
        for(int F=0;F<600;++F)
        {
            skate::XboxState Input{};
            if(Scenario<2 && F>=30 && F<210)Input.buttons=0x1000;
            if(F>=240 && F<264)Input.right={0,-32767};
            if(F>=264 && F<266)Input.right={0,32767};
            if(Scenario==1 && F>=270 && F<400)Input.left={14000,0};
            if((Scenario==2||Scenario==3) && F>=260 && F<350)Input.left={int16(Scenario==2?32767:-32767),0};
            if(Scenario==4 && F>=380 && F<460)Input.left={19660,-26213};
            if(Scenario==5 && F>=264 && F<276)Input.right={int16((F-264)*5000-30000),int16(30000-(F-264)*4000)};
            const float Dt=Scenario==0?1.f/30.f:1.f/60.f;
            if(!X->Step(Input,Dt,Error)||!Y->Step(Input,Dt,Error))return false;
            if(!SamePose(*X,*Y)){Error="Replay differs at scenario "+std::to_string(Scenario)+" frame "+std::to_string(F);return false;}
            ++Steps;
        }
        UE_LOG(LogTemp,Display,TEXT("SKATE MOTION REPLAY stance=%d scenario=%d: 600 matching steps"),int(Goofy),Scenario);
    }
    return true;
}
}
#endif

bool USkateMotionLibrary::VerifyMotion(const FString& ReferenceFolder,USkateMotionData* Data,const FString& ReportFile,FString& Error)
{
    Error.Reset();
    ON_SCOPE_EXIT { if(!Error.IsEmpty())UE_LOG(LogTemp,Error,TEXT("SKATE MOTION VERIFY: %s"),*Error); };
#if WITH_EDITOR
    std::string E;std::shared_ptr<const skate::GameplayResources> Reference,Runtime;
    std::shared_ptr<const skate::AnimationSource> Typed;
    if(!Data||!skate::LoadGameplayResources(std::filesystem::u8path(String(ReferenceFolder)),Reference,E)||!DecodeSkateMotion(*Data,Typed,E))
    {Error=Text(E);return false;}
    uint64 Frames=0,Samples=0,Steps=0;
    if(!CompareMotion(*Reference->animation,*Typed,Frames,Samples,E)){Error=Text(E);return false;}
    // Prove the production asset-backed resource loader needs no animation/metadata .skate files.
    const FString Fixture=FPaths::GetPath(ReportFile)/TEXT("asset-runtime-fixture");IFileManager::Get().MakeDirectory(*Fixture,true);
    for(const TCHAR* File:{TEXT("settings.skate"),TEXT("physics-skeletons.skate"),TEXT("action.graph"),TEXT("motion.graph"),TEXT("camera.graph"),TEXT("camera.skate"),TEXT("gestures.skate")})
        if(IFileManager::Get().Copy(*(Fixture/File),*(ReferenceFolder/File))!=COPY_OK){Error=TEXT("Cannot create isolated runtime fixture");return false;}
    if(!skate::LoadGameplayResources(std::filesystem::u8path(String(Fixture)),Runtime,E,Typed)||!Replays(Reference,Runtime,Steps,E))
    {Error=Text(E);return false;}
    // A one-bit sample change must fail the exact checker (without changing saved source assets).
    auto* Bank=Data->Banks[0].LoadSynchronous();auto& V=Bank->Clips[0].Bones[0].ScaleX[0];const float Saved=V;V=Float(Bits(V)^1u);
    std::shared_ptr<const skate::AnimationSource> Changed;const bool Decoded=DecodeSkateMotion(*Data,Changed,E);V=Saved;
    uint64 F=0,S=0;const bool Detected=Decoded&&!CompareMotion(*Reference->animation,*Changed,F,S,E);
    if(!Detected){Error=TEXT("Negative control did not detect the changed motion sample");return false;}
    FString BankPaths;
    for(const auto& Ref:Data->Banks)
    {if(!BankPaths.IsEmpty())BankPaths+=TEXT(",");BankPaths+=TEXT("\"")+Ref.ToSoftObjectPath().ToString()+TEXT("\"");}
    // Invalid editable records must fail admission, rather than reaching native assertions.
    const int32 Parent=Data->Bones[0].Parent;Data->Bones[0].Parent=0;
    std::shared_ptr<const skate::AnimationSource> Invalid;const bool RejectedRig=!DecodeSkateMotion(*Data,Invalid,E);Data->Bones[0].Parent=Parent;
    auto& Track=Bank->Clips[0].Bones[0].ScaleX;TArray<float> SavedTrack=Track;Track.Reset();
    const bool RejectedTrack=!DecodeSkateMotion(*Data,Invalid,E);Track=MoveTemp(SavedTrack);
    const float Rate=Data->Metadata[0].Clips[0].FrameRate;Data->Metadata[0].Clips[0].FrameRate=0;
    const bool RejectedMetadata=!DecodeSkateMotion(*Data,Invalid,E);Data->Metadata[0].Clips[0].FrameRate=Rate;
    if(!RejectedRig||!RejectedTrack||!RejectedMetadata) {Error=TEXT("Malformed typed record was accepted");return false;}
    const auto Report=FString::Printf(TEXT("{\"schema\":1,\"clips\":%llu,\"frames\":%llu,\"bone_samples\":%llu,\"replay_steps\":%llu,\"replay_cases\":12,\"exact\":true,\"negative_control\":true,\"invalid_record_controls\":3,\"runtime_without_motion_files\":true,\"banks\":[%s]}\n"),
        uint64(Typed->evaluator->frames.clips.size()),Frames,Samples,Steps,*BankPaths);
    if(!FFileHelper::SaveStringToFile(Report,*ReportFile)){Error=TEXT("Cannot save motion verification report");return false;}
    Error.Reset();return true;
#else
    Error=TEXT("Motion verification requires an editor build");return false;
#endif
}
