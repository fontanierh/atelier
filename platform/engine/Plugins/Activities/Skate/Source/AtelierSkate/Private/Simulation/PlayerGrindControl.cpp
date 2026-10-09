#include "PlayerGrindControl.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
static float Clamp(float value,float low,float high){if(value<low)return low;if(value>high)return high;return value;}
static float Deadzone(float v){return v>.25f?(v-.25f)*(4.0f/3.0f):v<-.25f?(v+.25f)*(4.0f/3.0f):0;}
void PlayerGrindControl::Update(std::uint32_t kind,Vec4 forward,Vec4 normal,bool front,bool switched,bool hanging,
    float translation,float nudge,float up_down,float grab)
{
    float target_yaw=0,target_pitch=0;bool modified=false;
    if(kind==0)target_pitch=up_down*up_down*up_down;
    else if(kind==3){const bool selected=front!=switched;const auto tilt=Dot3(normal,forward);
        const auto height=(selected?-tilt:tilt)*(switched?-1.0f:1.0f);auto input=up_down;
        if(height>0&&std::abs(up_down)<=.01f&&height>-.25f)input=selected?-.71f:.71f;
        auto target=input;
        if(std::abs(tilt)>.26f)target=selected?VectorMin(input,0):VectorMax(input,0);
        if(height<-.25f)target=selected?VectorMax(input,0):VectorMin(input,0);
        const auto sign=(front?1.0f:-1.0f)*(switched?-1.0f:1.0f);
        if(grab>0&&height<=grab){const auto value=(grab-height)*sign*10;target=sign>0?VectorMin(value,sign):VectorMax(value,sign);}
        if(hanging)target=Clamp(target+sign*.5f,-1,1);
        const auto y=Clamp(std::fma(Deadzone(translation),.85f,Deadzone(nudge)*.79f),-.85f,.85f);
        target_yaw=y*y*y;target_pitch=target*target*target;modified=target!=input;
    }
    const auto response=modified?.76f:.91f;yaw=std::fma(yaw,.91f,target_yaw*F(0x3db851e8));
    pitch=std::fma(1-response,target_pitch,pitch*response);
    if(std::abs(yaw)<.0001f)yaw=0;if(std::abs(pitch)<.0001f)pitch=0;
}
Vec4 PlayerGrindControlRotate(Vec4 axis,Vec4 value,float angle)
{
    const auto sc=SinCos(angle*.5f);const auto q=Scale4(axis,sc.first);
    return Add(value,Scale4(Cross3(q,Add(Scale4(value,sc.second),Cross3(q,value))),2));
}
Mat4 PlayerGrindTruckFrame(Mat4 board,Vec4 normal,const PlayerGrindControl& control,bool switched)
{
    auto forward=PlayerGrindControlRotate(normal,board[2],control.yaw*-.68f);const auto right0=Cross3(normal,forward);
    const auto length=std::sqrt(Dot3(right0,right0));if(length<=.001f)return board;
    const auto right=Scale4(right0,1/length);forward=PlayerGrindControlRotate(right,forward,control.pitch*(switched?-.68f:.68f));
    return {right,Cross3(forward,right),forward,board[3]};
}
Mat4 PlayerGrindTipFrame(Mat4 board,Vec4 direction,Vec4 normal,Vec4 point,bool backslash)
{
    const auto across=Cross3(direction,normal);const auto axis=Scale4(direction,Dot3(across,Sub(board[3],point))>0?-1.0f:1.0f);
    const auto up=PlayerGrindControlRotate(axis,normal,F(backslash?0x3f3ba866:0x3eb2b8c3));
    const auto right=Scale4(direction,Dot3(direction,board[0])>0?1.0f:-1.0f);return {right,up,Cross3(right,up),board[3]};
}
}
