// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionPhysicalConditions.h"
#include <array>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
std::string DebugString(std::string_view text)
{
    std::string out="\"";
    for (unsigned char c:text)
    {
        switch (c) {case 0:out+="\\0";break;case '\n':out+="\\n";break;case '\r':out+="\\r";break;case '\t':out+="\\t";break;
        case '\\':out+="\\\\";break;case '"':out+="\\\"";break;
        default:if (c<32 || c==127) {constexpr char digits[]="0123456789abcdef";out+="\\u{";if (c>=16) out+=digits[c>>4];out+=digits[c&15];out+='}';}else out+=char(c);break;}
    }
    out+='"';return out;
}
std::string DebugOptional(std::optional<std::string_view> text) {return text?"Some("+DebugString(*text)+")":"None";}
bool GameplayKind(GraphMotionPhysicalCondition::Kind kind)
{return kind>=GraphMotionPhysicalCondition::Kind::RetrievingBoard && kind<=GraphMotionPhysicalCondition::Kind::HandPlanting;}
bool StockKind(GraphMotionPhysicalCondition::Kind kind)
{return kind>=GraphMotionPhysicalCondition::Kind::CanLandOnBoard && kind<=GraphMotionPhysicalCondition::Kind::ApexReached;}
}
bool ParseGraphMotionPhysicalCondition(const GraphAttributes& a,GraphMotionPhysicalCondition& output,bool& recognized,std::string& error)
{
    GraphMotionPhysicalCondition c;const auto raw=a.Text("name").value_or("");const auto name=TrimMotionGraphName(raw);c.numeric=ParseNumericCondition(a);
    using K=GraphMotionPhysicalCondition::Kind;recognized=true;error.clear();
    const std::array<std::string_view,18> gameplay_names{{"IsRetrievingSkateboard","IsInBipedAir","IsHippyHurdling","PhysicsWantsRunout",
        "IsPhysicsWiping","IsBodyFlipping","PhysicsWantsWipeOut","IsBumped","IsGrabbingObject","OkToDoTrickOnStairs","IsEnteringSkitch",
        "IsSkitching","IsFootPlanting","ShouldPrepareOneFootAirForFootplant","HasNewHandPlantPos","ShouldPlayHandPlantAnim","IsMovingObject","IsHandPlanting"}};
    if (raw!=name) for (const auto family_name:gameplay_names) if (name==family_name)
    {error="Unknown gameplay condition "+std::string(raw);return false;}
    if (name=="IsRetrievingSkateboard") c.kind=K::RetrievingBoard;
    else if (name=="IsInBipedAir") c.kind=K::InBipedAir;
    else if (name=="IsHippyHurdling") c.kind=K::HippyHurdling;
    else if (name=="PhysicsWantsRunout") c.kind=K::WantsRunout;
    else if (name=="IsPhysicsWiping") c.kind=K::PhysicsWiping;
    else if (name=="IsBodyFlipping") c.kind=K::BodyFlipping;
    else if (name=="PhysicsWantsWipeOut") c.kind=K::WantsWipeout;
    else if (name=="IsBumped") c.kind=K::Bumped;
    else if (name=="IsGrabbingObject") c.kind=K::GrabbingObject;
    else if (name=="OkToDoTrickOnStairs") c.kind=K::TricksOnStairs;
    else if (name=="IsEnteringSkitch") c.kind=K::EnteringSkitch;
    else if (name=="IsSkitching") c.kind=K::Skitching;
    else if (name=="IsFootPlanting") c.kind=K::FootPlanting;
    else if (name=="ShouldPrepareOneFootAirForFootplant") c.kind=K::PrepareFootplant;
    else if (name=="HasNewHandPlantPos") c.kind=K::NewHandplantPosition;
    else if (name=="ShouldPlayHandPlantAnim")
    {c.kind=K::PlayHandplant;const auto phase=a.Text("anim");if (phase=="antic") c.value=2;else if (phase=="into") c.value=1;else if (phase=="out") c.value=0;
        else {error="Unauthored handplant animation phase "+DebugOptional(phase);return false;}}
    else if (name=="IsMovingObject") c.kind=K::MovingObject;
    else if (name=="IsHandPlanting")
    {c.kind=K::HandPlanting;const auto state=a.Text("state").value_or("");if (state=="air") c.value=0;else if (state=="ground") c.value=1;
        else {error="IsHandPlanting has unauthored state "+DebugString(state);return false;}
        const auto dir=a.Text("dir");c.direction=dir=="FS"?1:dir=="BS"?0:2;}
    else if (name=="TimeToLand") c.kind=K::TimeToLand;
    else if (name=="OBTimeToLand") c.kind=K::OffboardTimeToLand;
    else if (name=="OBTrajTime") c.kind=K::OffboardTrajectoryTime;
    else if (name=="LocoState")
    {c.kind=K::LocoState;const auto loco=a.Text("locostate");if (loco=="Stand") c.value=0;else if (loco=="Walk") c.value=1;else if (loco=="Run") c.value=2;else if (loco=="Sprint") c.value=3;
        else {error="Invalid stock LocoState locostate "+DebugOptional(loco);return false;}}
    else if (name=="GroundSlopeType")
    {c.kind=K::GroundSlopeType;const auto slope=a.Text("slopetype");if (!slope) {error="GroundSlopeType requires slopetype";return false;}
        const std::array<std::string_view,9> names{{"Flat","StairUpShallow","StairUpSteep","StairDnShallow","StairDnSteep","RampUpShallow","RampUpSteep","RampDnShallow","RampDnSteep"}};
        bool found=false;for (std::size_t i=0;i<names.size();++i) if (*slope==names[i]) {c.value=std::uint32_t(i);found=true;break;}
        if (!found) {error="Unknown GroundSlopeType slopetype "+std::string(*slope);return false;}}
    else if (name=="IsRidingGoofy") c.kind=K::RidingGoofy;
    else if (name=="IsBipedGroundThin") c.kind=K::BipedGroundThin;
    else if (name=="IsHoldingSkateboard") c.kind=K::HoldingBoard;
    else if (name=="IsStandingOnMovingObject") c.kind=K::StandingOnMovingObject;
    else if (name=="CanLandOnBoard") c.kind=K::CanLandOnBoard;
    else if (name=="DistToEdge") c.kind=K::DistanceToEdge;
    else if (name=="IsDeckFree") c.kind=K::DeckFree;
    else if (name=="IsBipedCommittedToMotion") c.kind=K::BipedCommitted;
    else if (name=="EnoughDistToObstacle") {c.kind=K::EnoughDistanceToObstacle;c.database=a.Text("db").value_or("");c.animation=a.Text("anim").value_or("");}
    else if (name=="CanBipedLand") c.kind=K::CanBipedLand;
    else if (name=="IsCrouchedEnoughForBlendToGrabCycle") c.kind=K::CrouchedEnough;
    else if (name=="TrucksOrDeckInContact") c.kind=K::TrucksOrDeckContact;
    else if (name=="PhysicsWantsManualExit") c.kind=K::ManualExit;
    else if (name=="ApexReached") c.kind=K::ApexReached;
    else if (name=="ComVelCompare") {c.kind=K::ComVelocity;const auto axis=a.Text("axis").value_or("0");const auto first=axis.empty()?0:axis.front();c.value=first=='x'||first=='X'?0:first=='y'||first=='Y'?1:first=='z'||first=='Z'?2:3;}
    else if (name=="SkateSlope") c.kind=K::SkateSlope;
    else if (name=="SurfaceSlope") c.kind=K::SurfaceSlope;
    else if (raw=="DisableDismount") c.kind=K::DisableDismount;
    else {recognized=false;output=std::move(c);return true;}
    // Original family dispatch recognizes a trimmed name but its secondary
    // parser still reads raw spelling. Preserve its ordinary error boundary.
    if ((c.kind==K::ComVelocity || c.kind==K::SkateSlope || c.kind==K::SurfaceSlope) && raw!=name)
    {error="Unknown riding condition "+std::string(raw);return false;}
    if (StockKind(c.kind) && raw!=name) {error="Original stock gameplay condition parser has an unreachable raw-name mismatch";return false;}
    output=std::move(c);return true;
}
bool GraphMotionPhysicalCondition::Evaluate(const MotionPhysicalConditionContext& c,bool& result,std::string& error) const
{
    using K=Kind;result=false;error.clear();const auto& physical=c.physical;const auto& input=physical.gameplay;
    if (GameplayKind(kind) && !input) {error="MotionGraph requires the actual physical condition publication";return false;}
    if (StockKind(kind) && !input) {error="stock gameplay condition requires physical publication";return false;}
    switch (kind)
    {
    case K::RetrievingBoard:result=input->retrieving_board;break;
    case K::InBipedAir:result=input->in_biped_air;break;
    case K::HippyHurdling:result=input->hippy_hurdling;break;
    case K::WantsRunout:result=input->wants_runout;break;
    case K::PhysicsWiping:result=input->physics_wiping;break;
    case K::BodyFlipping:result=input->body_flipping;break;
    case K::WantsWipeout:result=input->wants_wipeout;break;
    case K::Bumped:result=input->bumped;break;
    case K::GrabbingObject:result=input->grabbing_object;break;
    case K::TricksOnStairs:result=!input->tricks_blocked_on_stairs;break;
    case K::EnteringSkitch:result=!(input->time_to_skitch<0) && input->time_to_skitch<=input->skitch_transition_time;break;
    case K::Skitching:result=input->state==104;break;
    case K::FootPlanting:result=input->footplant_active && input->footplant_duration>=0;break;
    case K::PrepareFootplant:result=input->footplant_contact_time>=.1f && input->footplant_contact_time<=.5f;break;
    case K::NewHandplantPosition:result=(input->handplant_flags&0x40000000)!=0;break;
    case K::PlayHandplant:
    {const auto threshold=input->handplant_thresholds[value];result=input->handplant_time-Float(0x3c888889)<(value==0?-threshold:threshold);break;}
    case K::MovingObject:result=input->moving_object;break;
    case K::HandPlanting:
        result=(value==0?input->state==600:(input->handplant_flags&0x80000000)!=0) &&
            (direction==2 || (direction==1 && (input->handplant_flags&0x20000000)!=0) || (direction==0 && (input->handplant_flags&0x20000000)==0));break;
    case K::TimeToLand:
        if (!input) {error="TimeToLand requires physical condition publication";return false;}
        result=input->time_to_land_valid && numeric.Matches(input->time_to_land);break;
    case K::OffboardTimeToLand:
        if (!input) {error="OBTimeToLand requires physical condition publication";return false;}
        result=numeric.Matches(input->offboard_time_to_land);break;
    case K::OffboardTrajectoryTime:
        if (!input) {error="OBTrajTime requires physical condition publication";return false;}
        result=input->offboard_trajectory_valid && numeric.Matches(input->offboard_trajectory_time);break;
    case K::LocoState:
        if (!physical.offboard_locomotion_state) {error="LocoState requires retained Biped locomotion through OffBoard84";return false;}
        result=*physical.offboard_locomotion_state==value;break;
    case K::GroundSlopeType:
        if (!physical.ground_slope_type) {error="GroundSlopeType requires the completed ground slope publication";return false;}
        result=*physical.ground_slope_type==value;break;
    case K::RidingGoofy:
        if (!physical.physical_stance) {error="IsRidingGoofy requires PhysOutAnimation stance bytes";return false;}
        result=physical.physical_stance->first==physical.physical_stance->second;break;
    case K::BipedGroundThin:
        if (!physical.biped_ground_thin) {error="IsBipedGroundThin requires the native ground geometry publication";return false;}
        result=*physical.biped_ground_thin;break;
    case K::HoldingBoard:result=physical.holding_board.value_or(false);break;
    case K::StandingOnMovingObject:
        if (!input) {error="IsStandingOnMovingObject requires the physical state publication";return false;}
        result=input->moving_object;break;
    case K::CanLandOnBoard:result=input->can_land_on_board;break;
    case K::DistanceToEdge:result=numeric.Matches(input->offboard_edge_distance);break;
    case K::DeckFree:
        if (!physical.free_board) {error="IsDeckFree requires completed OffBoard312";return false;}
        result=*physical.free_board;break;
    case K::BipedCommitted:result=input->offboard_committed_to_motion;break;
    case K::EnoughDistanceToObstacle:
    {float translation;if (!c.animation.StockClipTranslationZ(database,animation,translation,error)) return false;
        result=!(input->offboard_obstacle_distance<translation+Float(0x3e99999a));break;}
    case K::CanBipedLand:result=input->offboard_landing_normal[1]>.85f;break;
    case K::CrouchedEnough:
        if (!physical.animation_height_72) {error="Crouch condition requires physical animation height";return false;}
        result=*physical.animation_height_72<Float(0x3f19999a);break;
    case K::TrucksOrDeckContact:result=input->trucks_or_deck_contact;break;
    case K::ManualExit:
        if (!physical.manual_exit) {error="PhysicsWantsManualExit requires completed physical animation output";return false;}
        result=*physical.manual_exit;break;
    case K::ApexReached:result=input->reached_apex;break;
    case K::ComVelocity:case K::SkateSlope:case K::SurfaceSlope:
    {
        if (!c.riding) {error="MotionGraph requires the actual COM and slope publication";return false;}
        const auto& p=*c.riding;float scalar;
        if (kind==K::ComVelocity)
        {const Vec4 velocity{p.com_velocity[0],p.com_velocity[1],p.com_velocity[2],0};
            scalar=value==0?Dot3(velocity,Vec4{p.skeleton_x[0],p.skeleton_x[1],p.skeleton_x[2],0}):value==1?velocity[1]:
                value==2?Dot3(velocity,Vec4{p.skeleton_z[0],p.skeleton_z[1],p.skeleton_z[2],0}):Length3(velocity);}
        else scalar=90.0f-Asin(kind==K::SkateSlope?p.skate_up_y:p.surface_up_y)*Float(0x42652ee1);
        result=numeric.Matches(scalar);break;
    }
    case K::DisableDismount:
        if (!physical.conditions.push_brake) {error="DisableDismount requires actual Ground80 and Skeleton598";return false;}
        result=Float(0x3f23d70a)>physical.conditions.push_brake->ground_axis_y || physical.conditions.push_brake->skeleton_disables_push_brake;break;
    case K::Unsupported:error="Unbound physical MotionGraph condition";return false;
    }
    return true;
}
}
