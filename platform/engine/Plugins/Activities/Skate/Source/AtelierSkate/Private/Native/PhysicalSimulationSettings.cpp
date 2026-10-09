#include "PhysicalSimulationSettings.h"
#include <algorithm>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float DecodeFloat(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
bool EqualAscii(std::string_view a,std::string_view b)
{
    if(a.size()!=b.size())return false;
    const auto lower=[](unsigned char c){return c>='A'&&c<='Z'?static_cast<unsigned char>(c+32):c;};
    for(std::size_t i=0;i<a.size();++i)if(lower(a[i])!=lower(b[i]))return false;return true;
}
class Fields
{
    const SettingsDatabase& data;std::string& error;
    const SettingValue* Field(std::string_view category,std::string_view name)
    {
        if(!error.empty())return nullptr;if(const auto* f=data.Field(category,"default",name))return f;
        const auto class_id=NameId(category);std::string current="default";
        for(std::size_t hop=0;hop<=data.Records().size();++hop)
        {
            const auto key_id=NameId(current);const auto found=std::find_if(data.Records().begin(),data.Records().end(),[&](const SettingRecord& r){return r.category_id==class_id&&r.key_id==key_id;});
            if(found==data.Records().end()){error="Missing stock collection "+std::string(category)+"/"+current;return nullptr;}
            if(found->parent.empty()){error="Missing stock field "+std::string(category)+"/default/"+std::string(name);return nullptr;}current=found->parent;
        }
        error="Cyclic stock collection inheritance "+std::string(category)+"/default";return nullptr;
    }
public:
    Fields(const SettingsDatabase& d,std::string& e):data(d),error(e){}
    float Scalar(std::string_view category,std::string_view name)
    {
        const auto* f=Field(category,name);if(!f)return 0;
        if(f->type!="EA::Reflection::Float"){error="Expected float at "+std::string(category)+"/default/"+std::string(name);return 0;}
        const auto w=Words<1>(category,name);if(!error.empty())return 0;const float value=DecodeFloat(w[0]);
        if(!std::isfinite(value)){error="Non-finite stock float "+std::string(category)+"/default/"+std::string(name);return 0;}return value;
    }
    std::int32_t Integer(std::string_view category,std::string_view name)
    {
        const auto* f=Field(category,name);if(!f)return 0;
        if(f->type!="EA::Reflection::Int32"&&f->type!="EA::Reflection::UInt32"){error="Expected integer at "+std::string(category)+"/default/"+std::string(name);return 0;}
        return static_cast<std::int32_t>(Words<1>(category,name)[0]);
    }
    template<std::size_t N>std::array<std::uint32_t,N> Words(std::string_view category,std::string_view name)
    {
        std::array<std::uint32_t,N> result{};const auto* f=Field(category,name);if(!f)return result;const std::uint32_t* words=nullptr;
        if(!f->Words(N,words)){error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(f->byte_count*2)+" bytes of hex";return result;}
        std::copy_n(words,N,result.begin());return result;
    }
    Vec4 Control(std::string_view name){const auto w=Words<4>("physics_reckoning",name);return {DecodeFloat(w[0]),DecodeFloat(w[1]),DecodeFloat(w[2]),DecodeFloat(w[3])};}
    PointGraph<8> Graph(std::string_view category,std::string_view name,bool negative=false)
    {
        PointGraph<8> out{};
        if(negative){const auto w=Words<20>(category,name);for(unsigned i=0;i<8;++i){out.x[i]=DecodeFloat(w[4+i]);out.y[i]=DecodeFloat(w[12+i]);}}
        else{const auto w=Words<16>(category,name);for(unsigned i=0;i<8;++i){out.x[i]=DecodeFloat(w[i]);out.y[i]=DecodeFloat(w[8+i]);}}return out;
    }
};
}
std::optional<PhysicalRidingSettings> PhysicalRidingSettings::Load(const SettingsDatabase& data,std::string& error)
{
    error.clear();Fields f(data,error);const auto scalar=[&](std::string_view n){return f.Scalar("physics_reckoning",n);};
    const auto deck_curve=f.Graph("physics_reckoning","DeckAngleUsageVsSpeed",true);
    PhysicalRidingSettings s;
    s.orientation={f.Control("GroundNormalSmoothing"),f.Control("UpVectorSmoothingSlow"),f.Control("UpVectorSmoothingFast"),
        f.Graph("physics_reckoning","DynamicUpVsGroundY"),f.Graph("physics_reckoning","GroundVectorBlendGraph"),deck_curve,
        f.Graph("physics_reckoning","UpVectorSmoothingVsSpeed"),f.Graph("physics_reckoning","UpVectorMaxDeltaVsSpeed"),scalar("GroundVMaxBlendDelta"),scalar("UpVectorMaxAcceleration"),
        scalar("UpVectAntiWobbleDamping"),scalar("ExtraSideDamping"),f.Integer("physics_reckoning","MinWheelsToUseGroundVector")};
    s.speed={f.Graph("physics_heading","TurnTorqueVsSpeed"),f.Graph("physics_heading","TurnTorqueVsSlope"),f.Scalar("physics_heading","HeadingAdjustMaxSpeed")};
    s.tilt_vs_rotation=f.Graph("physics_reckoning","TiltVsRotGround");s.tilt_vs_slope=f.Graph("physics_reckoning","TiltVsSlopeGround");s.maximum_ground_angle=scalar("MaxAllowedGroundNormalFromUp");
    if(!error.empty())return std::nullopt;return s;
}
std::optional<PhysicalSimulationSettings> PhysicalSimulationSettings::Load(const SettingsDatabase& data,const PhysicsSkeleton& physical,const AnimationRig& rig,std::string& error)
{
    error.clear();const auto board=BoardPhysicsSettings::Load(data,error);if(!board)return std::nullopt;
    const auto riding=PhysicalRidingSettings::Load(data,error);if(!riding)return std::nullopt;
    if(physical.bones.size()!=24){error="Stock skater physics skeleton must contain24 parts";return std::nullopt;}
    PhysicalSimulationSettings s;s.board=*board;s.riding=*riding;s.physical=physical;
    for(const auto& bone:rig.bones)s.hierarchy_parents.push_back(bone.parent);
    for(std::size_t part=0;part<24;++part)
    {
        const auto& bone=physical.bones[part];const auto found=std::find_if(rig.bones.begin(),rig.bones.end(),[&](const AnimationBone& b){return EqualAscii(b.name,bone.name);});
        if(found==rig.bones.end()){error="Stock physics bone "+bone.name+" is absent from the animation hierarchy";return std::nullopt;}
        s.bone_indices[part]=static_cast<std::size_t>(found-rig.bones.begin());const auto t=bone.Translation();s.physics_frames[part]=PhysicsBoneFrame(bone.Rotation(),{t[0],t[1],t[2],0.0f});
    }
    const auto collision=LoadSkeletonCollisionSettings(data,physical,error);if(!collision)return std::nullopt;s.collision=*collision;
    const auto feedback=LoadSkeletonFeedbackSettings(data,*collision,error);if(!feedback)return std::nullopt;s.feedback=*feedback;
    const auto possession=LoadBoardPossessionSettings(data,error);if(!possession)return std::nullopt;s.possession=*possession;
    const auto live=LoadBoardPossessionLiveState(data,*board,error);if(!live)return std::nullopt;s.possession_live=*live;return s;
}
AffineTransform PhysicalSimulationSettings::Spawn(Vec3 anchor) const
{
    AffineTransform spawn;spawn.basis.columns={{{1,0,0},{0,1,0},{0,0,1}}};
    spawn.translation={anchor.x,anchor.y+board.collision.wheel_radius-board.authored[0].translation.y,anchor.z};return spawn;
}
}
