#include "BipedAirState.h"
#include "BipedAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace offboard_air_math;
namespace{Vec4 RemovePositive(Vec4 value,Vec4 direction){const float component=Dot(value,UnitOr(direction,{}));return component>0?Sub(value,Mul(direction,component)):value;}}
BipedAirResponse BipedAirState::CollisionResponse(std::array<Vec4,2> errors,Vec4 up,bool allowed)
{
    std::array<float,2> vertical,residual,sizes;std::array<Vec4,2> planar;
    for(unsigned n=0;n<2;++n){vertical[n]=std::abs(Dot(errors[n],up));auto component=Mul(up,vertical[n]);for(float& lane:component)lane=std::abs(lane);residual[n]=Length(Sub(errors[n],component));planar[n]={errors[n][0],0,errors[n][2],errors[n][0]};sizes[n]=Length(planar[n]);}
    BipedAirResponse response{vertical[0]>.2f||vertical[1]>.2f||residual[0]>.2f||residual[1]>.2f,std::nullopt};
    if(!(sizes[0]>.01f||sizes[1]>.01f))return response;
    if(flags_544_550[6]){flags_544_550[3]=true;return response;}
    const auto normal=Unit(sizes[0]>sizes[1]?planar[0]:planar[1]);const auto velocity=result.velocity_288;
    if((sizes[0]>.01f||sizes[1]>.01f)&&Dot(normal,velocity)<-10)flags_544_550[3]=true;
    if(!(Dot(velocity,normal)<0))return response;
    const bool above=result.scalar_392>frame_208[3][1]&&result.normal_304[1]>.7f;
    if(allowed&&!above)response.restart=normal;return response;
}
OffboardAirLaunchPacket BipedAirState::RestartPacket(OffboardAirLaunchPacket packet,Vec4 normal,Vec4 position,Vec4 up,float height)
{
    flags_544_550[2]=true;const auto first=RemovePositive(result.velocity_288,Mul(normal,-1)),second=RemovePositive(first,Mul(normal,-1));
    packet.velocity_0=Madd(normal,1,second);packet.board_position_80=Madd(up,height,position);packet.position_32=Madd(packet.velocity_0,Step(),position);
    packet.has_board_position_116=true;restart_normal_528=normal;return packet;
}
void BipedAirState::FinishRestart(Mat4 frame,Vec4 normal){frame_452=0;flags_544_550[0]=false;flags_544_550[1]=false;frame_80=frame;initial_up_480=normal;}
void BipedAirState::CorrectRestartedSample()
{if(flags_544_550[2]){const auto step=Mul(result.velocity_288,Step());result.position_272=Add(Sub(result.position_272,step),RemovePositive(step,Mul(restart_normal_528,-1)));}}
}
