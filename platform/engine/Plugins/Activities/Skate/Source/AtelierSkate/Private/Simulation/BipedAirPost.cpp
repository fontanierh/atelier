#include "BipedAirState.h"
#include "BipedAirMath.h"
#include "StockSettingsReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace biped_air_math;
namespace
{
void Collision(WipeoutRequests& requests,BipedAirThresholds t,WipeoutMode mode,const WipeoutFrame& f)
{
    if(mode.check_squash&&f.maximum_pose_error>t.squash)requests.Request(18,0);
    else if(HeightDot(f.pose_error,f.pose_error)<=t.displacement*t.displacement){if(CheckWipeoutRegionalForce(f,t.body_contact,t.arm_contact))requests.Request(0,0);}
    else requests.Request(1,0);
}
}
bool BipedAirChecks::Load(const SettingsDatabase& data,std::string& error)
{
    StockSettingsReader reader(data);BipedAirChecks next;
    const char* names[]={"Wipeout_AirMaxSquash","Wipeout_AirSkeletonMaxDisp","Wipeout_AirSkeletonMaxContact","Wipeout_AirSkeletonMaxContactArms","Wipeout_OB_MaxSquash","Wipeout_OB_Air_SkelMaxDisp","Wipeout_OB_Air_SkelMaxContact","Wipeout_OB_SkeletonMaxContactArms","Wipeout_OB_Air_MinSpeed"};
    float* fields[]={&next.skeleton_air.squash,&next.skeleton_air.displacement,&next.skeleton_air.body_contact,&next.skeleton_air.arm_contact,&next.offboard_air.squash,&next.offboard_air.displacement,&next.offboard_air.body_contact,&next.offboard_air.arm_contact,&next.offboard_min_speed};
    for(unsigned n=0;n<9;++n)if(!reader.Float("physics_wipeout","default",names[n],*fields[n],error))return false;
    *this=next;error.clear();return true;
}
void BipedAirState::PostPhysics(BipedAirPostInput i,const BipedAirChecks& settings,const WipeoutFrame& f,WipeoutMode mode,Vec4 root_velocity,WipeoutRequests& requests) const
{
    if((i.flags_2484&2)!=0)Collision(requests,settings.skeleton_air,mode,f);
    if(!result.valid_404&&i.state_timer_2664>offboard_air_math::Bits(0x3ff33333))requests.Request(26,0);
    if(flags_544_550[3])requests.Request(30,0);
    requests.mode=4;if(HeightDot(root_velocity,root_velocity)>settings.offboard_min_speed*settings.offboard_min_speed)Collision(requests,settings.offboard_air,mode,f);
    if((i.flags_2484&0x400)!=0&&time_remaining_444>offboard_air_math::Step())requests.Request(31,0);
    if(flags_544_550[5]&&result.velocity_288[1]<0)requests.Request(31,0);
    if(result.valid_404&&-HeightDot(result.normal_304,result.contact_velocity_320)>offboard_air_math::Bits(0x41473333)&&time_remaining_444<offboard_air_math::Bits(0x3e23d70a))requests.Request(33,0);
    if(time_remaining_444<=0&&!flags_544_550[6]){const float forward=HeightDot(i.forward_224,result.contact_velocity_320),side=HeightDot(i.side_192,result.contact_velocity_320);if(forward>20||side>4||forward<-2)requests.Request(31,0);}
    if(time_remaining_444<0&&flags_544_550[4])requests.Request(31,0);
    if(time_remaining_444>4&&(std::abs(i.input_2708)>.01f||std::abs(i.input_2704)>.01f))requests.Request(26,0);
}
}
