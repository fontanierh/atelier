#include "MotionAnimationOperations.h"
#include "GraphMotionName.h"
#include <cstring>
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float f;std::memcpy(&f,&bits,4);return f;}
TransitionSettings Transition(const GraphAttributes& a)
{
    const auto type=a.Text("transType").value_or("");TransitionSettings s;s.kind=type=="play"?1:type=="sequence"?4:type=="channelblend"?3:2;s.seconds=Float(a.FloatBits("time",0x3e4ccccd));
    s.under=std::uint32_t(a.BooleanByte("transitionUnder",0)!=0);s.matching=a.BooleanByte("blendWithCurrentFrame",0)!=0?1:a.BooleanByte("blendMatchPhase",0)!=0?2:a.BooleanByte("blendMatchFrame",0)!=0?3:0;s.use_channels_from_weights=a.BooleanByte("useChannelFromWeights",0)!=0;return s;
}
}
bool ParseMotionAnimationOperation(const GraphAttributes& a,MotionAnimationOperation& output,bool& recognized,std::string& error)
{
    recognized=false;const auto raw=a.Text("name");if (!raw) {error="MotionGraph operation has no name";return false;}MotionAnimationOperation op;
    if (*raw=="CreateAttribute")
    {
        op.kind=MotionAnimationOperation::Kind::CreateAttribute;op.attribute=EncodeAnimationName(a.Text("attName").value_or(""));
        if (const auto* always=a.Get("always")) {const auto value=Float(always->float_bits);op.values={value,value,0.0f};}
        else if (!a.Get("begin")&&!a.Get("update")&&!a.Get("end")) op.values={std::nullopt,0.0f,std::nullopt};
        else {const std::array<std::string_view,3> names{"begin","update","end"};for (std::size_t i=0;i<3;++i) if (const auto* v=a.Get(names[i])) op.values[i]=Float(v->float_bits);op.set=a.BooleanByte("set",0)!=0;}
    }
    else if (TrimMotionGraphName(*raw)=="PlayAnimation")
    {
        op.kind=MotionAnimationOperation::Kind::Play;auto& p=op.play;p.animation=a.Text("anim").value_or("");
        if (const auto v=a.Text("switchAnim")) p.switch_animation=std::string(*v);if (const auto v=a.Text("mirrorAnim")) p.mirror_animation=std::string(*v);if (const auto v=a.Text("noBoardAnim")) p.no_board_animation=std::string(*v);
        p.playback_speed=Float(a.FloatBits("playBackSpeed",0x3f800000));p.apply_posture=a.BooleanByte("applyPosture",1)!=0;p.transition=Transition(a);
    }
    else {error.clear();return true;}
    recognized=true;output=std::move(op);error.clear();return true;
}
bool AddMotionAnimationParameter(MotionAnimationOperation& op,const GraphAttributes& a,std::string& error)
{
    if (op.kind==MotionAnimationOperation::Kind::Play)
    {
        PlaybackParameter p;const auto from=a.Text("from").value_or("");
        if (from=="intent") {p.source=PlaybackParameterSource::MotionIntent;p.intent=a.Text("intent").value_or("");}
        else if (from=="lastAnim") {p.source=PlaybackParameterSource::LastAnimation;p.last_animation=EncodeAnimationName(a.Text("attribute").value_or(""));}
        else {p.source=PlaybackParameterSource::FilteredIntent;p.intent=a.Text("filteredIntent").value_or("");}
        if (const auto v=a.Text("rename")) {const auto key=EncodeAnimationName(*v);if (key!=EncodeAnimationName("")) p.rename=key;}
        if (const auto* v=a.Get("defaultValue")) p.default_value=Float(v->float_bits);p.normalized=p.source!=PlaybackParameterSource::LastAnimation&&a.BooleanByte("normalize",0)!=0;op.play.parameters.push_back(std::move(p));
    }error.clear();return true;
}
bool ExecuteMotionAnimationOperation(const MotionAnimationOperation& op,MotionAnimationOperationState& state,std::uint8_t phase,PlaybackContext& context,MotionAnimation& animation,std::string& error)
{
    if (op.kind==MotionAnimationOperation::Kind::Play)
    {if (phase==0) return state.play.Begin(op.play,context,animation,error);if (phase==1) return state.play.Update(op.play,animation,error);state.play.End();error.clear();return true;}
    if (op.kind==MotionAnimationOperation::Kind::CreateAttribute)
    {if (phase>=3) {error="CreateAttribute phase exceeds lifecycle";return false;}if (const auto value=op.values[phase]) {animation.EmitPacket(op.attribute,*value);if (op.set) animation.SetAttribute({op.attribute,*value,false,-1});}error.clear();return true;}
    error="Unsupported MotionAnimation operation";return false;
}
}
