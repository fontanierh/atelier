#include "OffboardGroundQueryMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
OffboardGroundGeometryResult InterpretOffboardGroundHits(const OffboardGroundPacket& packet,const std::array<std::optional<OffboardGroundLineHit>,7>& hits)
{
    using namespace offboard_ground_query;const auto side_raw=Cross({0,1,0},packet.tangent);auto side=Mul(side_raw,InverseRoot(Dot(Cross({0,1,0},packet.tangent),Cross({0,1,0},packet.tangent))));
    std::uint32_t kind;
    if((hits[0]&&hits[1])||hits[4])kind=3;
    else if(hits[0])kind=hits[2]&&!(hits[2]->fraction>=.65f)?2:1;
    else if(hits[1]){side=Mul(side,-1);kind=hits[3]&&!(hits[3]->fraction>=.65f)?2:1;}
    else kind=0;
    const auto flag28=(hits[0]&&(hits[0]->packed_surface&0x0f80)==0x0400)||(hits[1]&&(hits[1]->packed_surface&0x0f80)==0x0400);
    bool flag26=true,flag27=false;
    if(hits[6])
    {
        const auto& hit=*hits[6];const auto delta=Sub(hit.position,packet.center);const auto d=Dot(hit.face_normal,Unit(packet.tangent,{}));
        const auto rejected=d>0?Sub(hit.face_normal,Mul(packet.tangent,d)):hit.face_normal,normal=Unit(rejected,{});
        flag26=!(delta.y> -1);flag27=.9f>normal.y&&Dot(Horizontal(delta),normal)>0;
    }
    return {{side,packet.up,packet.tangent,packet.center},kind,flag26,flag27,flag28};
}
OffboardGroundAdjustment ConsumeOffboardGroundGeometry(OffboardGroundConsumeInput input,std::optional<OffboardGroundGeometryResult> geometry)
{
    using namespace offboard_ground_query;OffboardGroundAdjustment out;out.input_up_416=input.previous_input_up_416;bool nearby=false;
    if(geometry)
    {
        const auto& g=*geometry;const auto delta=Sub(g.frame.position,input.frame_80.position),horizontal=Horizontal(delta);
        nearby=.3f>std::abs(delta.y)&&Bits(0x3d23d70b)>Dot(horizontal,horizontal)&&std::abs(Dot(g.frame.forward,input.frame_80.forward))>.9f;
        if(!g.flag28&&input.reach_364>Length(horizontal)+.7f){out.state_752=g.kind==2&&g.frame.up.y>.98f;out.state_754=g.flag26||g.flag27;}
        if(g.kind==0||g.kind==1)out.state_753=!(std::abs(Dot(delta,g.frame.right))>.06f)&&!((input.contact_flags_368&0x10)!=0&&(input.contact_flags_368&0x20)!=0);
        if(out.state_752||out.state_753)out.frame_768=g.frame;
    }
    if(!out.state_753&&(input.contact_flags_368&1)!=0&&(input.contact_flags_368&0x38)==0)
    {
        const auto height=Dot(Sub(input.frame_80.position,input.contact_position_192),input.frame_80.up);
        if(!(height>=.06f)&&!(height<= -.02f)){out.state_753=true;out.frame_768=input.frame_80;out.frame_768.position=input.contact_position_192;}
    }
    if(nearby||out.state_753)
    {
        auto x=Horizontal(out.frame_768.right);const auto x_length=Length(x);
        if(!(x_length<=.001f))
        {
            x=Mul(x,Reciprocal(x_length));auto z=Sub(out.frame_768.forward,Mul(x,Dot(out.frame_768.forward,x)));const auto z_length=Length(z);
            if(!(z_length<=.001f)){z=Mul(z,Reciprocal(z_length));out.frame_768.right=x;out.frame_768.forward=z;out.frame_768.up=Cross(z,x);}
        }
        if(0>out.frame_768.up.y){out.frame_768.up=Mul(out.frame_768.up,-1);out.frame_768.right=Mul(out.frame_768.right,-1);}out.input_up_416=out.frame_768.up;
    }
    return out;
}
}
