#include "GraphMotionScoreOperations.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
std::int32_t Signed(std::uint32_t word) {std::int32_t value;std::memcpy(&value,&word,4);return value;}
std::int32_t SaturatingInt(float value)
{if (std::isnan(value)) return 0;if (value>=2147483648.0f) return std::numeric_limits<std::int32_t>::max();if (value<=-2147483648.0f) return std::numeric_limits<std::int32_t>::min();return std::int32_t(value);}
std::string NormalizePath(std::string_view path) {std::string out(path);std::replace(out.begin(),out.end(),'/','\\');return out;}
std::uint32_t Djb2(std::string_view path) {std::uint32_t hash=5381;for (unsigned char c:path) hash=hash*33u+c;return hash;}
}
void MotionGraphScorePacket::Set(std::uint32_t value)
{
    constexpr std::array<std::uint32_t,10> bits{{31,30,29,28,27,26,23,21,22,20}};
    if (value>=bits.size()) return;flags|=1u<<bits[value];if (value!=2 && value!=3) name=value;
}
std::uint32_t MotionGraphMovingObjectRegistry::Register(std::string_view path)
{auto normalized=NormalizePath(path);const auto hash=Djb2(normalized);objects[hash]=std::move(normalized);return hash;}
bool MotionGraphMovingObjectRegistry::Begin(std::string_view path,std::string& error)
{const auto hash=Djb2(NormalizePath(path));if (objects.find(hash)==objects.end()) {error="MovingObject resource is not registered: "+std::string(path);return false;}active=hash;error.clear();return true;}
bool MotionGraphMovingObjectRegistry::Update(std::string_view path,bool& enabled,std::string& error) const
{const auto hash=Djb2(NormalizePath(path));enabled=false;if (objects.find(hash)==objects.end()) {error="MovingObject update references unknown resource: "+std::string(path);return false;}enabled=active==hash;error.clear();return true;}
std::string_view SelectGraphMotionGrabScore(std::string_view base,const std::array<std::optional<std::string>,4>& d,float x,float y)
{
    if (std::sqrt(x*x+y*y)<=.5f) return base;
    // The pinned host uses standard f32 atan2/rem_euclid here. The
    // simulation's trig approximations belong to other operations and must not leak.
    auto angle=std::fmod(std::atan2(y,x),Float(0x40c90fdb));if (angle<0) angle+=Float(0x40c90fdb);
    const std::array<std::pair<float,float>,4> windows{{
        {d[3]?44.0f:359.0f,d[1]?134.0f:181.0f}, {d[0]?44.0f:89.0f,d[2]?226.0f:271.0f},
        {d[1]?224.0f:179.0f,d[3]?316.0f:1.0f}, {d[2]?314.0f:269.0f,d[0]?46.0f:91.0f}}};
    const auto radians=Float(0x40490fdb)/180.0f;
    for (std::size_t i=0;i<4;++i)
    {const auto start=windows[i].first*radians,end=windows[i].second*radians;
        const bool inside=end<start?angle>=start || angle<=end:angle>=start && angle<=end;if (inside && d[i]) return *d[i];}
    return base;
}
bool ParseGraphMotionScoreOperation(const GraphAttributes& a,GraphMotionScoreOperation& output,bool& recognized,std::string& error)
{
    GraphMotionScoreOperation op;const auto raw_name=a.Text("name");recognized=false;error.clear();if (!raw_name) {error="MotionGraph operation has no name";return false;}
    const auto raw=*raw_name;const auto name=TrimMotionGraphName(raw);using K=GraphMotionScoreOperation::Kind;recognized=true;
    const auto encoded=[&](std::string_view field){return EncodeAnimationName(a.Text(field).value_or(""));};
    if (name=="ScoringTrick") {const auto trick=a.Text("trick");if (!trick) {error="ScoringTrick requires authored trick";return false;}op.kind=K::ScoringTrick;op.name=EncodeAnimationName(*trick);}
    else if (name=="ScoringGrabs" && raw!=name) {error="Original stock gameplay operation parser has an unreachable raw-name mismatch";return false;}
    else if (raw=="ScoringHandPlants" || raw=="ScoringGrabs")
    {
        op.kind=raw=="ScoringHandPlants"?K::ScoringHandPlants:K::ScoringGrabs;op.base=a.Text(raw=="ScoringHandPlants"?"handplantname":"grabName").value_or("");
        constexpr std::array<std::string_view,4> fields{{"up","left","down","right"}};for (std::size_t i=0;i<4;++i) if (const auto v=a.Text(fields[i])) op.directions[i]=std::string(*v);
        if (raw=="ScoringHandPlants") op.intents={std::string(a.Text("intentX").value_or("")),std::string(a.Text("intentY").value_or(""))};
        else {const auto x=a.Text("intentX"),y=a.Text("intentY");op.intents={std::string((x?x:a.Text("angle")).value_or("")),std::string((y?y:a.Text("magnitude")).value_or(""))};op.polar=!x;op.invert_y=a.BooleanByte("invertY",0)!=0;}
    }
    else if (raw=="SetScoreAugmentation")
    {
        op.kind=K::ScoreAugmentation;const auto decode=[&](std::string_view text,std::uint32_t& value)
        {const std::array<std::string_view,10> names{{"FSPowerslide","BSPowerslide","FSRevert","BSRevert","NoseManual","TailManual","Wipeout","Landing","RideIdle","Switching"}};
            for (std::size_t i=0;i<names.size();++i) if (text==names[i]) {value=std::uint32_t(i);return true;}error="Unknown authored score augmentation "+std::string(text);return false;};
        if (!decode(a.Text("augment").value_or(""),op.augmentation[0])) return false;
        if (const auto mirror=a.Text("mirrorAugment"))
        {if (*mirror=="Switching") {error="Native mirrorAugment=Switching has no initialized mirrored value";return false;}if (!decode(*mirror,op.augmentation[1])) return false;}
        else op.augmentation[1]=op.augmentation[0];
    }
    else if (raw=="SetTrickHeight")
    {op.kind=K::TrickHeight;op.name=encoded("from");op.rename=encoded("rename");if (const auto v=a.Get("setToValue")) op.value=Float(v->float_bits);op.manual=a.Get("trickFromManual")!=nullptr;op.grind=a.Get("trickFromGrind")!=nullptr;}
    else if (raw=="SetTrickAttr") {op.kind=K::TrickAttribute;op.name=encoded("trick");}
    else if (name=="TweakProject") op.kind=K::TweakProject;
    else if (raw=="ChooseRandomLanding") {op.kind=K::RandomLanding;op.count=SaturatingInt(Float(a.FloatBits("numlandings",0x3f800000)));}
    else if (raw=="EndShimmy") {op.kind=K::EndShimmy;op.value=Float(a.FloatBits("blendtime",0x3e4ccccd));}
    else if (name=="InitMovingObjects" || name=="MovingObject")
    {if (raw!=name) {error="Original stock gameplay operation parser has an unreachable raw-name mismatch";return false;}
        op.kind=name=="InitMovingObjects"?K::InitMovingObjects:K::MovingObject;
        const auto path=a.Text("path"),object=a.Text("object");op.path=(path?path:object?object:a.Text("nameToFind")).value_or("");}
    else {recognized=false;output=std::move(op);return true;}
    if (op.kind==K::TweakProject && raw!=name) {error="Original stock gameplay operation parser has an unreachable raw-name mismatch";return false;}
    output=std::move(op);return true;
}
bool GraphMotionScoreOperation::Execute(MotionScoreOperationContext c,std::uint8_t phase,std::string& error) const
{
    using K=Kind;error.clear();auto& a=c.animation;
    switch (kind)
    {
    case K::ScoringTrick:if (phase==1) {c.score.trick_names={name,name};c.score.flags|=0x01000000;}break;
    case K::ScoringGrabs:case K::ScoringHandPlants:
        if (phase==1)
        {
            const auto first=a.FilteredIntent(intents[0]).value_or(0),second=a.FilteredIntent(intents[1]).value_or(0);float x=first,y=second;
            if (kind==K::ScoringGrabs && polar) {x=second*std::sin(first);y=second*std::cos(first);if (invert_y) y=-y;}
            const auto selected=SelectGraphMotionGrabScore(base,directions,x,y);const MotionGraphScorePacket::NamedVector value{EncodeAnimationName(selected),{x,y}};
            if (kind==K::ScoringHandPlants) c.score.handplant=value;else c.score.grab=value;
        }break;
    case K::ScoreAugmentation:
        if (phase==1) {if (!c.playback.is_mirrored) {error="Score augmentation requires animation stance";return false;}c.score.Set(augmentation[*c.playback.is_mirrored?1:0]);}break;
    case K::TrickHeight:
        if (phase==0)
        {
            const auto gesture=a.MotionIntent("GestureSpeed").value_or(0);float height;
            if (value) height=*value;else if (const auto v=a.MotionIntent("TrickHeight")) height=*v;
            else {std::optional<AnimationAttribute> attribute;if (!a.LastAttribute(name,attribute,error)) return false;const auto lane=attribute?attribute->payload[0]:std::nullopt;height=lane?Float(*lane):0;
                if (c.trick_height_settings.first) height=c.trick_height_settings.second?VectorMin(height,VectorMax(gesture,0)):gesture;}
            a.EmitPacket(EncodeAnimationName("JumpHeightOverride"),gesture*(manual?.27f:grind?1.0f:.2f));a.SetAttribute({rename,height,true,-1});
        }break;
    case K::TrickAttribute:
        if (phase==0) a.SetConstructionValue(EncodeAnimationName("Trick"),name);
        else if (phase==2)
        {std::optional<AnimationAttribute> attribute;if (!a.LastAttribute(EncodeAnimationName("defaultcyc"),attribute,error)) return false;
            if (attribute) {auto& v=a.tree.construction_values;v.erase(std::remove_if(v.begin(),v.end(),[](const auto& item){return item.first==EncodeAnimationName("Trick");}),v.end());}}break;
    case K::TweakProject:
        if (phase==1)
        {const auto sx=a.FilteredIntent("TweakX"),sy=a.FilteredIntent("TweakY");if (!sx&&!sy) break;auto x=sx.value_or(0),y=sy.value_or(0);const auto total=std::abs(x)+std::abs(y);
            if (total>1) {const auto scale=1.0f/total;x*=scale;y*=scale;}a.SetAttribute({EncodeAnimationName("tweak_x"),x,false,-1});a.SetAttribute({EncodeAnimationName("tweak_y"),y,false,-1});}break;
    case K::RandomLanding:
        if (phase==0) {if (count<=0) {error="ChooseRandomLanding requires numlandings > 0";return false;}
            const auto raw=c.random.Next();const auto wrapped_abs=Signed(Signed(raw)<0?0u-raw:raw);const auto selected=std::int32_t(std::int64_t(wrapped_abs)%count);
            a.SetConstructionValue(EncodeAnimationName("Random"),EncodeAnimationName(std::to_string(selected)));}
        else if (phase==2) {auto& v=a.tree.construction_values;v.erase(std::remove_if(v.begin(),v.end(),[](const auto& item){return item.first==EncodeAnimationName("Random");}),v.end());}break;
    case K::EndShimmy:if (phase==0) for (auto channel:{"SKCH_2H_SHIMMY_LEFT_CHANNEL","SKCH_2H_SHIMMY_RIGHT_CHANNEL"}) a.channels.EndWith(channel,value.value_or(0),false);break;
    case K::InitMovingObjects:if (phase==0) c.moving_objects.Register(path);break;
    case K::MovingObject:
        if (phase==0) return c.moving_objects.Begin(path,error);
        if (phase==1) {bool active;if (!c.moving_objects.Update(path,active,error)) return false;if (!active) {error="MovingObject is not active: "+path;return false;}}
        else c.moving_objects.End();break;
    case K::Unsupported:error="Unbound MotionGraph score operation";return false;
    }
    return true;
}
}
