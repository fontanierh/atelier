#include "GraphMotionOffboardWipeoutOperations.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
std::int32_t Signed(std::uint32_t word) {std::int32_t value;std::memcpy(&value,&word,4);return value;}
float Bounded(float value,float limit) {value=-limit-value>=0? -limit:value;return limit-value>=0?value:limit;}
float PositiveTurn(float value) {return value>=0?value:value+Float(0x40c90fdb);}
void Set(MotionAnimation& a,std::string_view n,float value) {a.SetAttribute({EncodeAnimationName(n),value,false,-1});}
bool Flag(MotionAnimation& a,std::uint32_t bit,bool enabled,std::string& error)
{if (!a.tree.skater_animation_flags) {error="OffboardBodyTweakBlend requires SkaterAnim flag owner";return false;}auto& f=*a.tree.skater_animation_flags;f=(f&~bit)|(enabled?bit:0);return true;}
bool TweakTransition(MotionAnimation& a,const GraphMotionOffboardWipeoutOperation& op,bool held,bool cycle,std::string& error)
{
    const auto& name=held?(cycle?op.br_cycle:op.br_into):(cycle?op.nb_cycle:op.nb_into);bool transitioned;
    return a.TransitionChannel("AirBodyTweak",name,{0,cycle,false,1,cycle?.5f:.15f,false,cycle?.3f:0,false,true},{1,cycle?.1f:.15f,0,0,false},false,true,transitioned,error);
}
bool TweakUpdate(MotionGraphOffboardTweakState& state,const GraphMotionOffboardWipeoutOperation& op,MotionOffboardWipeoutContext c,std::string& error)
{
    if (!c.tweak_physical) {error="OffboardBodyTweakBlend requires completed OffBoard output";return false;}
    if (!c.playback.board_available) {error="OffboardBodyTweakBlend requires OffBoard311";return false;}const auto p=*c.tweak_physical;
    const auto x=c.animation.MotionIntent("OB_AirBodyTweakX"),y=c.animation.MotionIntent("OB_AirBodyTweakY");const auto request=c.animation.MotionIntent("OB_DoAirBodyTweak").has_value();
    if (Signed(state.ticks)>80) state.released=true;
    if (!state.released && x && !(*x>=.1f) && y && !(*y>=.1f)) state.released=true;
    const auto xv=x.value_or(0),yv=y.value_or(0),squared=std::fma(yv,yv,xv*xv);
    const auto inverse=InverseLengthSquared(squared,2),magnitude=squared==0?0:squared*inverse;
    const auto directed=state.released && magnitude>=.1f,centered=request || (!(p.scalar_92<=4) && !directed),active=directed||centered;
    if (active && !(p.time_to_land<.1f))
    {
        const auto remaining=c.animation.channels.Remaining("AirBodyTweak");
        if (c.animation.channels.Has("AirBodyTweak") || state.into_started)
        {if (!(remaining>.01f) && !state.cycle_started) {if (!TweakTransition(c.animation,op,*c.playback.board_available,true,error)) return false;state.cycle_started=true;}}
        else {if (!TweakTransition(c.animation,op,*c.playback.board_available,false,error)) return false;state.into_started=true;}
        if (centered) {for (auto& axis:state.axes) axis*=.85f;}
        else state.axes={std::fma(xv,.15f,state.axes[0]*.85f),std::fma(state.axes[1],.85f,yv*.15f)};
        Set(c.animation,"bodytweakx",state.axes[0]);Set(c.animation,"bodytweaky",state.axes[1]);c.controls.seed_from_air_tweak=true;if (!Flag(c.animation,0x8000,true,error)) return false;
    }
    else if (active && !(p.time_to_land>=.1f)) {if (!Flag(c.animation,0x10000,true,error)) return false;}
    else if (c.animation.channels.Has("AirBodyTweak"))
    {const auto duration=p.time_to_land-.3f>=0?.3f:p.time_to_land;c.animation.channels.EndWith("AirBodyTweak",duration,true);c.controls.seed_from_air_tweak=false;if (!Flag(c.animation,0x8000,false,error)) return false;}
    ++state.ticks;return true;
}
bool WipeoutExecute(MotionGraphWipeoutState& state,MotionOffboardWipeoutContext c,std::uint8_t phase,std::string& error)
{
    if (phase>1) return true;if (!c.wipeout_physical) {error="Wipeout requires completed physical outputs";return false;}const auto& p=*c.wipeout_physical;
    if (phase==0)
    {
        if (!c.animation.tree.skater_animation_flags) {error="Wipeout requires animation stance";return false;}const auto mirrored=(*c.animation.tree.skater_animation_flags&0x40000000u)!=0;
        state.ticks=0;state.lean=p.hips_right_angle_496;state.twist=PositiveTurn(mirrored?-p.hips_up_angle_500:p.hips_up_angle_500);state.twist_velocity=0;state.released=c.controls.seed_from_air_tweak;
        if (state.released) {c.controls.seed_from_air_tweak=false;state.gesture=c.action.air_body_tweak;}else state.gesture={0,0};return true;
    }
    if (c.action.request || Signed(state.ticks)>80) state.released=true;
    if (c.controls.gestures_enabled)
    {
        if (!c.animation.tree.skater_animation_flags) {error="Wipeout requires animation stance";return false;}const auto mirrored=(*c.animation.tree.skater_animation_flags&0x40000000u)!=0;const auto& s=c.settings;
        const auto lean_delta=((1-s.lean_blend)*state.lean+p.hips_right_angle_496*s.lean_blend)-state.lean;state.lean+=Bounded(lean_delta,s.lean_velocity);Set(c.animation,"Lean",state.lean);
        const auto observation=PositiveTurn(mirrored?-p.hips_up_angle_500:p.hips_up_angle_500);auto delta=observation-state.twist;const auto pi=Float(0x40490fdb),turn=Float(0x40c90fdb);
        if (delta>pi) delta-=turn;else if (delta<-pi) delta+=turn;
        delta=((state.twist+delta)*s.twist_blend+(1-s.twist_blend)*state.twist)-state.twist;
        auto velocity=Bounded(delta,s.twist_velocity);if (state.ticks>=2) velocity=Bounded(velocity-state.twist_velocity,s.twist_acceleration)+state.twist_velocity;
        auto twist=state.twist+velocity;if (twist>turn) twist-=turn;state.twist_velocity=velocity;state.twist=PositiveTurn(twist);Set(c.animation,"Twist",state.twist);
        const auto x=c.action.gesture?std::optional<float>((*c.action.gesture)[0]):std::nullopt,y=c.action.gesture?std::optional<float>((*c.action.gesture)[1]):std::nullopt;const auto xv=x.value_or(0),yv=y.value_or(0);
        if (!state.released && x && y && std::abs(xv)<.1f && std::abs(yv)<.1f) state.released=true;
        if (state.released) {state.gesture[0]=(1-s.gesture_x_blend)*state.gesture[0]+xv*s.gesture_x_blend;state.gesture[1]=(1-s.gesture_y_blend)*state.gesture[1]+yv*s.gesture_y_blend;}
        if (state.gesture[1]*state.gesture[1]+state.gesture[0]*state.gesture[0]>s.threshold*s.threshold) c.animation.EmitPacket(EncodeAnimationName("ControlledWipeout"),1);
        c.controls.gesture=state.gesture;
    }
    Set(c.animation,"WipeoutGestureX",state.gesture[0]);Set(c.animation,"WipeoutGestureY",state.gesture[1]);++state.ticks;return true;
}
}
bool MotionGraphWipeoutSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const std::pair<std::string_view,float*> fields[]={{"controlled_drives_thresh",&threshold},{"clamp_twist_vel",&twist_velocity},{"clamp_twist_acc",&twist_acceleration},{"clamp_lean_vel",&lean_velocity},{"blend_twist",&twist_blend},{"blend_lean",&lean_blend},{"blend_gesture_y",&gesture_y_blend},{"blend_gesture_x",&gesture_x_blend}};
    for (const auto& [name,output]:fields) {const auto* f=data.Field("anim_wipeout","default",name);const auto value=f?f->Float():std::nullopt;if (!value) {error="Expected finite stock float at anim_wipeout/default/"+std::string(name);return false;}*output=*value;}error.clear();return true;
}
void MotionGraphOffboardTweakState::Begin() {ticks=0;into_started=false;cycle_started=false;released=false;}
MotionGraphOffboardWipeoutInstance CreateMotionGraphOffboardWipeoutInstance(const GraphMotionOffboardWipeoutOperation& op)
{using K=GraphMotionOffboardWipeoutOperation::Kind;switch (op.kind) {case K::BodyTweak:return MotionGraphOffboardTweakState{};case K::TwistLean:return MotionGraphTwistLeanState{};case K::Wipeout:return MotionGraphWipeoutState{};default:return std::monostate{};}}
bool ParseGraphMotionOffboardWipeoutOperation(const GraphAttributes& a,GraphMotionOffboardWipeoutOperation& output,bool& recognized,std::string& error)
{
    const auto name=TrimMotionGraphName(a.Text("name").value_or(""));GraphMotionOffboardWipeoutOperation op;using K=GraphMotionOffboardWipeoutOperation::Kind;recognized=true;error.clear();
    if (name=="OffboardBodyTweakBlend") {op.kind=K::BodyTweak;op.nb_cycle=a.Text("NbCycAnim").value_or(op.nb_cycle);op.nb_into=a.Text("NbIntoAnim").value_or(op.nb_into);op.br_cycle=a.Text("BrCycAnim").value_or(op.br_cycle);op.br_into=a.Text("BrIntoAnim").value_or(op.br_into);}
    else if (name=="MatchTwistAndLean") {op.kind=K::TwistLean;op.always=a.Text("update")==std::optional<std::string_view>("always");}
    else if (name=="Wipeout") op.kind=K::Wipeout;else if (name=="EnableWipeoutGestures") op.kind=K::EnableGestures;else recognized=false;output=std::move(op);return true;
}
bool GraphMotionOffboardWipeoutOperation::Execute(MotionGraphOffboardWipeoutInstance& instance,MotionOffboardWipeoutContext c,std::uint8_t phase,std::string& error) const
{
    using K=Kind;error.clear();switch (kind)
    {
    case K::EnableGestures:if (phase!=1) c.controls.gestures_enabled=phase==0;return true;
    case K::BodyTweak:{auto* state=std::get_if<MotionGraphOffboardTweakState>(&instance);if (!state) {error="OffboardBodyTweakBlend operation/instance mismatch";return false;}if (phase==0) state->Begin();else if (phase==1) return TweakUpdate(*state,*this,c,error);else if (c.animation.channels.Has("AirBodyTweak")) c.animation.channels.EndWith("AirBodyTweak",.1f,true);return true;}
    case K::Wipeout:{if (phase>1) return true;auto* state=std::get_if<MotionGraphWipeoutState>(&instance);if (!state) {error="Wipeout operation/instance mismatch";return false;}return WipeoutExecute(*state,c,phase,error);}
    case K::TwistLean:{auto* state=std::get_if<MotionGraphTwistLeanState>(&instance);if (!state) {error="MatchTwistAndLean operation/instance mismatch";return false;}std::optional<MotionGraphTwistLeanState> observation;
        if (phase==0 || (phase==1 && always)) {if (!c.wipeout_physical) {error="MatchTwistAndLean requires canonical physical angles";return false;}if (!c.animation.tree.skater_animation_flags) {error="MatchTwistAndLean requires live animation stance";return false;}const auto mirrored=(*c.animation.tree.skater_animation_flags&0x40000000u)!=0;observation=MotionGraphTwistLeanState{mirrored?-c.wipeout_physical->hips_up_angle_500:c.wipeout_physical->hips_up_angle_500,c.wipeout_physical->hips_right_angle_496};}
        if (phase==0) {if (observation) *state=*observation;}else if (phase==1) {const auto values=always?observation.value_or(MotionGraphTwistLeanState{}):*state;Set(c.animation,"Twist",values.twist);Set(c.animation,"Lean",values.lean);}return true;}
    case K::Unsupported:error="Unbound MotionGraph offboard/wipeout operation";return false;
    }
    return true;
}
}
