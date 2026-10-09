#pragma once
#include "GroundState.h"
#include "ForceQueue.h"
#include <string>
namespace atelier::skate
{
struct AntiFlipNudgeInput { float deck_speed_2652; Vec4 deck_axis_96; };
struct AntiFlipNudgeResult { bool attempted, queued; };
struct HangUpInput
{
    std::uint32_t flags_1516;
    float deck_speed_2652, scalar_84;
    bool geometry_axis_dot_positive;
};
struct HalfpipeWheelCatchInput
{
    std::uint32_t flags_1516;
    float deck_speed_2652, deck_x_axis_y, deck_y_axis_y, signed_deck_distance;
};
struct PinningInput
{
    std::uint32_t flags_2488;
    std::int32_t frames_since_teleport_2584;
    std::uint32_t flags_2472;
};
// Required physical/numerical call boundaries. Each successful call may publish
// effects immediately; a later error retains those effects and state writes.
class GroundCorrectionServices
{
public:
    virtual ~GroundCorrectionServices()=default;
    virtual bool GroundDot3(Vec4,Vec4,float&,std::string&)=0;
    virtual bool GroundScaleToMagnitude(Vec4,float,float,Vec4&,std::string&)=0;
    virtual bool BuildHangForce(Vec4&,std::string&)=0;
    virtual bool ApplyHangForce(Vec4,std::string&)=0;
    virtual bool DetectHungUpGeometry(bool&,std::string&)=0;
    virtual bool RequestHungWipeout(std::string&)=0;
    virtual bool WheelCatchDisplacement(Vec4&,std::string&)=0;
    virtual bool ApplyWheelCatchDisplacement(Vec4,std::string&)=0;
    virtual bool PinToCapturedPosition(float,float,std::string&)=0;
};
bool UpdateAntiFlipNudge(PhysicsGroundState&,AntiFlipNudgeInput,BoardForceQueue&,
    GroundCorrectionServices&,AntiFlipNudgeResult&,std::string&);
bool ManageHangUps(PhysicsGroundState&,HangUpInput,GroundCorrectionServices&,std::string&);
bool ManageHalfpipeWheelCatches(HalfpipeWheelCatchInput,GroundCorrectionServices&,bool& applied,std::string&);
bool ConsiderGroundPinning(PhysicsGroundState&,PinningInput,GroundCorrectionServices&,std::string&);
}
