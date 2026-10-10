#pragma once
#include "BoardTypes.h"
#include "DriveFrames.h"

namespace atelier::skate
{
struct JointSettings
{
    float truck_twist_limit_degrees,truck_twist_angle_degrees,wheel_swing_limit_degrees;
    static JointSettings Stock();
};
struct JointRecord
{
    BoardBodyId definition_body_0,definition_body_1;
    std::array<std::uint32_t,16> parameters;
    std::array<std::uint32_t,20> frames;
    BoardBodyId LiveBodyA() const {return definition_body_1;}
    BoardBodyId LiveBodyB() const {return definition_body_0;}
};
// Registration order is two deck/truck joints followed by four truck/wheel joints.
std::array<JointRecord,6> JointRecords(JointSettings settings);
std::array<JointRecord,6> DefaultJointRecords();
}
