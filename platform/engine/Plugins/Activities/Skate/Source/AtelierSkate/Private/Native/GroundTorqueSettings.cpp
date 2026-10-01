// SPDX-License-Identifier: Apache-2.0
#include "GroundTorqueSettings.h"
#include <cstring>
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t w) {float f;std::memcpy(&f,&w,4);return f;}
bool Scalar(const SettingsDatabase& data,std::string_view c,std::string_view k,std::string_view n,float& output,std::string& error)
{
    const auto identity=std::string(c)+"/"+std::string(k)+"/"+std::string(n);const auto field=data.Field(c,k,n);
    if (!field) {error="Missing stock field "+identity;return false;}
    const auto value=field->Float();if (!value) {error="Expected finite stock float "+identity;return false;}
    output=*value;return true;
}
template<std::size_t N> bool Curve(const SettingsDatabase& data,std::string_view c,std::string_view n,PointGraph<N>& output,std::string& error)
{
    const auto identity=std::string(c)+"/default/"+std::string(n);const auto field=data.Field(c,"default",n);
    if (!field) {error="Missing stock field "+identity;return false;}
    const std::uint32_t* words=nullptr;std::size_t prefix=0;
    if (!field->Words(N*2,words))
    {
        if constexpr (N==8) {if (field->Words(20,words)) prefix=4;else {error="Invalid native eight-point graph "+identity;return false;}}
        else {error="Expected 32 stock graph words "+identity;return false;}
    }
    for (std::size_t i=0;i<N;++i) {output.x[i]=Word(words[prefix+i]);output.y[i]=Word(words[prefix+N+i]);}return true;
}
}
bool GroundTorqueSettings::Load(const SettingsDatabase& data,std::string_view surface,std::string& error)
{
    GroundTorqueSettings s;const auto f=[&](std::string_view c,std::string_view n,float& v){return Scalar(data,c,"default",n,v,error);};const auto p=[&](std::string_view n,float& v){return Scalar(data,"physics_surfaces",surface,n,v,error);};
    if (!Curve(data,"physics_friction","SlideVsNormal",s.slide.angle_response,error)||!Curve(data,"physics_friction","SlideVsSpeed",s.slide.speed_response,error)||!Curve(data,"physics_heading","SideFrictionFactor",s.slide.time_response,error)||!f("physicswheels","SoftestWheelSideFrictionScalar",s.slide.scalar_516)||!p("StraightenOut_ForceTime",s.slide.heading_time_limit)||!p("SideFriction_Scalar",s.slide.friction)||
        !Curve(data,"physics_heading","StraightenOutForce",s.straighten.time_response,error)||!f("physics_heading","StraightenMaxTurnInput",s.straighten.opposite_turn_limit)||!f("physicswheels","SoftestWheelStraightenOutTimeScalar",s.straighten.time_scalar)||!p("StraightenOut_ForceTime",s.straighten.heading_time_limit)||!p("StraightenOut_Scalar",s.straighten.strength)||
        !f("physics_manual","SpinNoLiftScalar",s.heading.manual_wrong_wheel_scalar)||!f("physics_manual","ManualSpinBlendSpeed",s.heading.manual_damping)||!f("physics_heading","HeadingAdjustMaxSpeed",s.heading.speed_max)||!f("physics_heading","HeadingAdjustFactor",s.heading.heading_strength)||!f("physics_heading","TurnTorqueScalar",s.heading.turn_strength)||!Curve(data,"physics_heading","TurnTorqueVsNegAngVel",s.heading.angular_response,error)||!Curve(data,"physics_manual","SpinVsSpeed",s.heading.manual_response,error)||!Curve(data,"physics_heading","HeadingAdjustVsSlope",s.heading.inclination_response,error)||!Curve(data,"physics_heading","HeadingAdjustVsSpeed",s.heading.speed_response,error)||
        !Curve(data,"physics_feet","AntiFlipTorqueX",s.anti_flip.axis_96_response,error)||!Curve(data,"physics_feet","AntiFlipTorqueZ",s.anti_flip.axis_64_response,error)) return false;
    s.heading.normal_threshold.fill(Word(0x358637bd));s.anti_flip.normal_threshold=s.heading.normal_threshold;*this=std::move(s);error.clear();return true;
}
}
