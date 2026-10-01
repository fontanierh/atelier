// SPDX-License-Identifier: Apache-2.0
#include "GrindRuntimeSettings.h"
#include "StockSettingsReader.h"
#include <cmath>
#include <cstring>
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {float Value(std::uint32_t word) {float v;std::memcpy(&v,&word,4);return v;}}
bool GrindSubstateSettings::Vertical(PlayerGrindFamily family,std::uint32_t mode,float strength,float& output,std::string& error) const
{
    if(mode>=vertical.size()) {error="Invalid grind jump physics mode "+std::to_string(mode);return false;}
    const std::size_t group=family==PlayerGrindFamily::Boardslide?1:family==PlayerGrindFamily::Tipslide?2:0;
    const auto pair=vertical[mode][group];output=std::fma(1.0f-strength,pair[0],pair[1]*strength);return true;
}
float GrindGeometrySideJump(PlayerGrindFamily family,std::uint32_t kind)
{
    switch(family) {
    case PlayerGrindFamily::Boardslide:case PlayerGrindFamily::Darkslide:return kind==2?Value(0x3f666666):0.0f;
    case PlayerGrindFamily::Backslash:return Value(0x3f666666);
    default:return Value(0x3f000000);
    }
}
bool GrindRuntimeSettings::Load(const SettingsDatabase& data,GrindRuntimeSettings& output,std::string& error)
{
    StockSettingsReader r(data);GrindRuntimeSettings s{};std::vector<std::uint32_t> pin,exit,words;
    if(!r.Words("physics_grinds","default","PinVsSlope",8,pin,error))return false;
    if(!r.Words("physics_grinds","default","ExitAssistVsLeanAngle",12,exit,error))return false;
    float drag;if(!r.Float("physicsdeck","default","DeckAngularDrag",drag,error))return false;
    s.standard_angular_drag=drag*Value(0x426fffff);
    for(std::size_t i=0;i<4;++i) {s.pin_vs_slope.x[i]=Value(pin[i]);s.pin_vs_slope.y[i]=Value(pin[4+i]);}
    if(!r.Float("physics_grinds","default","GrindLookAheadScalar",s.look_ahead,error))return false;
    for(std::size_t i=0;i<4;++i) {s.exit_assist.x[i]=Value(exit[4+i]);s.exit_assist.y[i]=Value(exit[8+i]);}
    if(!r.Float("physics_wipeout","default","Wipeout_GroundSkeletonMaxContactArms",s.post.max_arm_contact_164,error))return false;
    if(!r.Float("physics_wipeout","default","Wipeout_GroundSkeletonMaxContact",s.post.max_body_contact_168,error))return false;
    if(!r.Float("physics_wipeout","default","Wipeout_GrindXZDeck",s.post.xz_acceleration_204,error))return false;
    if(!r.Float("physics_wipeout","default","Wipeout_GrindSkeletonMaxDisp",s.post.max_displacement_208,error))return false;
    if(!r.Float("physics_wipeout","default","Wipeout_GrindMaxAngularDeckError",s.post.max_angular_deck_error_212,error))return false;
    if(!r.Words("physics_reckoning","default","GroundNormalSmoothing",4,words,error))return false;
    for(std::size_t i=0;i<4;++i)s.reckoning.ground_normal_smoothing[i]=Value(words[i]);
    // This host loader reads exactly sixteen words; the general Curve8 reader
    // also accepts twenty-word layouts and has different malformed diagnostics.
    const auto graph=[&](const char* name,PointGraph<8>& output) {
        if(!r.Words("physics_reckoning","default",name,16,words,error))return false;
        for(std::size_t i=0;i<8;++i){output.x[i]=Value(words[i]);output.y[i]=Value(words[8+i]);}
        return true;
    };
    if(!graph("TiltVsRotGround",s.reckoning.tilt_vs_rotation))return false;
    if(!graph("TiltVsSlopeGround",s.reckoning.tilt_vs_slope))return false;
    if(!r.Words("physics_collision","default","CollisionTorqueVsAngle",20,words,error))return false;
    const char* modes[]={"easy","normal","hardcore","motorized","test"};
    const char* fields[][2]={{"Hash_3097A69281990652","Hash_FA4CDBAE0DFD1FAD"},{"Hash_B2B1170AFFC8AC69","Hash_1B3E9F9C836D287D"},{"Hash_703829BD711E54DE","Hash_F2473E9125079F0"}};
    for(std::size_t i=0;i<5;++i)for(std::size_t j=0;j<3;++j)for(std::size_t k=0;k<2;++k)
        if(!r.Float("physics_mode",modes[i],fields[j][k],s.substate.vertical[i][j][k],error))return false;
    if(!r.Float("physics_animation","default","MaxDeckZAxisYForAnimatedDeck",s.substate.animated_board_threshold,error))return false;
    auto& c=s.substate.collision;
    if(!r.Float("physics_collision","default","MaxVelDelta",c.maximum_velocity_delta,error))return false;
    if(!r.Float("physics_collision","default","ForceYOffset",c.force_y_offset,error))return false;
    if(!r.Float("physics_collision","default","CollisionForceScalar",c.force_scalar,error))return false;
    if(!r.Float("physics_collision","default","TargetDisplacementVel",c.target_displacement_velocity,error))return false;
    for(std::size_t i=0;i<8;++i) {c.torque_vs_angle.x[i]=Value(words[4+i]);c.torque_vs_angle.y[i]=Value(words[12+i]);}
    output=s;return true;
}
}
