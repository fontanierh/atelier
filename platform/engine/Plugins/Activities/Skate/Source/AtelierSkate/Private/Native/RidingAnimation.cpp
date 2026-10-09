#include "RidingAnimation.h"
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float f;std::memcpy(&f,&word,4);return f;}
float Minimum(float a,float b) {return a-b>=0?b:a;}
float Maximum(float a,float b) {return a-b>=0?a:b;}
float Bound(float value,float low,float high) {return Minimum(high,Maximum(low,value));}
float Nonnegative(float value) {return -value>=0?0.0f:value;}
float Unit(float value) {return Minimum(1,Nonnegative(value));}
float FlushSubnormal(float value) {std::uint32_t word;std::memcpy(&word,&value,4);return (word&0x7f800000)==0?Float(word&0x80000000):value;}
Vec4 Vector(Vec3 v) {return {v.x,v.y,v.z,0};}
}
AnimationCrouchingState AnimationCrouchingState::Begin(const AnimationCrouchingPhysical& p,const AnimationCrouchingSettings& s)
{
    AnimationCrouchingState state;const float maximum=s.maximum_height.Evaluate(p.body_164);state.fraction=1.0f-Unit((p.animation_height_72-s.minimum_height)/(maximum-s.minimum_height));return state;
}
AnimationCrouchingOutput AnimationCrouchingState::Update(const AnimationCrouchingPhysical& p,AnimationCrouchingIntents intents,float dt,const AnimationCrouchingSettings& s)
{
    const float restoring=-s.absorption_upforce.Evaluate(1.0f-fraction);float board=Bound(-p.force_516/s.maximum_force,-1,1);absorbed_velocity+=p.body_84;absorbed_velocity=s.skateboard_damping*absorbed_velocity;if (absorbed_velocity<0) board=-board;
    const float ground=Bound(-p.ground_force_520/s.maximum_ground_force,-1,1);float absorption=board<0?(ground>0?ground+board:board):Maximum(board,ground);
    if (absorption<0) {if (!(absorption<restoring)) absorption=restoring;}else absorption+=restoring;
    const float angle=intents.auto_pump_angle.value_or(0),magnitude=intents.auto_pump_magnitude.value_or(0);const auto& a=s.auto_pump;
    const bool started=std::abs(previous_angle)<a.intent_angle_region&&previous_magnitude<a.intent_magnitude_start&&std::abs(angle)<a.intent_angle_region&&magnitude>a.intent_magnitude_start;
    previous_angle=angle;previous_magnitude=magnitude;filtered_potential=std::fma(p.body_188,a.potential_blend,(1.0f-a.potential_blend)*filtered_potential);const bool sufficient_potential=!(filtered_potential<a.potential_threshold);
    if (started) {auto_time=0;auto_state=1;}if (auto_state==1&&auto_time>a.crouch_time) auto_state=2;
    const bool new_auto_pump=(auto_state==1||auto_state==2)&&fraction>a.sufficient_crouch&&sufficient_potential;if (new_auto_pump) auto_state=3;
    if ((auto_state==2||auto_state==3)&&!(fraction>a.standing_threshold+p.minimum_crouch_528)) auto_state=0;
    switch (auto_state)
    {
    case 0:auto_fraction=0;break;
    case 1:auto_fraction=Minimum(a.maximum_crouch.Evaluate(p.body_164),a.crouch_speed+auto_fraction);auto_time=Minimum(a.crouch_time+1.0f,dt+auto_time);break;
    case 2:auto_fraction=Nonnegative(auto_fraction-a.rise_speed);break;
    case 3:auto_fraction=Nonnegative(auto_fraction-a.pump_speed);break;
    default:break;
    }
    float crouch=intents.crouch.value_or(0);if (!intents.motion_flag_108) crouch=Maximum(crouch,intents.hard_turn_crouch.value_or(0));if (intents.motion_flag_108&&intents.manual&&*intents.manual<0) crouch=Maximum(crouch,Float(0x3ecccccd));
    const float blend=Unit(s.input_blend);filtered_input=std::fma(Maximum(crouch,auto_fraction),blend,(1.0f-blend)*filtered_input);if (std::abs(filtered_input)<Float(0x3ba3d70a)) filtered_input=0;
    float delta=s.absorption_factor*absorption;
    if (crouch>0||auto_fraction>0||(player_pumping&&fraction>p.minimum_crouch_528)) {player_pumping=true;delta=Maximum(Minimum(1,Maximum(p.minimum_crouch_528,filtered_input))-fraction,-s.maximum_delta);pump_idle_time=0;}
    else {player_pumping=false;pump_idle_time+=Float(0x3c888889);}
    const bool player_controlled_pump=pump_idle_time<0.5f;const float minimum_delta=-(s.pump_maxspeed.Evaluate(1.0f-fraction)*s.pump_vertical_speed),maximum_delta=s.pump_maxspeed.Evaluate(fraction)*s.pump_vertical_speed;
    delta=Bound(delta,minimum_delta,maximum_delta);delta_fraction=Bound(delta,delta_fraction-s.maximum_delta_delta,s.maximum_delta_delta+delta_fraction);fraction=Bound(fraction+delta_fraction,p.minimum_crouch_528,1);
    const float from_deck=s.maximum_crouch_from_deck*p.deck_angle_532;if (from_deck>fraction) fraction=from_deck;const float height_ratio=Unit(std::fma(-s.maximum_ratio,fraction,1.0f)),maximum_height=s.maximum_height.Evaluate(p.body_164);
    return {std::fma(maximum_height-s.minimum_height,height_ratio,s.minimum_height),new_auto_pump,player_controlled_pump};
}
std::optional<float> AnimationBodyTiltState::Update(bool enabled,bool mirrored,const AnimationBodyTiltPhysical& p,const AnimationBodyTiltSettings& s)
{
    if (!was_enabled&&enabled) {value=0;velocity=0;}was_enabled=enabled;if (!enabled) return std::nullopt;
    std::uint32_t word;std::memcpy(&word,&p.lateral_tilt,4);const float tilt=mirrored?p.lateral_tilt:Float(word^0x80000000);const float target=s.body_spin_factor.Evaluate(std::abs(p.body_spin_speed))*tilt;
    const float speed=p.filtered_category==2?s.air_velocity:s.ground_velocity,acceleration=p.filtered_category==2?s.air_acceleration:s.ground_acceleration;
    const auto bound=[](float v,float lo,float hi) {const float lower=lo-v>=0?lo:v;return hi-lower>=0?lower:hi;};
    const float desired=bound(target-value,-speed,speed),change=bound(desired-velocity,-acceleration,acceleration);velocity+=change;value+=velocity;return value;
}
std::optional<bool> AnimationFakieState::Update(const AnimationFakiePhysical& p,float dt,AnimationFakieSettings s)
{
    bool eligible;if (p.category==5) {after_teleport=0;eligible=false;}else {eligible=after_teleport>s.after_teleport_seconds;after_teleport+=dt;}
    if (!eligible) {slowly_backwards=0;return false;}
    const bool allowed=(p.category==1||p.category==2||(p.category==6&&p.grind_state==503))&&!p.doing_trick;
    if (!allowed) {slowly_backwards=0;return p.category!=1&&p.category!=2?std::optional<bool>(false):std::nullopt;}
    const float projection=Dot3(p.category==1?p.deck_velocity:p.external_velocity,p.board_axis);
    if (p.ground_projected_speed>s.high_speed&&projection<-.5f) {slowly_backwards=0;return true;}
    if (p.ground_projected_speed>s.low_speed&&projection<-.5f) {slowly_backwards=dt+slowly_backwards;return slowly_backwards>s.slowly_backwards_seconds;}
    slowly_backwards=0;return false;
}
AnimationPumpUpdate AnimationPumpState::Update(float physics_pump,std::array<bool,5> occupied,const AnimationPumpSettings& s)
{
    const float previous=value,raw=physics_pump/s.maximum_physics_pump,lower=-raw>=0?0.0f:raw,input=1.0f-lower>=0?lower:1.0f;filtered=std::fma(input,s.input_blend,(1.0f-s.input_blend)*filtered);value=s.amplify.Evaluate(filtered);AnimationPumpUpdate out;
    if (!(previous>s.new_pump_threshold)&&value>s.new_pump_threshold) for (std::size_t i=0;i<occupied.size();++i) if (!occupied[i]) {out.start=i;break;}
    if (out.start) {channel=out.start;peak=value;}if (value>=previous&&value>=peak&&channel) {peak=value;out.influence=std::pair<std::size_t,float>{*channel,value};}return out;
}
Vec4 ConditionAnimationGroundAcceleration(AnimationGroundAccelerationInput p)
{
    const auto inverse=[](const Mat4& frame,Vec4 vector) {Vec4 out;for (std::size_t i=0;i<4;++i) out[i]=std::fma(frame[i][2],vector[2],std::fma(frame[i][1],vector[1],frame[i][0]*vector[0]));return out;};
    const auto rotate=[](const Mat4& frame,Vec4 vector) {Vec4 out;for (std::size_t i=0;i<4;++i) out[i]=std::fma(frame[2][i],vector[2],std::fma(frame[1][i],vector[1],frame[0][i]*vector[0]));return out;};
    auto deck=inverse(p.deck,p.world_acceleration);deck[1]=0;const auto world=rotate(p.deck,deck);auto ground=inverse(p.ground,world);ground[1]=0;return ground;
}
bool AnimationIsBumped(Vec4 acceleration,AnimationGroundAccelerationSettings s)
{
    acceleration[0]*=s.scale_x_acc;const float squared=Dot3(acceleration,acceleration);float reciprocal=ReciprocalSquareRootEstimate(squared);
    for (unsigned i=0;i<2;++i) {const float square=reciprocal*reciprocal,half=reciprocal*.5f,error=std::fma(-squared,square,1.0f);reciprocal=std::fma(half,error,reciprocal);}
    const float magnitude=squared==0?0.0f:squared*reciprocal;return magnitude>s.min_bump_mag;
}
AnimationGroundAccelerationOutput PublishAnimationGroundAcceleration(AnimationGroundAccelerationInput input,AnimationGroundAccelerationSettings settings) {const auto acceleration=ConditionAnimationGroundAcceleration(input);return {acceleration,AnimationIsBumped(acceleration,settings)};}
AnimationPhysicalFeedback PublishPhysicalAnimationFeedback(TurnConditionerState& state,const TurnConditionerSettings& settings,
    AnimationBoardFeedback motion,AnimationPumpingFeedback pumping,float wobble,AnimationReckoningFeedback reckoning,
    AnimationControlFeedback controls,AnimationGroundAccelerationOutput acceleration)
{
    const float lean=(controls.processed_flags&0x00100000)!=0?reckoning.target_lean_angle:-reckoning.target_lean_angle;
    const auto turn=UpdateTurnConditioner(state,{motion.speed,wobble,lean,controls.turn,std::uint8_t((controls.processed_flags&0x80000000)!=0),std::uint8_t(controls.animation_mirrored)},settings);
    const auto system=Vector(reckoning.system_position),board=Vector(reckoning.board_position);Vec4 difference;for (std::size_t i=0;i<4;++i) difference[i]=FlushSubnormal(FlushSubnormal(system[i])-FlushSubnormal(board[i]));const float height=Dot3(difference,Vector(reckoning.system_up));
    return {{turn[0],turn[1],turn[5],turn[6],turn[7],motion.forward_speed},
        {motion.linear_velocity_y,motion.ground_speed,pumping.pumping,pumping.absorption,pumping.ground_normal_absorption,pumping.minimum_crouch,pumping.deck_angle_absorption,height},
        pumping.pump_acceleration,acceleration.acceleration,acceleration.bumped,turn};
}
}
