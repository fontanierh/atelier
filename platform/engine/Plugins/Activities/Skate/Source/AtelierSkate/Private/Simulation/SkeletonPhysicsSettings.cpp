#include "SkeletonPhysicsSettings.h"
#include <algorithm>
#include <cstring>
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
class Fields
{
    const SettingsDatabase& data;
    std::string& error;
    const SettingValue* Field(std::string_view category,std::string_view key,std::string_view name)
    {
        if(!error.empty())return nullptr;if(const auto* f=data.Field(category,key,name))return f;
        const auto class_id=NameId(category);auto current=std::string(key);
        for(std::size_t hop=0;hop<=data.Records().size();++hop)
        {
            const auto key_id=NameId(current);const auto found=std::find_if(data.Records().begin(),data.Records().end(),[&](const SettingRecord& r){return r.category_id==class_id && r.key_id==key_id;});
            if(found==data.Records().end()){error="Missing stock collection "+std::string(category)+"/"+current;return nullptr;}
            if(found->parent.empty()){error="Missing stock field "+Path(category,key,name);return nullptr;}current=found->parent;
        }
        error="Cyclic stock collection inheritance "+std::string(category)+"/"+std::string(key);return nullptr;
    }
    static std::string Path(std::string_view category,std::string_view key,std::string_view name)
    {return std::string(category)+"/"+std::string(key)+"/"+std::string(name);}
    template<std::size_t N>std::array<std::uint32_t,N> Decode(const SettingValue* f)
    {
        std::array<std::uint32_t,N> out{};if(!f)return out;const std::uint32_t* words=nullptr;
        if(!f->Words(N,words)){error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(f->byte_count*2)+" bytes of hex";return out;}
        std::copy_n(words,N,out.begin());return out;
    }
public:
    Fields(const SettingsDatabase& d,std::string& e):data(d),error(e){}
    float Scalar(std::string_view category,std::string_view key,std::string_view name)
    {
        const auto* f=Field(category,key,name);if(!f)return 0;
        if(f->type!="EA::Reflection::Float"){error="Expected float at "+Path(category,key,name);return 0;}
        const auto words=Decode<1>(f);if(!error.empty())return 0;const float value=Float(words[0]);
        if(!std::isfinite(value)){error="Non-finite stock float "+Path(category,key,name);return 0;}return value;
    }
    float Scalar(std::string_view category,std::string_view name){return Scalar(category,"default",name);}
    std::uint32_t Integer(std::string_view category,std::string_view name)
    {
        const auto* f=Field(category,"default",name);if(!f)return 0;
        if(f->type!="EA::Reflection::Int32" && f->type!="EA::Reflection::UInt32"){error="Expected integer at "+Path(category,"default",name);return 0;}
        return Decode<1>(f)[0];
    }
    bool Boolean(std::string_view category,std::string_view name)
    {
        const auto* f=Field(category,"default",name);if(!f)return false;
        if(f->type!="EA::Reflection::Bool"){error="Expected boolean at "+Path(category,"default",name);return false;}
        const auto v=f->Boolean();if(!v){error="Invalid stock boolean "+Path(category,"default",name);return false;}return *v;
    }
    template<std::size_t N>std::array<std::uint32_t,N> Words(std::string_view category,std::string_view key,std::string_view name)
    {return Decode<N>(Field(category,key,name));}
    template<std::size_t N>std::array<std::uint32_t,N> Words(std::string_view category,std::string_view name)
    {return Words<N>(category,"default",name);}
    Vec4 Vector(std::string_view category,std::string_view key,std::string_view name)
    {const auto w=Words<4>(category,key,name);return {Float(w[0]),Float(w[1]),Float(w[2]),Float(w[3])};}
};
BoneDriveSettings ReadBoneDriveSettings(Fields& f)
{
    const auto scalar=[&](std::string_view name){return f.Scalar("physics_skeleton_drives",name);};
    const auto animation=[&](std::string_view key){return AnimationDriveSettings{f.Scalar("animation_drives",key,"LinearStrMin"),f.Scalar("animation_drives",key,"LinearDispMin"),f.Scalar("animation_drives",key,"AngularStrMin"),f.Scalar("animation_drives",key,"AngularDispMin")};};
    return {{{animation("local"),animation("root")}},scalar("CollisionSoftDisp"),scalar("CollisionSoftStrength"),scalar("RagdollSoftDisp"),scalar("RagdollSoftStrength"),
        {{scalar("Hash_138976EAF99DF926"),scalar("Hash_C313093118C7A83F")},{scalar("Hash_1E6BDF62043784FC"),scalar("Hash_BD3E4F132848A588")},{scalar("Hash_D7652B4B19BB4747"),scalar("Hash_C4B564DFD233CF04")}},
        {{scalar("Hash_14A2DDDD0A35C267"),scalar("Hash_24D5AA7F214A901C")},{scalar("Hash_6C6CCD16A0A438AD"),scalar("Hash_7379F8AB250BF611")},{scalar("Hash_28446A9E25DCC04C"),scalar("Hash_B59D493B3DB372C8")}},scalar("Hash_E1B89BB09D725EEC")};
}
}
std::optional<SkeletonBodyDefinition> LoadSkeletonBodyDefinition(const SettingsDatabase& data,const PhysicsSkeleton& skeleton,
    std::optional<std::string_view> hat_collection,std::string& error)
{
    error.clear();if(skeleton.bones.size()!=24){error="Physical skeleton requires24 bone records";return std::nullopt;}Fields f(data,error);
    std::array<Vec3,24> sizes;std::array<BoneSettings,24> bones;
    for(std::size_t i=0;i<24;++i)
    {
        const auto size=skeleton.bones[i].Size();sizes[i]={size[0],size[1],size[2]};const auto w=f.Words<6>("physics_skeleton_bones","PART_"+skeleton.bones[i].name);if(!error.empty())return std::nullopt;
        bones[i]={Float(w[0]),Float(w[1]),w[2]>>24!=0,((w[2]>>16)&255u)!=0,w[3],Float(w[4]),w[5]};
    }
    const SkeletonBodySettings settings{f.Scalar("physics_skeleton","MassOfSkeleton"),f.Scalar("physics_skeleton","SkateRootCapsuleRadius"),f.Scalar("physics_skeleton","SkateRootCapsuleLength"),
        f.Scalar("physics_skeleton_bones","CapsuleRadiusScalar"),f.Scalar("physics_skeleton","CapsuleLengthScalar"),f.Scalar("physics_wipeout","RagdollInvMassFactor"),f.Integer("animation","InertiaMultiplyType"),f.Scalar("animation","InertiaMultFactor")};
    if(!error.empty())return std::nullopt;std::optional<HatGeometry> hat;
    if(hat_collection)
    {
        const float radius=f.Scalar("physics_hat",*hat_collection,"Hash_372DF5DB27AF1C79"),thickness=f.Scalar("physics_hat",*hat_collection,"Thickness");
        const auto orientation=f.Vector("physics_hat",*hat_collection,"OrientationOffset"),position=f.Vector("physics_hat",*hat_collection,"PosOffset");
        if(!error.empty())return std::nullopt;hat=HatGeometry::FromOffsets(radius,thickness,{orientation[0],orientation[1],orientation[2]},{position[0],position[1],position[2]});
    }
    return SkeletonBodyDefinition::Build(sizes,bones,settings,hat,error);
}
std::optional<SkeletonBody> LoadSkeletonBody(const SettingsDatabase& data,const PhysicsSkeleton& skeleton,
    const std::array<Mat4,24>& mapped,Mat4 spawn,SimulationStep simulation,std::optional<std::string_view> hat,std::string& error)
{auto definition=LoadSkeletonBodyDefinition(data,skeleton,hat,error);if(!definition)return std::nullopt;return SkeletonBody(std::move(*definition),mapped,spawn,simulation);}
std::optional<SkeletonCollisionSettings> LoadSkeletonCollisionSettings(const SettingsDatabase& data,const PhysicsSkeleton& skeleton,std::string& error)
{
    error.clear();if(skeleton.bones.size()!=24){error="Skeleton collision requires24 bone records";return std::nullopt;}Fields f(data,error);std::array<bool,24> compliant{};std::array<float,24> priority{};compliant[0]=true;
    for(std::size_t i=1;i<24;++i){const auto w=f.Words<9>("physics_skeleton_drives","PART_"+skeleton.bones[i].name);if(!error.empty())return std::nullopt;compliant[i]=w[7]>>24!=0;priority[i]=Float(w[8]);}
    const float friction=f.Scalar("physics_skeleton","FrictionNormal");const bool enabled=f.Boolean("physics_skeleton","EnableCollision");const float restitution=f.Scalar("physics_skeleton","RestitutionNormal"),effect=f.Scalar("physics_skeleton","CollisionEffectTime");
    if(!error.empty())return std::nullopt;return SkeletonCollisionSettings{enabled,{friction,friction,restitution},compliant,priority,effect};
}
std::optional<SkeletonFeedbackSettings> LoadSkeletonFeedbackSettings(const SettingsDatabase& data,SkeletonCollisionSettings body,std::string& error)
{
    error.clear();Fields f(data,error);const SkeletonFeedbackSettings settings{body,f.Scalar("physics_skeleton","SmallObjectMassThreshold"),f.Scalar("physics_collision","GroundPlaneMaxDist"),f.Scalar("physics_collision","GroundPlaneMaxAngle"),
        f.Scalar("physics_collision","SkaterSkeletonScalar"),f.Scalar("physics_collision","AISkeletonScalar"),f.Vector("physics_collision","default","GroinLocalOffset"),f.Vector("physics_collision","default","FaceLocalOffset"),f.Scalar("physics_collision","GroinRadius"),f.Scalar("physics_collision","FaceRadius")};
    if(!error.empty())return std::nullopt;return settings;
}
std::optional<BoneDriveSettings> LoadBoneDriveSettings(const SettingsDatabase& data,std::string& error)
{error.clear();Fields f(data,error);const auto settings=ReadBoneDriveSettings(f);if(!error.empty())return std::nullopt;return settings;}
std::optional<SkeletonJoints> LoadSkeletonJoints(const SettingsDatabase& data,const PhysicsSkeleton& skeleton,
    const std::vector<Mat4>& hierarchy,const std::vector<std::int32_t>& hierarchy_parents,const std::array<std::size_t,24>& indices,std::string& error)
{
    error.clear();if(hierarchy_parents.size()!=hierarchy.size() || std::any_of(indices.begin(),indices.end(),[&](std::size_t i){return i>=hierarchy.size();}))
    {error="Physical joint hierarchy differs from initial rig pose";return std::nullopt;}
    if(skeleton.bones.size()!=24){error="Physical joints require24 bone records";return std::nullopt;}
    std::array<Mat4,24> initial;std::array<std::optional<std::size_t>,24> parents{};
    for(std::size_t i=0;i<24;++i)initial[i]=hierarchy[indices[i]];
    for(std::size_t child=0;child<24;++child)
    {
        auto parent=hierarchy_parents[indices[child]];std::size_t visited=0;
        while(parent!=-1)
        {
            if(parent<0){error="Invalid animation parent index";return std::nullopt;}
            const auto index=static_cast<std::size_t>(parent);if(index>=hierarchy_parents.size() || visited>=hierarchy_parents.size()){error="Invalid or cyclic animation hierarchy";return std::nullopt;}
            const auto found=std::find(indices.begin(),indices.end(),index);if(found!=indices.end()){parents[child]=static_cast<std::size_t>(found-indices.begin());break;}
            parent=hierarchy_parents[index];++visited;
        }
    }
    std::array<SkeletonJointBone,24> bones;
    for(std::size_t i=0;i<24;++i)
    {
        const auto& bone=skeleton.bones[i];Quat parent,orientation;for(unsigned lane=0;lane<4;++lane){parent[lane]=Float(bone.words[lane]);orientation[lane]=Float(bone.words[4+lane]);}
        const auto t=bone.Translation();bones[i]={parent,orientation,PhysicsBoneFrame(bone.Rotation(),{t[0],t[1],t[2],0}),Float(bone.words[21]),Float(bone.words[20])};
    }
    constexpr std::array<std::string_view,22> names{{"JOINT_NECK_NECK1","JOINT_SPINE3_NECK","JOINT_LEFT_FOREARM_HAND","JOINT_LEFT_ARM_FOREARM","JOINT_LEFT_SHOULDER_ARM","JOINT_SPINE3_LEFT_SHOULDER","JOINT_RIGHT_FOREARM_HAND","JOINT_RIGHT_ARM_FOREARM","JOINT_RIGHT_SHOULDER_ARM","JOINT_SPINE3_RIGHT_SHOULDER","JOINT_SPINE2_SPINE3","JOINT_SPINE1_SPINE2","JOINT_SPINE_SPINE1","JOINT_HIPS_SPINE","JOINT_LEFT_FOOT_TOE_BASE","JOINT_LEFT_LEG_FOOT","JOINT_LEFT_UPLEG_LEG","JOINT_HIPS_LEFT_LEG","JOINT_RIGHT_FOOT_TOE_BASE","JOINT_RIGHT_LEG_FOOT","JOINT_RIGHT_UPLEG_LEG","JOINT_HIPS_RIGHT_LEG"}};
    Fields f(data,error);std::array<SkeletonJointBoneSettings,22> settings;
    for(std::size_t i=0;i<22;++i){const auto w=f.Words<5>("physics_skeleton_joints",names[i]);if(!error.empty())return std::nullopt;settings[i]={w[0]>>24!=0,Float(w[1]),Float(w[2]),Float(w[3]),Float(w[4])};}
    const SkeletonJointSettings global{f.Vector("physics_skeleton","default","DisplacementLimit"),f.Scalar("physics_skeleton","TwistDisplacementLimit"),f.Scalar("physics_skeleton","SwingDisplacementLimit"),f.Boolean("physics_skeleton_joints","EnforceSwingFree"),f.Boolean("physics_skeleton_joints","EnforceTwistFree")};
    if(!error.empty())return std::nullopt;return SkeletonJoints::FromDefinition(initial,parents,bones,settings,global,error);
}
std::optional<SkeletonDrives> LoadSkeletonDrives(const SettingsDatabase& data,const PhysicsSkeleton& skeleton,
    const std::vector<Mat4>& hierarchy,const std::array<std::size_t,24>& indices,const std::array<Mat4,24>& mapped,const SkeletonJoints& joints,
    Mat4 alignment,Mat4 spawn,SimulationStep simulation,std::string& error)
{
    error.clear();if(std::any_of(indices.begin(),indices.end(),[&](std::size_t i){return i>=hierarchy.size();})){error="Skeleton drive initial hierarchy has missing bones";return std::nullopt;}
    if(skeleton.bones.size()!=24){error="Skeleton drives require24 bone records";return std::nullopt;}std::array<std::optional<std::size_t>,24> parents{};
    for(const auto& joint:joints.records){if(joint.child>=24)std::abort();parents[joint.child]=joint.parent;}
    std::array<Mat4,24> initial;for(std::size_t i=0;i<24;++i)initial[i]=hierarchy[indices[i]];
    std::array<std::array<float,2>,24> strength{};Fields f(data,error);const float scalar=f.Scalar("physics_skeleton_drives","CollisionDriveScalar");
    for(std::size_t i=1;i<24;++i){const auto w=f.Words<9>("physics_skeleton_drives","PART_"+skeleton.bones[i].name);if(!error.empty())return std::nullopt;strength[i]={Float(w[5])*scalar,Float(w[6])*scalar};}
    const SkeletonDriveSettings settings{ReadBoneDriveSettings(f),f.Boolean("animation","Use_Drives"),{f.Scalar("animation","DriveStrengthLocal"),f.Scalar("animation","DriveStrengthRootLocal")},strength};
    if(!error.empty())return std::nullopt;return SkeletonDrives::FromDefinition(initial,mapped,parents,alignment,spawn,simulation,settings,error);
}
}
