#include "GraphMotionPushOperations.h"
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
// push_behaviors.rs uses subtraction/fsel, rather than f32::min/max.
float Minimum(float a,float b) {return a-b>=0?b:a;}
float Maximum(float a,float b) {return a-b>=0?a:b;}
float Bounded(float value,float minimum,float maximum) {return Minimum(maximum,Maximum(minimum,value));}
float Nonnegative(float value) {return value>=0?value:0.0f;}
float Unit(float value) {const auto lower=-value>=0?0.0f:value;return 1.0f-lower>=0?lower:1.0f;}
float VelocityBlend(float speed,float low_length,float low_velocity,float high_length,float high_velocity)
{
    const auto low_distance=low_length*low_velocity,speed_distance=speed*low_length;
    const auto sum=std::fma(high_length,high_velocity,speed_distance),numerator=speed_distance-low_distance;
    const auto denominator=-std::fma(speed,high_length,-(sum-low_distance));return Unit(numerator/denominator);
}
float BlendedEnd(float coefficient,MotionGraphPushClipMetrics low,MotionGraphPushClipMetrics high)
{
    coefficient=Unit(coefficient);const auto high_weight=coefficient*high.length,low_weight=(1.0f-coefficient)*low.length;
    return std::fma(high.end_velocity,high_weight,low.end_velocity*low_weight)/(high_weight+low_weight);
}
float Approach(float current,float target,float rate,float dt)
{
    const auto difference=target-current;float result;
    if (std::abs(difference)>.001f)
    {if (difference>0) {const auto candidate=std::fma(dt,rate,current);result=candidate-target>=0?target:candidate;}
        else {const auto candidate=-std::fma(dt,rate,-current);result=candidate-target>=0?candidate:target;}}
    else result=target;return Unit(result);
}
void InitializePush(MotionGraphPushState& state)
{state.continue_push=false;state.current_push_dv=0;state.current={-1,-1,-1};state.target=state.current;}
bool ClipMetrics(const AnimationMetadata& metadata,std::string_view name,MotionGraphPushClipMetrics& out,std::string& error)
{
    const auto* clip=metadata.Clip(name,error);if (!clip) return false;const auto frames=Float(clip->frames_bits),fps=Float(clip->fps_bits),base=Float(clip->base_speed_bits);
    // PushingSettings::metadata constructs the clock directly, before later
    // SetSpeed's different multiplication order. It does not mutate metadata.
    const auto length=(frames-1.0f)/((1.0f*base)*fps);ClipClock clock{frames,fps,base,1,length,0,0,0,(clip->flags_word&0x10000000)!=0,(clip->flags_word&0x40000000)!=0};
    std::optional<float> begin,end;
    for (const auto& attribute:clip->attributes)
    {
        const auto from=Float(attribute.begin_bits);
        if (from!=-1)
        {const auto status=std::uint32_t(clock.AttributeStatus(from,Float(attribute.end_bits)));if ((15u&0x1cu&status)==0 || (15u&3u&status)==0) continue;}
        if (attribute.type_id!=0 && attribute.type_id!=1 && attribute.type_id!=3)
        {error=std::string(name)+": attribute "+attribute.name+" needs type"+std::to_string(attribute.type_id)+" evaluation";return false;}
        if (attribute.payload_words.empty()) {error=std::string(name)+": uninitialized push attribute payload";return false;}
        const auto key=EncodeAnimationName(attribute.name);const auto value=Float(attribute.payload_words[0]);
        if (key==EncodeAnimationName("HStr_Vel_B") || key==EncodeAnimationName("LStr_Vel_B")) begin=value;
        else if (key==EncodeAnimationName("Vel_E")) end=value;
    }
    if (!begin) {error=std::string(name)+": missing begin-velocity attribute";return false;}
    if (!end) {error=std::string(name)+": missing Vel_E attribute";return false;}
    out={length,*begin,*end};return true;
}
}
MotionGraphPushAttributes MotionGraphPushAttributes::FromClips(std::array<MotionGraphPushClipMetrics,4> clips)
{
    const std::array<float,4> b{{clips[0].begin_velocity,clips[1].begin_velocity,clips[2].begin_velocity,clips[3].begin_velocity}};
    const std::array<float,4> d{{clips[0].end_velocity-b[0],clips[1].end_velocity-b[1],clips[2].end_velocity-b[2],clips[3].end_velocity-b[3]}};
    return {clips,Minimum(Minimum(b[0],b[1]),Minimum(b[2],b[3])),Maximum(Maximum(b[0],b[1]),Maximum(b[2],b[3])),
        Minimum(Minimum(d[0],d[1]),Minimum(d[2],d[3])),Maximum(Maximum(d[0],d[1]),Maximum(d[2],d[3]))};
}
MotionGraphPushBlend MotionGraphPushAttributes::Target(float forward_speed,float strength) const
{
    const auto speed=Bounded(Nonnegative(forward_speed),minimum_begin_velocity,maximum_begin_velocity);strength=Bounded(strength,minimum_delta_velocity,maximum_delta_velocity);
    const auto& a=clips[0];const auto& b=clips[1];const auto& c=clips[2];const auto& d=clips[3];
    const auto strong_speed=Bounded(speed,a.begin_velocity,b.begin_velocity),gentle_speed=Bounded(speed,c.begin_velocity,d.begin_velocity);
    const auto strong=VelocityBlend(strong_speed,a.length,a.begin_velocity,b.length,b.begin_velocity),gentle=VelocityBlend(gentle_speed,c.length,c.begin_velocity,d.length,d.begin_velocity);
    const auto strong_length=std::fma(1.0f-strong,a.length,b.length*strong),gentle_length=std::fma(1.0f-gentle,c.length,d.length*gentle);
    const auto strong_end=BlendedEnd(strong,a,b),gentle_end=BlendedEnd(gentle,c,d),target_end=Bounded(strength+speed,gentle_end,strong_end);
    const auto strength_blend=VelocityBlend(target_end,gentle_length,gentle_end,strong_length,strong_end);return {Unit(strong),Unit(gentle),Unit(strength_blend)};
}
float MotionGraphPushAttributes::OutFactor(float forward_speed,float strength,float weight,float maximum_out) const
{
    const auto first_speed=minimum_begin_velocity+minimum_delta_velocity,speed=Bounded(Nonnegative(forward_speed),first_speed,maximum_begin_velocity);strength=Bounded(strength,minimum_delta_velocity,maximum_delta_velocity);
    const auto strength_factor=Unit((strength-minimum_delta_velocity)/(maximum_delta_velocity-minimum_delta_velocity)),speed_factor=Unit((speed-first_speed)/(maximum_begin_velocity-first_speed));
    const auto combined=std::fma(strength_factor,1.0f-weight,speed_factor*weight),lower=-combined>=0?0.0f:combined;return Minimum(maximum_out,lower);
}
float MotionGraphPushCurves::Strength(float held,float speed) const
{const auto duration=button_time_max.Evaluate(speed);return button_time_to_dv.Evaluate(Unit(held/duration));}
MotionGraphPushBlend MotionGraphPushCurves::UpdateBlend(MotionGraphPushBlend current,MotionGraphPushBlend target,float speed,float dt) const
{
    if (current.vel_e<0) current=target;const auto frame_seconds=Float(0x3c888889),velocity_rate=1.0f/(blend_speed_over_frames.Evaluate(current.vel_e)*frame_seconds);
    speed=Nonnegative(speed);const auto strength_rate=1.0f/(blend_acc_over_frames.Evaluate(speed)*frame_seconds);
    return {Approach(current.hstr_vel_b,target.hstr_vel_b,velocity_rate,dt),Approach(current.lstr_vel_b,target.lstr_vel_b,velocity_rate,dt),Approach(current.vel_e,target.vel_e,strength_rate,dt)};
}
bool GraphMotionPushSettings::Load(const SettingsDatabase& data,const AnimationMetadata& metadata,std::string& error)
{
    const auto scalar=[&](std::string_view name,float& value)
    {const auto field=data.Field("anim_motion","pushing",name);if (!field) {error="Missing stock field anim_motion/pushing/"+std::string(name);return false;}
        if (field->type!="EA::Reflection::Float" || !field->Float()) {error="Expected float at anim_motion/pushing/"+std::string(name);return false;}value=*field->Float();
        if (!std::isfinite(value)) {error="Non-finite stock float anim_motion/pushing/"+std::string(name);return false;}return true;};
    const auto curve=[&](std::string_view name,PointGraph<8>& value)
    {const auto field=data.Field("anim_motion","pushing",name);const std::uint32_t* words=nullptr;
        if (!field || !field->Words(20,words)) {error="Missing anim_motion/pushing curve "+std::string(name);return false;}
        for (std::size_t i=0;i<8;++i) {value.x[i]=Float(words[4+i]);value.y[i]=Float(words[12+i]);}return true;};
    if (!curve("button_time_max",curves.button_time_max) || !curve("button_time_to_dv",curves.button_time_to_dv) || !curve("blend_speed_over_frames",curves.blend_speed_over_frames) || !curve("blend_acc_over_frames",curves.blend_acc_over_frames) ||
        !scalar("pushing_usemaxpushfromteleporttime",teleport_window) || !scalar("max_holding_acc",maximum_holding_acceleration) || !scalar("dynamic_out_factor_speed_vs_acc",out_speed_weight) || !scalar("last_push_out_time",maximum_out_factor)) return false;
    const std::array<std::array<std::string_view,4>,2> names{{
        {{"R_PUSHLSP_HSTR_N_0_CYC1","R_PUSHHSP_HSTR_N_0_CYC1","R_PUSHLSP_LSTR_N_0_CYC1","R_PUSHHSP_LSTR_N_0_CYC1"}},
        {{"R_PUSHLSP_HSTR_MONGO_0_CYC1","R_PUSHHSP_HSTR_MONGO_0_CYC1","R_PUSHLSP_LSTR_MONGO_0_CYC1","R_PUSHHSP_LSTR_MONGO_0_CYC1"}}}};
    for (std::size_t i=0;i<names.size();++i)
    {std::array<MotionGraphPushClipMetrics,4> metrics{};for (std::size_t j=0;j<4;++j) if (!ClipMetrics(metadata,names[i][j],metrics[j],error)) return false;
        (i==0?regular:mongo)=MotionGraphPushAttributes::FromClips(metrics);}
    error.clear();return true;
}
const MotionGraphPushAttributes& GraphMotionPushSettings::Attributes(bool requested_regular,bool is_switch) const
{return requested_regular!=is_switch?regular:mongo;}
MotionGraphFirstPushStrength MotionGraphFirstPushStrength::Begin(float time,float window)
{return {0,time<window,true,true};}
void MotionGraphFirstPushStrength::Update(MotionGraphPushState& state,const MotionGraphPushCurves& curves,std::optional<float> pushing,float speed,float dt)
{
    if (!pushing) first_push=false;
    if (first_push || push_from_teleport)
    {float held;if (push_from_teleport) {held=simulated_held_seconds;simulated_held_seconds=dt+simulated_held_seconds;}else held=pushing.value_or(0);
        const auto strength=curves.Strength(held,Nonnegative(speed));if (strength>state.current_push_dv) state.current_push_dv=strength;}
    first_update=false;
}
MotionGraphPushCycle MotionGraphPushCycle::Begin(MotionGraphPushState& state,const MotionGraphPushCurves& curves,MotionGraphPushIntents intents)
{const bool holding=bool(intents.pushing)&&intents.configured_foot;state.continue_push=holding;return {holding?Phase::HoldingFirst:Phase::WaitingNext,curves.button_time_to_dv.Evaluate(0)};}
void MotionGraphPushCycle::Update(MotionGraphPushState& state,const MotionGraphPushCurves& curves,MotionGraphPushIntents intents,float speed,float maximum)
{
    speed=Nonnegative(speed);
    if (phase==Phase::HoldingFirst)
    {if (intents.pushing) {next_push_dv=curves.Strength(*intents.pushing,speed);if (next_push_dv>maximum) {next_push_dv=maximum;state.current_push_dv=maximum;}if (state.current_push_dv<next_push_dv) state.current_push_dv=next_push_dv;}
        else {phase=Phase::WaitingNext;next_push_dv=curves.button_time_to_dv.Evaluate(0);state.continue_push=false;}}
    if (phase==Phase::WaitingNext && intents.new_push && intents.configured_foot) phase=Phase::HoldingNext;
    if (phase==Phase::HoldingNext && !intents.configured_foot) {phase=Phase::NextReleased;state.current_push_dv=next_push_dv;}
    if (phase==Phase::HoldingNext) {next_push_dv=curves.Strength(intents.pushing.value_or(0),speed);if (state.current_push_dv<next_push_dv) state.current_push_dv=next_push_dv;state.continue_push=true;}
}
bool ParseGraphMotionPushOperation(const GraphAttributes& a,GraphMotionPushOperation& output,bool& recognized,std::string& error)
{
    GraphMotionPushOperation op;const auto name=a.Text("name");using K=GraphMotionPushOperation::Kind;recognized=true;error.clear();
    if (name=="InitPush") op.kind=K::Init;
    else if (name=="ComputeFirstPushStrength") op.kind=K::FirstStrength;
    else if (name=="ComputeTargetCoefsFromSpeedAndStrength") {op.kind=K::TargetCoefficients;op.regular_attributes=a.BooleanByte("regularAttributes",1)!=0;}
    else if (name=="ComputeRepushDeadline") {op.kind=K::RepushDeadline;op.regular_attributes=a.BooleanByte("regularAttributes",1)!=0;}
    else if (name=="SetPushCoefs") {op.kind=K::SetCoefficients;op.on_first_update_only=a.BooleanByte("onFirstUpdateOnly",0)!=0;}
    else if (name=="PushCycle") {op.kind=K::Cycle;op.new_push_name=a.Text("newPushName").value_or("LeftPush");}
    else if (name=="PushOut") {op.kind=K::Out;op.right_foot=a.BooleanByte("isRightFoot",1)!=0;}
    else recognized=false;output=std::move(op);return true;
}
bool GraphMotionPushOperation::Execute(GraphMotionPushInstance& instance,MotionPushOperationContext c,std::uint8_t phase,std::string& error) const
{
    using K=Kind;error.clear();if (!c.physical) {error="Push behavior requires actual skater physical outputs";return false;}
    if (!c.shared) {error="Native push state initialization has not been published";return false;}
    auto& state=*c.shared;const auto& physical=*c.physical;const auto& curves=c.settings.curves;
    const auto intents=[&](){return MotionGraphPushIntents{c.animation.MotionIntent("Pushing"),c.animation.motion_intents.Contains("NewPush"),c.animation.motion_intents.Contains(new_push_name)};};
    const auto publish=[&](std::string_view name,float value,bool normalized){c.animation.SetAttribute({EncodeAnimationName(name),value,normalized,-1});};
    if (phase==0)
    {
        switch (kind)
        {case K::Init:InitializePush(state);break;
        case K::FirstStrength:instance.first_strength=MotionGraphFirstPushStrength::Begin(c.time_since_teleport,c.settings.teleport_window);break;
        case K::SetCoefficients:instance.first_update=true;break;
        case K::Cycle:instance.cycle=MotionGraphPushCycle::Begin(state,curves,intents());break;
        case K::Out:{const auto value=physical.foot_frame?physical.foot_frame->OutDistance(right_foot):std::array<float,2>{0,0};publish("OutDistanceX",value[0],false);publish("OutDistanceY",value[1],false);break;}
        default:break;}
    }
    else if (phase==1)
    {
        switch (kind)
        {case K::FirstStrength:if (!instance.first_strength) {error="ComputeFirstPushStrength updated before Begin";return false;}instance.first_strength->Update(state,curves,c.animation.MotionIntent("Pushing"),physical.forward_speed,c.dt);break;
        case K::TargetCoefficients:state.target=c.settings.Attributes(regular_attributes,physical.is_switch).Target(physical.forward_speed,state.current_push_dv);break;
        case K::SetCoefficients:
            if (!on_first_update_only || instance.first_update) {state.current=curves.UpdateBlend(state.current,state.target,physical.forward_speed,c.dt);publish("HStr_Vel_B",state.current.hstr_vel_b,true);publish("LStr_Vel_B",state.current.lstr_vel_b,true);publish("Vel_E",state.current.vel_e,true);}instance.first_update=false;break;
        case K::Cycle:if (!instance.cycle) {error="PushCycle updated before Begin";return false;}instance.cycle->Update(state,curves,intents(),physical.forward_speed,c.settings.maximum_holding_acceleration);break;
        default:break;}
    }
    else if (kind==K::RepushDeadline) state.out_factor=c.settings.Attributes(regular_attributes,physical.is_switch).OutFactor(physical.forward_speed,state.current_push_dv,c.settings.out_speed_weight,c.settings.maximum_out_factor);
    if (kind==K::Unsupported) {error="Unbound MotionGraph push operation";return false;}return true;
}
}
