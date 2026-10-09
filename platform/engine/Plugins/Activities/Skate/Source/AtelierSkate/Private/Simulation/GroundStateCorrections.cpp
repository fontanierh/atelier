#include "GroundStateCorrections.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) { float value;std::memcpy(&value,&word,4);return value; }
float FlipSign(float value) { std::uint32_t word;std::memcpy(&word,&value,4);word^=0x80000000u;std::memcpy(&value,&word,4);return value; }
std::int32_t Add(std::int32_t value,std::int32_t delta)
{
    const auto word=std::uint32_t(value)+std::uint32_t(delta);
    std::int32_t result;std::memcpy(&result,&word,4);return result;
}
}
bool UpdateAntiFlipNudge(PhysicsGroundState& state,AntiFlipNudgeInput input,BoardForceQueue& queue,
    GroundCorrectionServices& services,AntiFlipNudgeResult& result,std::string& error)
{
    float squared;
    if(!services.GroundDot3(state.anti_flip_torque_2624,state.anti_flip_torque_2624,squared,error))return false;
    state.anti_flip_nudge_frames_2752=squared>0.0f?Add(state.anti_flip_nudge_frames_2752,1):0;
    if(state.anti_flip_nudge_frames_2752<=12||!(input.deck_speed_2652<Float(0x3f8ccccd)))
    {result={false,false};return true;}
    auto direction=input.deck_axis_96;
    if(direction[1]>0.0f)for(auto& lane:direction)lane=FlipSign(lane);
    direction[1]=0.0f;
    if(!services.GroundDot3(direction,direction,squared,error))return false;
    if(!(squared>Float(0x3a83126f))){result={false,false};return true;}
    Vec4 force;
    if(!services.GroundScaleToMagnitude(direction,squared,50.0f,force,error))return false;
    const bool queued=queue.Append({17,{force[0],force[1],force[2]}, {}});
    state.anti_flip_nudge_applied_2723=true;result={true,queued};return true;
}
bool ManageHangUps(PhysicsGroundState& state,HangUpInput input,GroundCorrectionServices& services,std::string& error)
{
    const bool investigating=(input.flags_1516&0x08000000u)!=0;
    if(investigating)
    {
        if(input.deck_speed_2652<Float(0x3f8ccccd)&&input.scalar_84<Float(0x3f666666)&&input.scalar_84>0.0f)
            state.hang_detection_frames_2740=Add(state.hang_detection_frames_2740,1);
    }
    else state.hang_detection_frames_2740=0;
    if(state.hang_detection_frames_2740==20)
    {
        state.hang_force_frames_2744=10;Vec4 force;
        if(!services.BuildHangForce(force,error))return false;
        state.vector_2608=force;
    }
    if(state.hang_force_frames_2744>0)
    {
        if(investigating&&!services.ApplyHangForce(state.vector_2608,error))return false;
        state.hang_force_frames_2744=Add(state.hang_force_frames_2744,-1);
        if(state.hang_force_frames_2744==0)state.hang_detection_frames_2740=0;
    }
    const bool candidate=input.deck_speed_2652<Float(0x3f8ccccd)
        &&(input.flags_1516&0x0c000000u)==0x0c000000u&&input.geometry_axis_dot_positive;
    bool hung=false;
    if(candidate&&!services.DetectHungUpGeometry(hung,error))return false;
    state.hung_wipeout_frames_2748=hung?Add(state.hung_wipeout_frames_2748,1):0;
    if(state.hung_wipeout_frames_2748>20&&!services.RequestHungWipeout(error))return false;
    return true;
}
bool ManageHalfpipeWheelCatches(HalfpipeWheelCatchInput input,GroundCorrectionServices& services,bool& applied,std::string& error)
{
    const bool candidate=(input.flags_1516&0x08000000u)!=0&&input.deck_speed_2652<3.0f
        &&std::abs(input.deck_x_axis_y)<Float(0x3f11eb85)&&std::abs(input.deck_y_axis_y)<Float(0x3df5c28f)
        &&input.signed_deck_distance<Float(0x3de147ae)&&input.signed_deck_distance>0.0f;
    if(!candidate){applied=false;return true;}
    Vec4 displacement;
    if(!services.WheelCatchDisplacement(displacement,error))return false;
    if(!services.ApplyWheelCatchDisplacement(displacement,error))return false;
    applied=true;return true;
}
bool ConsiderGroundPinning(PhysicsGroundState& state,PinningInput input,GroundCorrectionServices& services,std::string& error)
{
    if(input.flags_2488&1u){state.pinning_2727=false;state.was_pinning_2728=false;return true;}
    if(state.human_player_2724&&input.frames_since_teleport_2584<90)
    {
        const bool eligible=state.was_pinning_2728||input.frames_since_teleport_2584<30;
        const bool controls_seen=input.frames_since_teleport_2584>0&&(input.flags_2472&0x00800000u)==0;
        state.controls_latched_2725|=controls_seen;
        if(eligible&&state.captured_position_valid_2726&&!state.controls_latched_2725)
        {
            if(!services.PinToCapturedPosition(state.captured_position_x_2656,state.captured_position_z_2660,error))return false;
            state.pinning_2727=true;
        }
    }
    state.was_pinning_2728=state.pinning_2727;return true;
}
}
