#include "GraphMotionTrickLifecycle.h"
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
float Clamp(float value,float low,float high) {return value<low?low:value>high?high:value;}
float ManualClamp(float value,float limit) {const auto lower=-limit-value>=-0.0f?-limit:value;return limit-lower>=-0.0f?lower:limit;}
void Set(MotionAnimation& a,std::string_view name,float value) {a.SetAttribute({EncodeAnimationName(name),value,false,-1});}
bool ClipDuration(const AnimationMetadata& metadata,std::string_view name,float& duration,std::string& error)
{const auto* clip=metadata.Clip(name,error);if (!clip) return false;duration=(Float(clip->frames_bits)-1.0f)/(Float(clip->base_speed_bits)*Float(clip->fps_bits));return true;}
}
bool MotionGraphTrickLifecycleSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const auto words=[&](std::string_view key,std::string_view name,std::size_t count,const std::uint32_t*& out)
    {const auto field=data.Field("anim_motion",key,name);if (!field || !field->Words(count,out)) {error="Missing stock words anim_motion/"+std::string(key)+"/"+std::string(name);return false;}return true;};
    const std::uint32_t* w=nullptr;if (!words("Hash_41DB0C4F82003A15","Hash_E0C1407B688858AD",20,w)) return false;finger_minimum=Float(w[0]);finger_maximum=Float(w[2]);
    if (!std::isfinite(finger_minimum) || !std::isfinite(finger_maximum) || finger_minimum>finger_maximum) {error="FingerFlipOut has invalid stock timer bounds";return false;}
    for (std::size_t i=0;i<8;++i) {finger_curve.x[i]=Float(w[4+i]);finger_curve.y[i]=Float(w[12+i]);}
    if (!words("hippy_flip","antic_length_to_hippy_height",20,w)) return false;for (std::size_t i=0;i<8;++i) {hippy_height.x[i]=Float(w[4+i]);hippy_height.y[i]=Float(w[12+i]);}
    if (!words("manual","manual_balance",16,w)) return false;for (std::size_t i=0;i<8;++i) {manual_balance.x[i]=Float(w[i]);manual_balance.y[i]=Float(w[8+i]);}
    const auto scalar=[&](std::string_view name,float& out){const auto field=data.Field("anim_motion","manual",name);if (!field || !field->Float() || field->type!="EA::Reflection::Float") {error="Expected float at anim_motion/manual/"+std::string(name);return false;}out=*field->Float();if (!std::isfinite(out)) {error="Non-finite stock float anim_motion/manual/"+std::string(name);return false;}return true;};
    if (!scalar("manual_clamp_vel",manual_velocity_limit) || !scalar("manual_clamp_acc",manual_acceleration_limit)) return false;error.clear();return true;
}
float MotionGraphFingerFlipState::Update(bool present,float dt,const MotionGraphTrickLifecycleSettings& s)
{elapsed=present?elapsed-dt:elapsed+dt;elapsed=Clamp(elapsed,s.finger_minimum,s.finger_maximum);return s.finger_curve.Evaluate(elapsed);}
float MotionGraphManualAngleState::Update(std::optional<float> source,const MotionGraphTrickLifecycleSettings& s)
{
    const auto manual=source.value_or(0);auto target=s.manual_balance.Evaluate(std::abs(manual));target=manual>=-0.0f?target:-target;const auto desired=ManualClamp(target-angle,s.manual_velocity_limit),acceleration=ManualClamp(desired-velocity,s.manual_acceleration_limit);velocity+=acceleration;angle+=velocity;return angle;
}
void MotionGraphStoreLandingState::Update(std::uint32_t category,Vec4 com,Vec4 up,MotionGraphRidingState& riding)
{
    const auto air=category==2;if (!was_air&&air) riding.last_good_landing_velocity=0;was_air=air;const auto velocity=Dot3(com,up);if (velocity<0 && velocity<previous_velocity) riding.last_good_landing_velocity=std::abs(velocity);previous_velocity=velocity;
}
MotionGraphTrickLifecycleInstance CreateMotionGraphTrickLifecycleInstance(const GraphMotionTrickLifecycleOperation& op)
{
    using K=GraphMotionTrickLifecycleOperation::Kind;switch (op.kind) {case K::FingerFlip:return MotionGraphFingerFlipState{};case K::HippyJump:return MotionGraphHippyJumpState{};case K::ManualAngle:return MotionGraphManualAngleState{};case K::StoreLanding:return MotionGraphStoreLandingState{};case K::SetLanding:return MotionGraphLandingHeightState{};default:return std::monostate{};}
}
bool ParseGraphMotionTrickLifecycleOperation(const GraphAttributes& a,GraphMotionTrickLifecycleOperation& output,bool& recognized,std::string& error)
{
    GraphMotionTrickLifecycleOperation op;const auto raw=a.Text("name").value_or(""),name=TrimMotionGraphName(raw);using K=GraphMotionTrickLifecycleOperation::Kind;recognized=true;error.clear();
    if (raw=="FootPlantAbsorb") op.kind=K::FootplantAbsorb;else if (raw=="SetHandPlantAnticLength") op.kind=K::HandplantAntic;else if (raw=="StoreLandingData") op.kind=K::StoreLanding;else if (raw=="SetLandingData") op.kind=K::SetLanding;
    else if (name=="FingerFlipOut" || name=="HippyJumpAntic" || name=="SetManualAngle" || name=="LandOnBoard")
    {if (raw!=name) {error="Original stock gameplay operation parser has an unreachable raw-name mismatch";return false;}
        if (name=="FingerFlipOut") {op.kind=K::FingerFlip;op.grab_intent=a.Text("grabintent").value_or("");}
        else if (name=="HippyJumpAntic") op.kind=K::HippyJump;else if (name=="SetManualAngle") op.kind=K::ManualAngle;else op.kind=K::LandOnBoard;}
    else recognized=false;output=std::move(op);return true;
}
bool GraphMotionTrickLifecycleOperation::Execute(MotionGraphTrickLifecycleInstance& instance,MotionTrickLifecycleContext c,std::uint8_t phase,std::string& error) const
{
    error.clear();using K=Kind;auto& a=c.animation;
    switch (kind)
    {
    case K::FingerFlip:{auto* state=std::get_if<MotionGraphFingerFlipState>(&instance);if (!state) {error="FingerFlipOut operation/instance mismatch";return false;}if (phase==0) state->elapsed=0;else if (phase==1) Set(a,"Grabbing",state->Update(a.motion_intents.Contains(grab_intent),c.dt,c.settings));break;}
    case K::HippyJump:{auto* state=std::get_if<MotionGraphHippyJumpState>(&instance);if (!state) {error="HippyJumpAntic instance was not allocated";return false;}if (phase==0) {state->active=true;state->elapsed=0;}else if (phase==1) {state->elapsed+=1.0f/60.0f;Set(a,"TrickHeight",c.settings.hippy_height.Evaluate(state->elapsed));}else {state->active=false;state->elapsed=0;}break;}
    case K::ManualAngle:{auto* state=std::get_if<MotionGraphManualAngleState>(&instance);if (!state) {error="SetManualAngle instance was not allocated";return false;}if (phase==0) *state={};else if (phase==1) Set(a,"manual_angle",state->Update(a.MotionIntent("Manual"),c.settings));break;}
    case K::FootplantAbsorb:if (phase==1) {if (!c.physical) {error="FootPlantAbsorb requires physical output";return false;}Set(a,"absorblength",c.physical->footplant_duration);}break;
    case K::HandplantAntic:if (phase==0) {float normal,late;if (!ClipDuration(a.tree.Metadata(),"INVERT_HANDPLANT_FS_0_ANTIC",normal,error) || !ClipDuration(a.tree.Metadata(),"INVERT_HANDPLANT_FS_0_ANTIC_LATE",late,error)) return false;if (!c.physical) {error="Handplant antic requires physical output";return false;}const auto value=((normal-(c.physical->handplant_thresholds[2]-c.physical->handplant_time)-late)/(normal-late));Set(a,"antic_length",Clamp(value,0,1));}break;
    case K::LandOnBoard:if (phase==0) {if (!c.physical) {error="LandOnBoard requires completed physical output";return false;}if (c.physical->landing_turning) {if (!a.tree.skater_animation_flags) {error="LandOnBoard requires SkaterAnim orientation";return false;}*a.tree.skater_animation_flags^=0x80000000u;}}break;
    case K::StoreLanding:{auto* state=std::get_if<MotionGraphStoreLandingState>(&instance);if (!state) {error="StoreLandingData operation/instance mismatch";return false;}if (phase==1) {if (!c.filtered_category) {error="StoreLandingData requires physical category";return false;}if (!c.native_physical) {error="StoreLandingData requires raw physical COM velocity/up";return false;}state->Update(*c.filtered_category,c.native_physical->com_velocity,c.native_physical->system_up,c.riding);}break;}
    case K::SetLanding:{auto* state=std::get_if<MotionGraphLandingHeightState>(&instance);if (!state) {error="Landing operation/instance mismatch";return false;}if (phase==0) {if (!c.landing) {error="SetLandingData requires actual landing publication";return false;}if (!c.playback.is_mirrored) {error="SetLandingData requires animation stance";return false;}Set(a,"Spin",*c.playback.is_mirrored?c.landing->spin:-c.landing->spin);Set(a,"AvgVelY",c.riding.last_good_landing_velocity);state->height=c.landing->height;}else if (phase==1) Set(a,"disttocog",state->height);break;}
    case K::Unsupported:error="Unbound MotionGraph trick lifecycle operation";return false;
    }
    return true;
}
}
