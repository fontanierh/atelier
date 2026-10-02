// SPDX-License-Identifier: Apache-2.0
#include "SkateCookedProbe.h"

#include "SkateCollisionAsset.h"
#include "SkateCollisionWorld.h"
#include "SkateProfile.h"
#include "SkateRuntimeAsset.h"
#include "SkateSettings.h"
#include "Native/GameplaySession.h"
#include "Async/Async.h"
#include "Containers/StringConv.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProperties.h"
#include "Misc/CommandLine.h"
#include "Misc/CoreDelegates.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PhysicsEngine/BodySetup.h"
#include "RenderingThread.h"
#include "StaticMeshResources.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"
#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstring>
#include <iterator>

namespace
{
using namespace atelier::skate;
FDelegateHandle ProbeDelegate;
FString ProbeReportPath;
bool bProbeStarted=false;
constexpr int32 ProbeTicks=480;
constexpr uint32 NativeStackBytes=32*1024*1024;

FString Text(const std::string& Value)
{return FString(UTF8_TO_TCHAR(Value.c_str()));}
std::string NativeText(const FString& Value)
{const FTCHARToUTF8 Utf8(*Value);return std::string(Utf8.Get(),Utf8.Length());}
TArray<TSharedPtr<FJsonValue>> Strings(const TArray<FString>& Values)
{
    TArray<TSharedPtr<FJsonValue>> Result;
    for(const auto& Value:Values)Result.Add(MakeShared<FJsonValueString>(Value));
    return Result;
}
TArray<TSharedPtr<FJsonValue>> VectorJson(const FVector& Value)
{
    return {MakeShared<FJsonValueNumber>(Value.X),MakeShared<FJsonValueNumber>(Value.Y),
        MakeShared<FJsonValueNumber>(Value.Z)};
}

class FProbeFloatEnvironment
{
public:
    FProbeFloatEnvironment()
    {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
        bSaved=std::fegetenv(&Saved)==0;
        bReady=bSaved && std::fesetenv(FE_DFL_ENV)==0;
    }
    ~FProbeFloatEnvironment()
    {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
        if(bSaved)std::fesetenv(&Saved);
    }
    bool Ready() const {return bReady;}
    FProbeFloatEnvironment(const FProbeFloatEnvironment&)=delete;
    FProbeFloatEnvironment& operator=(const FProbeFloatEnvironment&)=delete;
private:
    std::fenv_t Saved{};
    bool bSaved=false,bReady=false;
};

// Explicit little-endian public words avoid hashing ABI padding or lossy JSON.
struct FProbeWords
{
    TArray<uint8> Bytes;
    void Word(uint32 Value)
    {for(uint32 I=0;I<4;++I)Bytes.Add(static_cast<uint8>(Value>>(8*I)));}
    void Float(float Value)
    {uint32 Bits;std::memcpy(&Bits,&Value,4);Word(Bits);}
    void String(const std::string& Value)
    {Word(static_cast<uint32>(Value.size()));for(unsigned char Char:Value)Bytes.Add(Char);}
    void Vector(const Vec3& Value) {Float(Value.x);Float(Value.y);Float(Value.z);}
    void Vector(const Vec4& Value) {for(float Lane:Value)Float(Lane);}
    void Matrix(const Mat4& Value) {for(const auto& Column:Value)Vector(Column);}
    void Basis(const Basis3& Value)
    {for(const auto& Column:Value.columns)for(float Lane:Column)Float(Lane);}
    void Pose(const GameplayPose& Value)
    {
        Word(static_cast<uint32>(Value.tick));Word(static_cast<uint32>(Value.tick>>32));String(Value.state);
        Matrix(Value.root);Vector(Value.velocity);
        Word(static_cast<uint32>(Value.bones.size()));for(const auto& Bone:Value.bones)Matrix(Bone);
        Word(static_cast<uint32>(Value.names.size()));for(const auto& Name:Value.names)String(Name);
    }
    void Camera(const std::optional<camera::CameraFrame>& Value)
    {
        Word(Value.has_value());
        if(!Value)return;
        const auto& C=*Value;
        Basis(C.basis);Vector(C.position);Basis(C.previous_basis);Vector(C.previous_position);
        Vector(C.linear_velocity);Vector(C.angular_velocity);Vector(C.shake_translation);
        Word(C.discontinuity);Float(C.field_of_view_degrees);Float(C.opacity);Float(C.blur);
    }
    void Score(const ScoringRuntime& Value)
    {
        const auto& Holder=Value.session.holder.State();const auto& S=Holder.snapshot;
        Float(S.completed_lines);Float(S.line);Float(S.accumulated);Float(S.last_reward);
        Float(S.general_pending);Float(S.fingerflip_pending);Float(S.grind_reward);
        for(auto V:Holder.repetitions)Word(static_cast<uint32>(static_cast<int32>(V)));
        for(auto V:Holder.sequence_history)Word(static_cast<uint32>(static_cast<int32>(V)));
        for(auto V:Holder.type_history)Word(static_cast<uint32>(static_cast<int32>(V)));
        Word(Holder.pending_sequence);Word(Holder.suppressed);
        Float(Value.session.combo.timer.points);Word(Value.session.combo.timer.expired);
        Float(Value.session.combo.multiplier);Float(Value.session.line.points);Word(Value.session.line.expired);
        String(Value.CurrentTrick());
    }
};

bool Finite(const Vec3& V)
{return std::isfinite(V.x)&&std::isfinite(V.y)&&std::isfinite(V.z);}
bool Finite(const Vec4& V)
{return std::all_of(V.begin(),V.end(),[](float F){return std::isfinite(F);});}
bool Finite(const Basis3& B)
{
    return std::all_of(B.columns.begin(),B.columns.end(),[](const auto& Column)
        {return std::all_of(Column.begin(),Column.end(),[](float Lane){return std::isfinite(Lane);});});
}
bool Finite(const camera::CameraFrame& C)
{
    return Finite(C.basis)&&Finite(C.position)&&Finite(C.previous_basis)&&Finite(C.previous_position)
        &&Finite(C.linear_velocity)&&Finite(C.angular_velocity)&&Finite(C.shake_translation)
        &&std::isfinite(C.field_of_view_degrees)&&C.field_of_view_degrees>0&&C.field_of_view_degrees<180
        &&std::isfinite(C.opacity)&&std::isfinite(C.blur);
}
bool Finite(const ScoringRuntime& Value)
{
    const auto& S=Value.session.holder.State().snapshot;
    const float Values[]={S.completed_lines,S.line,S.accumulated,S.last_reward,S.general_pending,
        S.fingerflip_pending,S.grind_reward,Value.session.combo.timer.points,Value.session.combo.multiplier,
        Value.session.line.points};
    return std::all_of(std::begin(Values),std::end(Values),[](float V){return std::isfinite(V);});
}

struct FStanceProbe
{
    bool bGoofy=false,bCreated=false,bConfigured=false,bTuned=false,bActivated=false,bReference=false;
    bool bOllieSupportedBeforeRelease=false,bTrickSupportedBeforeRelease=false;
    int32 Ticks=0,SupportTicks=0,AirTicks=0,OllieAirTicks=0,TrickAirTicks=0,TrickingTicks=0,CameraTicks=0;
    int32 TrickWindowTrickingTicks=0;
    int32 PoseChanges=0,PushTicks=0;
    float MaxHorizontalSpeed=0,PushDisplacement=0;
    uint64 FinalTick=0;
    TArray<FString> States,TrickNames,Issues;
    FString PoseHash,ReferenceHash,CameraHash,ScoreHash;
    int32 PoseBytes=0,CameraBytes=0,ScoreBytes=0,ReferenceBones=0;
};
struct FNativeProbeResult
{
    bool bFloatEnvironment=false,bLoaded=false;
    int32 ClipCount=0;
    TArray<FString> Issues;
    TArray<FStanceProbe> Stances;
};
struct FProbeTuning
{
    std::string Difficulty;
    float Trucks=0.5f,Pop=1,Spin=1,Speed=1,Power=1,Vert=0;
};

XboxState ProbePad(int32 Tick,bool bGoofy)
{
    XboxState Pad;
    // Settle first; then hold actual push, coast, and two distinct pad flicks.
    // These are controller inputs, never completed contacts/trajectory/pose.
    if(Tick>=120 && Tick<168)Pad.buttons=0x1000;
    if(Tick>=192 && Tick<204)Pad.right[1]=-28000;
    if(Tick==204)Pad.right[1]=28000;
    if(Tick>=348 && Tick<360)Pad.right[1]=-28000;
    if(Tick==360){Pad.right[0]=bGoofy?-24000:24000;Pad.right[1]=28000;}
    return Pad;
}

FStanceProbe RunStance(std::shared_ptr<const GameplayResources> Resources,
    const GameplayWorldSnapshot& World,const FProbeTuning& Tuning,bool bGoofy)
{
    FStanceProbe R;R.bGoofy=bGoofy;
    std::string Error;std::unique_ptr<GameplaySession> Session;
    R.bCreated=GameplaySession::Create(std::move(Resources),World,{0,0,0},0,Session,Error);
    if(!R.bCreated){R.Issues.Add(TEXT("Session construction: ")+Text(Error));return R;}
    R.bConfigured=Session->Configure(Tuning.Difficulty,bGoofy,Tuning.Trucks,Error);
    if(!R.bConfigured){R.Issues.Add(TEXT("Profile configuration: ")+Text(Error));return R;}
    R.bTuned=Session->Tune(Tuning.Pop,Tuning.Spin,Tuning.Speed,Tuning.Power,Tuning.Vert,Error);
    if(!R.bTuned){R.Issues.Add(TEXT("Profile tuning: ")+Text(Error));return R;}
    R.bActivated=Session->Activate({0,0,0},0,Error);
    if(!R.bActivated){R.Issues.Add(TEXT("Session activation: ")+Text(Error));return R;}
    std::vector<Mat4> Reference;
    R.bReference=Session->ReferencePose(Reference,Error);
    FProbeWords ReferenceWords;
    if(!R.bReference)R.Issues.Add(TEXT("Reference pose: ")+Text(Error));
    else
    {
        R.ReferenceBones=static_cast<int32>(Reference.size());ReferenceWords.Word(R.ReferenceBones);
        for(const auto& Bone:Reference)
        {
            ReferenceWords.Matrix(Bone);
            for(const auto& Column:Bone)if(!Finite(Column))R.Issues.Add(TEXT("Reference pose contains nonfinite data"));
        }
        if(Reference.empty())R.Issues.Add(TEXT("Reference pose is empty"));
    }
    R.ReferenceHash=USkateRuntimeAsset::HashPayload(ReferenceWords.Bytes);
    FProbeWords PoseWords,CameraWords,ScoreWords;
    TArray<uint8> PreviousMotion;
    Vec3 PushStart{};bool bHavePushStart=false;
    bool bBadPose=false,bBadCamera=false,bBadScore=false,bBadPeriod=false,bBadShape=false;
    for(int32 Tick=0;Tick<ProbeTicks;++Tick)
    {
        const auto Pad=ProbePad(Tick,bGoofy);
        if(Pad.buttons)++R.PushTicks;
        if(Tick==204)R.bOllieSupportedBeforeRelease=Session->gameplay->input->processed.wheel_count_2556>0;
        if(Tick==360)R.bTrickSupportedBeforeRelease=Session->gameplay->input->processed.wheel_count_2556>0;
        if(!Session->Tick(Pad,Error))
        {R.Issues.Add(FString::Printf(TEXT("Tick %d: %s"),Tick,*Text(Error)));break;}
        ++R.Ticks;
        const auto Pose=Session->Pose();R.FinalTick=Pose.tick;
        R.States.AddUnique(Text(Pose.state));
        const bool bAir=PhysicalStateCategory(Session->gameplay->player_state->Current())==200;
        if(bAir){++R.AirTicks;if(Tick>=204 && Tick<348)++R.OllieAirTicks;if(Tick>=360)++R.TrickAirTicks;}
        if(Session->gameplay->animation->action.is_tricking.value_or(false))
        {++R.TrickingTicks;if(Tick>=360)++R.TrickWindowTrickingTicks;}
        if(Session->gameplay->input->processed.wheel_count_2556>0)++R.SupportTicks;
        if(!Session->CheckPublishedPose(Error)&&!bBadPose)
        {bBadPose=true;R.Issues.Add(FString::Printf(TEXT("Published pose at tick %d: %s"),Tick,*Text(Error)));}
        if((Pose.bones.empty()||Pose.names.size()!=Pose.bones.size())&&!bBadShape)
        {bBadShape=true;R.Issues.Add(TEXT("Public pose has empty or mismatched bone/name arrays"));}
        if((!std::isfinite(Session->Period())||Session->Period()<=0)&&!bBadPeriod)
        {bBadPeriod=true;R.Issues.Add(TEXT("Simulation period is nonfinite or nonpositive"));}
        if(Pose.camera)
        {
            ++R.CameraTicks;
            if(!Finite(*Pose.camera)&&!bBadCamera)
            {bBadCamera=true;R.Issues.Add(TEXT("Public camera has nonfinite data or an invalid field of view"));}
        }
        if(!Finite(Session->gameplay->scoring)&&!bBadScore)
        {bBadScore=true;R.Issues.Add(TEXT("Public score contains nonfinite data"));}
        const auto& Name=Session->gameplay->scoring.CurrentTrick();
        if(!Name.empty())R.TrickNames.AddUnique(Text(Name));
        const float Speed=std::hypot(Pose.velocity.x,Pose.velocity.z);
        if(Tick>=120 && Tick<=191 && std::isfinite(Speed))
            R.MaxHorizontalSpeed=std::max(R.MaxHorizontalSpeed,Speed);
        const Vec3 Position{Pose.root[3][0],Pose.root[3][1],Pose.root[3][2]};
        if(Tick==120){PushStart=Position;bHavePushStart=true;}
        if(Tick==191 && bHavePushStart)
            R.PushDisplacement=std::hypot(Position.x-PushStart.x,Position.z-PushStart.z);
        FProbeWords Motion;Motion.Matrix(Pose.root);
        Motion.Word(static_cast<uint32>(Pose.bones.size()));for(const auto& Bone:Pose.bones)Motion.Matrix(Bone);
        if(!PreviousMotion.IsEmpty()&&PreviousMotion!=Motion.Bytes)++R.PoseChanges;
        PreviousMotion=MoveTemp(Motion.Bytes);
        PoseWords.Pose(Pose);CameraWords.Float(Session->Period());CameraWords.Camera(Pose.camera);
        ScoreWords.Score(Session->gameplay->scoring);
    }
    if(R.Ticks!=ProbeTicks)R.Issues.Add(TEXT("The complete raw-input history did not execute"));
    if(R.SupportTicks==0)R.Issues.Add(TEXT("No actual wheel support was published by the baked geometry"));
    if(!(R.MaxHorizontalSpeed>0.1f && R.PushDisplacement>0.05f))
        R.Issues.Add(TEXT("Actual push produced insufficient horizontal speed/displacement"));
    if(!R.bOllieSupportedBeforeRelease || R.OllieAirTicks==0)
        R.Issues.Add(TEXT("The raw ollie flick did not launch from actual wheel support into on-board air"));
    if(!R.bTrickSupportedBeforeRelease || R.TrickAirTicks==0 || R.TrickWindowTrickingTicks==0)
        R.Issues.Add(TEXT("The second raw flick did not launch from actual support into air/tricking publication"));
    if(R.CameraTicks==0)R.Issues.Add(TEXT("The session published no camera"));
    if(R.PoseChanges==0)R.Issues.Add(TEXT("The session published no pose motion"));
    R.PoseBytes=PoseWords.Bytes.Num();R.CameraBytes=CameraWords.Bytes.Num();R.ScoreBytes=ScoreWords.Bytes.Num();
    R.PoseHash=USkateRuntimeAsset::HashPayload(PoseWords.Bytes);
    R.CameraHash=USkateRuntimeAsset::HashPayload(CameraWords.Bytes);
    R.ScoreHash=USkateRuntimeAsset::HashPayload(ScoreWords.Bytes);
    return R;
}

FNativeProbeResult RunNative(std::shared_ptr<const GameplayResourceSource> Source,
    GameplayWorldSnapshot World,FProbeTuning Tuning)
{
    FNativeProbeResult R;FProbeFloatEnvironment Environment;R.bFloatEnvironment=Environment.Ready();
    if(!R.bFloatEnvironment){R.Issues.Add(TEXT("Could not establish the default native float environment"));return R;}
    std::string Error;std::vector<std::string> Clips;
    if(Source->EnumerateClips(Clips,Error))R.ClipCount=static_cast<int32>(Clips.size());
    else R.Issues.Add(TEXT("Snapshot clip enumeration: ")+Text(Error));
    std::shared_ptr<const GameplayResources> Resources;
    R.bLoaded=LoadGameplayResources(*Source,Resources,Error);
    if(!R.bLoaded){R.Issues.Add(TEXT("Asset-only native resource decode/integrity: ")+Text(Error));return R;}
    // Decoded resources own their storage. Release the raw 70 MB snapshot here.
    Source.reset();
    if(World.triangles.empty())
    {R.Issues.Add(TEXT("Stance sessions are blocked because no actual baked collision snapshot was captured"));return R;}
    for(bool bGoofy:{false,true})R.Stances.Add(RunStance(Resources,World,Tuning,bGoofy));
    return R;
}

TSharedRef<FJsonObject> StanceJson(const FStanceProbe& R)
{
    auto J=MakeShared<FJsonObject>();
    J->SetBoolField(TEXT("goofy"),R.bGoofy);J->SetBoolField(TEXT("valid"),R.Issues.IsEmpty());
    J->SetBoolField(TEXT("created"),R.bCreated);J->SetBoolField(TEXT("configured"),R.bConfigured);
    J->SetBoolField(TEXT("tuned"),R.bTuned);J->SetBoolField(TEXT("activated"),R.bActivated);
    J->SetBoolField(TEXT("reference_pose_loaded"),R.bReference);
    J->SetNumberField(TEXT("requested_ticks"),ProbeTicks);J->SetNumberField(TEXT("executed_ticks"),R.Ticks);
    J->SetStringField(TEXT("final_tick"),FString::Printf(TEXT("%llu"),static_cast<unsigned long long>(R.FinalTick)));
    J->SetNumberField(TEXT("support_ticks"),R.SupportTicks);J->SetNumberField(TEXT("air_ticks"),R.AirTicks);
    J->SetNumberField(TEXT("ollie_air_ticks"),R.OllieAirTicks);J->SetNumberField(TEXT("trick_air_ticks"),R.TrickAirTicks);
    J->SetNumberField(TEXT("tricking_ticks"),R.TrickingTicks);J->SetNumberField(TEXT("camera_ticks"),R.CameraTicks);
    J->SetNumberField(TEXT("second_flick_tricking_ticks"),R.TrickWindowTrickingTicks);
    J->SetBoolField(TEXT("ollie_supported_before_release"),R.bOllieSupportedBeforeRelease);
    J->SetBoolField(TEXT("trick_supported_before_release"),R.bTrickSupportedBeforeRelease);
    J->SetNumberField(TEXT("pose_changes"),R.PoseChanges);J->SetNumberField(TEXT("push_input_ticks"),R.PushTicks);
    J->SetNumberField(TEXT("max_horizontal_speed_mps"),R.MaxHorizontalSpeed);
    if(std::isfinite(R.PushDisplacement))J->SetNumberField(TEXT("push_displacement_m"),R.PushDisplacement);
    else J->SetStringField(TEXT("push_displacement_m"),TEXT("nonfinite"));
    J->SetNumberField(TEXT("reference_bones"),R.ReferenceBones);
    J->SetNumberField(TEXT("pose_word_bytes"),R.PoseBytes);J->SetNumberField(TEXT("camera_word_bytes"),R.CameraBytes);
    J->SetNumberField(TEXT("score_word_bytes"),R.ScoreBytes);
    J->SetStringField(TEXT("pose_sha256"),R.PoseHash);J->SetStringField(TEXT("reference_pose_sha256"),R.ReferenceHash);
    J->SetStringField(TEXT("camera_sha256"),R.CameraHash);J->SetStringField(TEXT("score_sha256"),R.ScoreHash);
    J->SetArrayField(TEXT("states"),Strings(R.States));J->SetArrayField(TEXT("trick_names"),Strings(R.TrickNames));
    J->SetArrayField(TEXT("issues"),Strings(R.Issues));return J;
}

void PackageEvidence(const UObject* Object,const FString& Role,TArray<FString>& Issues,
    TArray<TSharedPtr<FJsonValue>>& Packages)
{
    if(!Object){Issues.Add(Role+TEXT(": asset did not load"));return;}
    const UPackage* Package=Object->GetOutermost();
    const bool bCooked=Package&&Package->HasAnyPackageFlags(PKG_Cooked);
    auto J=MakeShared<FJsonObject>();J->SetStringField(TEXT("role"),Role);
    J->SetStringField(TEXT("object"),Object->GetPathName());
    J->SetStringField(TEXT("package"),Package?Package->GetName():FString());
    J->SetBoolField(TEXT("cooked"),bCooked);Packages.Add(MakeShared<FJsonValueObject>(J));
    if(!bCooked)Issues.Add(Role+TEXT(": package is not marked PKG_Cooked: ")+Object->GetPathName());
}

struct FFloorFace
{
    USkateCollisionMeshData* Data=nullptr;
    UStaticMesh* Mesh=nullptr;
    int32 Triangle=INDEX_NONE;
    FVector Centre=FVector::ZeroVector,Normal=FVector::ZeroVector;
    double ClearanceCm=0,AreaCm2=0;
};
void ConsiderFloor(USkateCollisionMeshData* Data,UStaticMesh* Mesh,FFloorFace& Best)
{
    for(int32 I=0;I+2<Data->Indices.Num();I+=3)
    {
        FVector A(Data->Positions[Data->Indices[I]]),B(Data->Positions[Data->Indices[I+1]]),
            C(Data->Positions[Data->Indices[I+2]]);
        const FVector Authored(Data->TangentZ[Data->Indices[I]]);
        if(FVector::DotProduct(FVector::CrossProduct(B-A,C-A),Authored)<0)Swap(B,C);
        const FVector Cross=FVector::CrossProduct(B-A,C-A);
        const double TwiceArea=Cross.Size();if(!(TwiceArea>0))continue;
        const FVector Normal=Cross/TwiceArea;
        if(Normal.Z<0.9999999 || FMath::Max3(A.Z,B.Z,C.Z)-FMath::Min3(A.Z,B.Z,C.Z)>0.01)continue;
        const FVector Centre=(A+B+C)/3.0;
        const double Clearance=TwiceArea/(3.0*FMath::Max3((B-A).Size(),(C-B).Size(),(A-C).Size()));
        if(Clearance>Best.ClearanceCm)
        {Best={Data,Mesh,I/3,Centre,Normal,Clearance,TwiceArea/2.0};}
    }
}

TSharedRef<FJsonObject> RenderBufferEvidence(const UStaticMesh& Mesh,TArray<FString>& Issues)
{
    auto J=MakeShared<FJsonObject>();
    J->SetBoolField(TEXT("allow_cpu_access"),Mesh.bAllowCPUAccess);
    if(Mesh.bAllowCPUAccess)Issues.Add(TEXT("Selected cooked complex mesh still allows render CPU access"));
    const auto* RenderData=Mesh.GetRenderData();
    J->SetBoolField(TEXT("render_data_present"),RenderData!=nullptr);
    TArray<TSharedPtr<FJsonValue>> Lods;
    if(RenderData)for(int32 I=0;I<RenderData->LODResources.Num();++I)
    {
        const auto& Lod=RenderData->LODResources[I];
        const auto& Positions=Lod.VertexBuffers.PositionVertexBuffer;
        const auto& Indices=Lod.IndexBuffer;
        auto L=MakeShared<FJsonObject>();L->SetNumberField(TEXT("lod"),I);
        L->SetNumberField(TEXT("position_vertex_metadata_count"),Positions.GetNumVertices());
        L->SetBoolField(TEXT("position_initialized"),Positions.IsInitialized());
        L->SetBoolField(TEXT("position_cpu_access"),Positions.GetAllowCPUAccess());
        L->SetBoolField(TEXT("position_cached_pointer_nonnull"),Positions.GetVertexData()!=nullptr);
        L->SetStringField(TEXT("position_allocation_visibility"),
            TEXT("Private VertexData allocation; cached pointer is not a live CPU allocation test in UE5.8"));
        L->SetBoolField(TEXT("index_initialized"),Indices.IsInitialized());
        L->SetBoolField(TEXT("index_cpu_access"),Indices.GetAllowCPUAccess());
        L->SetNumberField(TEXT("index_retained_bytes"),Indices.GetIndexDataSize());
        if(Positions.GetAllowCPUAccess()||Indices.GetAllowCPUAccess())
            Issues.Add(FString::Printf(TEXT("Selected cooked mesh LOD %d retains CPU-enabled render buffers"),I));
        if(Indices.GetIndexDataSize()!=0)
            Issues.Add(FString::Printf(TEXT("Selected cooked mesh LOD %d still contains CPU index bytes"),I));
        Lods.Add(MakeShared<FJsonValueObject>(L));
    }
    J->SetArrayField(TEXT("lods"),Lods);return J;
}

void ExecuteProbe()
{
    if(bProbeStarted)return;bProbeStarted=true;
    check(IsInGameThread());
    auto Report=MakeShared<FJsonObject>();TArray<FString> Issues;
    TArray<TSharedPtr<FJsonValue>> Packages;
    Report->SetNumberField(TEXT("schema"),1);
    Report->SetStringField(TEXT("scope"),TEXT("Cooked asset-only native decode and baked-mesh local session smoke; not whole-map placement or console parity"));
    Report->SetBoolField(TEXT("editor_build"),WITH_EDITOR!=0);
    Report->SetBoolField(TEXT("requires_cooked_data"),FPlatformProperties::RequiresCookedData());
    Report->SetNumberField(TEXT("worker_stack_bytes"),NativeStackBytes);
    if(WITH_EDITOR)Issues.Add(TEXT("Cooked validation requires an actual non-editor game executable"));
    if(!FPlatformProperties::RequiresCookedData())Issues.Add(TEXT("The executable does not require cooked data"));
    TStrongObjectPtr<USkateProfile> Profile(GetDefault<USkateSettings>()->DefaultProfile.LoadSynchronous());
    PackageEvidence(Profile.Get(),TEXT("default_profile"),Issues,Packages);
    std::shared_ptr<const GameplayResourceSource> Source;
    FProbeTuning Tuning;FFloorFace Floor;
    TStrongObjectPtr<USkateRuntimeAsset> Asset;
    TArray<TStrongObjectPtr<USkateCollisionAsset>> CatalogPins;
    TArray<USkateCollisionAsset*> Catalogs;
    TStrongObjectPtr<UStaticMesh> SelectedMesh;
    int32 MeshCount=0,ComplexCount=0;
    if(Profile.IsValid())
    {
        TArray<FString> ProfileIssues;Profile->ValidateProfile(ProfileIssues);Issues.Append(ProfileIssues);
        Tuning={NativeText(Profile->GetDifficultyPreset()),Profile->TruckTightness,Profile->PopHeightScale,
            Profile->AirSpinScale,Profile->PushSpeedScale,Profile->PushPowerScale,Profile->VertAssist};
        Asset.Reset(Profile->RuntimeData.LoadSynchronous());
        PackageEvidence(Asset.Get(),TEXT("runtime_data"),Issues,Packages);
        if(Asset.IsValid())
        {
            const auto Validation=Asset->Validate(false);Issues.Append(Validation.Issues);
            Report->SetNumberField(TEXT("resource_records"),Validation.RecordCount);
            Report->SetNumberField(TEXT("resource_expected_records"),Asset->ExpectedRecordCount);
            Report->SetNumberField(TEXT("resource_clips"),Validation.ClipCount);
            Report->SetNumberField(TEXT("resource_payload_bytes"),static_cast<double>(Validation.PayloadBytes));
            Report->SetStringField(TEXT("resource_manifest_sha256"),Asset->ManifestSha256);
            Report->SetStringField(TEXT("resource_source_identity"),Asset->SourceIdentity);
            FString Error;
            if(!Asset->CreateSnapshot(Source,Error))Issues.Add(TEXT("Immutable asset snapshot: ")+Error);
            if(Validation.RecordCount!=3334)Issues.Add(TEXT("The cooked stock runtime must contain all 3334 records"));
        }
        for(int32 I=0;I<Profile->CollisionDataCatalog.Num();++I)
        {
            auto* Catalog=Profile->CollisionDataCatalog[I].LoadSynchronous();
            PackageEvidence(Catalog,FString::Printf(TEXT("collision_catalog[%d]"),I),Issues,Packages);
            if(!Catalog)continue;
            CatalogPins.Emplace(Catalog);Catalogs.Add(Catalog);
            TArray<FString> CatalogIssues;Catalog->Validate(CatalogIssues);Issues.Append(CatalogIssues);
            for(const auto& MeshData:Catalog->Meshes)
            {
                auto* Data=MeshData.Get();
                ++MeshCount;
                PackageEvidence(Data,TEXT("baked_mesh"),Issues,Packages);
                if(!Data)continue;
                TStrongObjectPtr<UStaticMesh> Mesh(Data->SourceMesh.LoadSynchronous());
                PackageEvidence(Mesh.Get(),TEXT("source_static_mesh"),Issues,Packages);
                TArray<FString> MeshIssues;
                const bool bValid=Data->Validate(MeshIssues);Issues.Append(MeshIssues);
                if(!bValid||!Mesh.IsValid()||!Mesh->GetBodySetup()
                    ||Mesh->GetBodySetup()->GetCollisionTraceFlag()!=CTF_UseComplexAsSimple||Data->Indices.IsEmpty())continue;
                ++ComplexCount;ConsiderFloor(Data,Mesh.Get(),Floor);
                if(Floor.Mesh==Mesh.Get())SelectedMesh.Reset(Mesh.Get());
            }
        }
    }
    Report->SetNumberField(TEXT("collision_catalogs"),Catalogs.Num());
    Report->SetNumberField(TEXT("baked_meshes"),MeshCount);
    Report->SetNumberField(TEXT("nonempty_complex_meshes"),ComplexCount);
    if(Catalogs.IsEmpty())Issues.Add(TEXT("The profile supplied no cooked collision catalog"));
    GameplayWorldSnapshot World;
    if(!Floor.Data)Issues.Add(TEXT("No actual upward horizontal triangle was found in baked complex collision"));
    else
    {
        // Wait for normal mesh resource initialization before observing retained
        // CPU bytes. Do not discard or mutate a render resource to force success.
        FlushRenderingCommands();
        Report->SetObjectField(TEXT("selected_render_buffer_status"),RenderBufferEvidence(*SelectedMesh,Issues));
        auto Face=MakeShared<FJsonObject>();
        Face->SetStringField(TEXT("mesh_data"),Floor.Data->GetPathName());
        Face->SetStringField(TEXT("source_mesh"),Floor.Mesh->GetPathName());
        Face->SetStringField(TEXT("geometry_hash"),Floor.Data->GeometryHash);
        Face->SetNumberField(TEXT("source_triangle"),Floor.Triangle);
        Face->SetNumberField(TEXT("source_positions"),Floor.Data->Positions.Num());
        Face->SetNumberField(TEXT("source_indices"),Floor.Data->Indices.Num());
        Face->SetNumberField(TEXT("area_cm2"),Floor.AreaCm2);
        Face->SetNumberField(TEXT("centroid_clearance_cm"),Floor.ClearanceCm);
        Face->SetArrayField(TEXT("source_centroid_cm"),VectorJson(Floor.Centre));
        Face->SetArrayField(TEXT("source_normal"),VectorJson(Floor.Normal));
        Face->SetArrayField(TEXT("local_translation_cm"),VectorJson(-Floor.Centre));
        Face->SetStringField(TEXT("placement"),TEXT("Source local geometry translated by its actual floor centroid; no added floor or world actor transform"));
        Report->SetObjectField(TEXT("baked_support_face"),Face);
        if(Floor.ClearanceCm<500)Issues.Add(TEXT("The actual floor face has less than 5 m of centroid support clearance"));
        FSkateCollisionSnapshot Collision;
        // Bounding region is centered on the measured face. The entire selected
        // baked mesh is queried inside 100 m; no synthetic support is appended.
        Collision.Region=FBox(FVector(-10000,-10000,-10000),FVector(10000,10000,10000));
        Collision.AddSurface(*Floor.Data,FTransform(FQuat::Identity,-Floor.Centre),nullptr,
            MakeArrayView(Catalogs));
        Report->SetNumberField(TEXT("snapshot_triangles"),Collision.Num());
        if(Collision.Full())Issues.Add(TEXT("The actual baked collision exceeded the snapshot triangle budget"));
        if(Collision.Num()==0)Issues.Add(TEXT("The actual baked collision produced an empty local snapshot"));
        World=SkateNativeCollisionSnapshot(Collision);
        Report->SetNumberField(TEXT("snapshot_material_entries"),World.triangle_materials.size());
        Report->SetNumberField(TEXT("snapshot_surface_entries"),World.triangle_surfaces.size());
        if(!World.triangle_materials.empty())Issues.Add(TEXT("The component-free baked probe unexpectedly overrode stock floor materials"));
        bool bSupportTriangle=false;
        for(const auto& T:World.triangles)
        {
            const Vec3 A=T[0],B=T[1],C=T[2];
            const float Y=(A.y+B.y+C.y)/3.0f;
            // Find the selected triangle after the production f32/coordinate
            // transport, rather than assuming it survived snapshot conversion.
            const float X=(A.x+B.x+C.x)/3.0f,Z=(A.z+B.z+C.z)/3.0f;
            const float Up=(B.z-A.z)*(C.x-A.x)-(B.x-A.x)*(C.z-A.z);
            if(std::abs(X)<0.001f&&std::abs(Y)<0.001f&&std::abs(Z)<0.001f&&Up>0)bSupportTriangle=true;
        }
        Report->SetBoolField(TEXT("selected_floor_survived_native_snapshot"),bSupportTriangle);
        if(!bSupportTriangle)Issues.Add(TEXT("The chosen upward floor triangle did not survive the actual native snapshot transport"));
    }
    TArray<TSharedPtr<FJsonValue>> Stances;
    if(Source)
    {
        // All UObject/asset reads ended above. This lambda owns only plain
        // immutable resources, collision coordinates, and copied scalar tuning.
        auto Native=AsyncThread([Source=MoveTemp(Source),World=MoveTemp(World),Tuning=MoveTemp(Tuning)]() mutable
            {return RunNative(MoveTemp(Source),MoveTemp(World),MoveTemp(Tuning));},NativeStackBytes).Get();
        Issues.Append(Native.Issues);
        Report->SetBoolField(TEXT("float_environment_ready"),Native.bFloatEnvironment);
        Report->SetBoolField(TEXT("native_resources_loaded"),Native.bLoaded);
        Report->SetNumberField(TEXT("decoded_clip_paths"),Native.ClipCount);
        for(const auto& Stance:Native.Stances)
        {Issues.Append(Stance.Issues);Stances.Add(MakeShared<FJsonValueObject>(StanceJson(Stance)));}
        if(Native.Stances.Num()!=2)Issues.Add(TEXT("Both actual stance sessions did not execute"));
    }
    else
    {
        Report->SetBoolField(TEXT("native_resources_loaded"),false);
        Issues.Add(TEXT("Native decoding and actual session probe blocked by a missing asset snapshot"));
    }
    Report->SetArrayField(TEXT("stances"),Stances);Report->SetArrayField(TEXT("packages"),Packages);
    Report->SetArrayField(TEXT("issues"),Strings(Issues));Report->SetBoolField(TEXT("valid"),Issues.IsEmpty());
    FString Json;const auto Writer=TJsonWriterFactory<>::Create(&Json);
    const bool bSerialized=FJsonSerializer::Serialize(Report,Writer);
    const FString Directory=FPaths::GetPath(ProbeReportPath);
    if(!Directory.IsEmpty())IFileManager::Get().MakeDirectory(*Directory,true);
    const bool bWritten=bSerialized&&FFileHelper::SaveStringToFile(Json,*ProbeReportPath,
        FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    if(!bWritten)
    {
        UE_LOG(LogTemp,Error,TEXT("Skate cooked probe could not write report: %s"),*ProbeReportPath);
    }
    else
    {
        UE_LOG(LogTemp,Display,TEXT("Skate cooked probe: %s (%d issues): %s"),
            Issues.IsEmpty()?TEXT("PASS"):TEXT("FAIL"),Issues.Num(),*ProbeReportPath);
    }
    FPlatformMisc::RequestExitWithStatus(false,bWritten?(Issues.IsEmpty()?0:1):2,TEXT("SkateCookedProbe"));
}
}

void RegisterSkateCookedProbe()
{
    if(ProbeDelegate.IsValid())return;
    if(!FParse::Value(FCommandLine::Get(),TEXT("SkateCookedProbe="),ProbeReportPath)||ProbeReportPath.IsEmpty())return;
    bProbeStarted=false;
    ProbeDelegate=FCoreDelegates::OnFEngineLoopInitComplete.AddStatic(&ExecuteProbe);
}

void UnregisterSkateCookedProbe()
{
    if(ProbeDelegate.IsValid())FCoreDelegates::OnFEngineLoopInitComplete.Remove(ProbeDelegate);
    ProbeDelegate.Reset();ProbeReportPath.Reset();
}
