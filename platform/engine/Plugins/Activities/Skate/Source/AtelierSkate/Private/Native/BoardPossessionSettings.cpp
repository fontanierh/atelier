#include "BoardPossessionSettings.h"
#include <algorithm>
#include <cstring>
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
    PointGraph<8> Curve(std::string_view name)
    {
        PointGraph<8> result{};const auto* f=Field("physics_skatecontroller","default",name);if(!f)return result;
        if(f->type!="Sk8::PointNegGraphData8"){error=std::string(name)+": expected PointNegGraphData8";return result;}
        const auto words=Decode<20>(f);if(!error.empty())return result;
        for(auto w:words)if(!std::isfinite(Float(w))){error=std::string(name)+": nonfinite stock graph";return result;}
        for(unsigned i=0;i<8;++i){result.x[i]=Float(words[4+i]);result.y[i]=Float(words[12+i]);}
        for(unsigned i=1;i<8;++i)if(result.x[i-1]>result.x[i]){error=std::string(name)+": unordered stock knots";return result;}
        return result;
    }
};
}
std::optional<BoardPossessionSettings> LoadBoardPossessionSettings(const SettingsDatabase& data,std::string& error)
{
    error.clear();Fields fields(data,error);const auto scalar=[&](std::string_view name){return fields.Scalar("physics_skatecontroller",name);};
    const BoardPossessionSettings result{scalar("MaxDistance"),scalar("DistanceToHideSkateboard"),scalar("DistanceForBoardReturn"),scalar("DistanceForMountedReturn"),scalar("MinTimeToRetrieveBoardWhileMounting"),
        fields.Curve("RetrievalTimeVsDist"),fields.Curve("RetrievalSpeedCurve"),scalar("ThrownSkateboardLaunchPitch"),fields.Curve("ThrownSkateboardVelocity"),
        scalar("ThrownSkateboardPitchTarget"),scalar("ThrownSkateboardPitchScalar"),scalar("ThrownSkateboardRollScalar"),scalar("ThrownSkateboardYawScalar")};
    if(!error.empty())return std::nullopt;return result;
}
std::optional<float> BoardPossessionStandardAngularDrag(const SettingsDatabase& data,std::string& error)
{
    error.clear();Fields fields(data,error);const float authored=fields.Scalar("physicsdeck","DeckAngularDrag");if(!error.empty())return std::nullopt;
    return authored*Float(0x426fffff);
}
std::optional<BoardPossessionLiveState> LoadBoardPossessionLiveState(const SettingsDatabase& data,const BoardPhysicsSettings& physics,std::string& error)
{
    error.clear();Fields fields(data,error);const float friction=fields.Scalar("physics_wipeout","SkateboardFriction");if(!error.empty())return std::nullopt;
    BoardPossessionLiveState live;live.volumes.trucks=physics.collision.truck_collisions;
    for(const auto& child:physics.collision.deck_geometry.children)live.volumes.deck_children.push_back(child.collision_enabled);
    live.standard_materials={physics.standard_wheel_material,physics.collision.truck_material,physics.collision.deck_material};
    const float restitution=fields.Scalar("physics_wipeout","SkateboardRestitution");if(!error.empty())return std::nullopt;live.released_material={friction,friction,restitution};
    const auto drag=BoardPossessionStandardAngularDrag(data,error);if(!drag)return std::nullopt;live.standard_drag=*drag;return live;
}
}
