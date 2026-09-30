// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionSpecialConditions.h"
#include <array>
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
std::string DebugOptional(std::optional<std::string_view> text)
{
    if (!text) return "None";std::string out="Some(\"";
    for (unsigned char c:*text)
    {switch (c) {case 0:out+="\\0";break;case '\n':out+="\\n";break;case '\r':out+="\\r";break;case '\t':out+="\\t";break;
        case '\\':out+="\\\\";break;case '"':out+="\\\"";break;default:out+=char(c);break;}}
    return out+"\")";
}
}
bool MotionGraphPrelandingConditionSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const auto x=data.Field("anim_motion","body_tilt","overide_preland_x"),v=data.Field("anim_motion","body_tilt","overide_preland_velY");
    if (!x || !x->Float()) {error="Missing stock overide_preland_x";return false;}if (!v || !v->Float()) {error="Missing stock overide_preland_velY";return false;}
    override_x=*x->Float();override_velocity_y=*v->Float();error.clear();return true;
}
bool MotionGraphOverridePrelanding(const MotionGraphPrelandingInputs& p,const MotionGraphPrelandingConditionSettings& s)
{return p.air_444 || (p.air_normal_144_y<=.5f && std::abs(p.animation_16_x)>s.override_x && p.com_velocity_y>s.override_velocity_y);}
bool ParseGraphMotionSpecialCondition(const GraphAttributes& a,GraphMotionSpecialCondition& output,bool& recognized,std::string& error)
{
    GraphMotionSpecialCondition c;const auto name=a.Text("name").value_or("");c.numeric=ParseNumericCondition(a);using K=GraphMotionSpecialCondition::Kind;recognized=true;error.clear();
    if (name=="IsGrindBluntingBackslash") c.kind=K::GrindBlunting;
    else if (name=="IsGrindApproach") {c.kind=K::GrindApproach;c.value=EncodeAnimationName(a.Text("Facing").value_or("F"))==EncodeAnimationName("F");}
    else if (name=="GrindTrickOutTypeAllowed")
    {c.kind=K::GrindTrickOut;const auto type=a.Text("type");if (type=="normal") c.value=0;else if (type=="left") c.value=1;else if (type=="right") c.value=2;
        else {error="Invalid GrindTrickOutTypeAllowed type: "+DebugOptional(type);return false;}}
    else if (name=="IsLandingIntoGrind") c.kind=K::LandingIntoGrind;
    else if (name=="IsDroppingIn") c.kind=K::DroppingIn;
    else if (name=="HasLandingType") {c.kind=K::LandingType;const auto type=a.Text("landingType").value_or("straight");c.value=type=="spin"?2:type=="sketchy"?1:0;}
    else if (name=="HasTiltToLargeForPreland") c.kind=K::TiltForPreland;
    else if (name=="IsDoneWipingOut") c.kind=K::DoneWipingOut;
    else if (name=="WipeoutTimeToLand") c.kind=K::WipeoutTimeToLand;
    else if (name=="WipeoutTimeSinceContact") c.kind=K::WipeoutTimeSinceContact;
    else if (name=="GestureType")
    {c.kind=K::GestureType;const auto value=a.Text("gesture");const std::array<std::string_view,5> names{{"Freefall","CannonBall","JudoKick","SwanDive","Torpedo"}};
        bool found=false;for (std::size_t i=0;i<names.size();++i) if (value==names[i]) {c.value=std::uint32_t(i);found=true;break;}
        if (!found) {error="Invalid Wipeout gesture type "+DebugOptional(value);return false;}}
    else if (name=="IsInWater")
    {c.kind=K::InWater;const auto orientation=a.Text("orientation");if (orientation=="onback") c.value=0;else if (orientation=="onfront") c.value=1;else if (orientation=="either") c.value=2;
        else {error="Invalid water orientation "+DebugOptional(orientation);return false;}}
    else {recognized=false;output=std::move(c);return true;}
    output=std::move(c);return true;
}
bool GraphMotionSpecialCondition::Evaluate(const MotionSpecialConditionContext& c,bool& result,std::string& error) const
{
    using K=Kind;result=false;error.clear();
    if (kind>=K::GrindBlunting && kind<=K::DroppingIn)
    {if (!c.grind) {error="Grind condition requires completed physical output";return false;}const auto& p=*c.grind;
        switch (kind) {case K::GrindBlunting:result=p.blunting_136==4;break;case K::GrindApproach:result=p.filtered_grinding_80 && p.approach_268==value;break;
        case K::GrindTrickOut:result=p.trick_out_240==value;break;case K::LandingIntoGrind:result=p.air_grind_443 && p.air_time_184<.2f;break;
        case K::DroppingIn:result=p.dropping_in_324;break;default:break;}return true;}
    if (kind>=K::DoneWipingOut && kind<=K::InWater)
    {if (!c.wipeout) {error="Wipeout condition requires completed physical output";return false;}const auto& p=*c.wipeout;
        switch (kind) {case K::DoneWipingOut:result=p.over_599;break;case K::WipeoutTimeToLand:result=numeric.Matches(p.collision_time_144);break;
        case K::WipeoutTimeSinceContact:result=numeric.Matches(p.no_support_time_548);break;case K::GestureType:result=p.profile_148==value;break;
        case K::InWater:if (p.below_surface_82) {if (!p.orientation_y) {error="IsInWater requires skeleton output80.Y";return false;}result=std::uint32_t(!(*p.orientation_y>0))==value || value==2;}break;
        default:break;}return true;}
    if (kind==K::LandingType) {if (!c.landing) {error="HasLandingType requires Animation96";return false;}result=c.landing->kind==value;return true;}
    if (kind==K::TiltForPreland) {if (!c.prelanding) {error="HasTiltToLargeForPreland requires original prelanding output";return false;}result=MotionGraphOverridePrelanding(*c.prelanding,c.prelanding_settings);return true;}
    error="Unbound special MotionGraph condition";return false;
}
}
