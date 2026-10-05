// SPDX-License-Identifier: Apache-2.0
#include "OffboardControllerMath.h"
#include "GravityScale.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void BipedContactCorrection::Update(BipedContactInput input)
{
    using namespace biped_math;
    displacement={};const auto a=input.collision_displacements[0],b=input.collision_displacements[1];
    const auto square_a=Dot3(a,a),square_b=Dot3(b,b);const auto selected=square_a>square_b?a:b;
    const auto maximum=Select(square_a-square_b,square_a,square_b);active=false;
    if(!(maximum<=Bits(0x38d1b717)))
    {
        direction=Mul(selected,Inverse(Dot3(selected,selected)));active=true;
        const auto excess=Root(maximum)-Bits(0x3d4ccccd),positive=Select(excess,excess,0);
        Vec4 change{};for(std::size_t n=0;n<4;++n)change[n]=(direction[n]*positive)*.5f;
        const auto projection=Dot3(input.projection_axis_416,change);
        change=Sub(change,Mul(input.projection_axis_416,projection));
        // Contact correction uses native_arithmetic::dot3 for its length.
        const auto length=Root(Dot3(change,change));
        if(length>=Bits(0x37800000))
        {
            const auto bounded=Select(Bits(0x3dcccccd)-length,length,Bits(0x3dcccccd));auto inverse=ReciprocalEstimate(length);
            for(unsigned n=0;n<2;++n)inverse=std::fma(inverse,std::fma(-inverse,length,1.0f),inverse);
            for(auto& value:change)value=(value*bounded)*inverse;
        }
        displacement=change;
    }
    displacement=Sub(displacement,Mul(input.up_axis_16,Dot3(input.up_axis_16,displacement)));
}
void BipedSpecialMode::Update(float movement,std::uint32_t flags,float forward_y)
{
    using namespace biped_math;
    if(enabled_714){elapsed_788+=Step();if(!(movement>=.5f)||(!(elapsed_788<=.5f)&&(flags&0x200)==0))enabled_714=false;}
    else if(!(elapsed_788<=0)){if(Bits(0x3e19999a)>forward_y)elapsed_788=0;}
    else if((flags&0x200)!=0){elapsed_788=0;enabled_714=true;}
}
namespace
{
Vec4 SlidingUnit(Vec4 v)
{
    const auto square=Dot3(v,v),inverse=biped_math::Inverse(square),length=biped_math::Root(square);
    return length>biped_math::Bits(0x358637bd)?biped_math::Mul(v,inverse):Vec4{};
}
Vec4 SlidingClamp(Vec4 v,float maximum)
{
    const auto length=biped_math::Root(Dot3(v,v));if(!(length>=biped_math::Bits(0x37800000)))return v;
    const auto bounded=biped_math::Select(maximum-length,length,maximum);auto inverse=ReciprocalEstimate(length);
    for(unsigned n=0;n<2;++n)inverse=std::fma(inverse,std::fma(-inverse,length,1.0f),inverse);
    for(auto& x:v)x=(x*bounded)*inverse;return v;
}
Vec4 ClampSurfaceAxis(Vec4 value,Vec4 axis,float low,float high)
{
    const auto projection=biped_math::Dot(value,axis);
    return biped_math::Madd(axis,biped_math::Clamp(projection,low,high),biped_math::Sub(value,biped_math::Mul(axis,projection)));
}
}
void BipedSliding::Update(BipedSlidingInput input,const PointGraph<8>& slope,const PointGraph<8>& speed)
{
    using namespace biped_math;
    if(input.special_mode_714)return;
    const Vec4 down{0,-1,0,0};const auto downhill=Sub(down,Mul(input.surface_normal_560,Dot3(input.surface_normal_560,down)));
    const auto tilt=-downhill[1],lower=Select(-tilt,0,tilt),amount=Select(1.0f-lower,lower,1);
    auto uphill=SlidingUnit(downhill);for(auto& value:uphill)value=-value;
    const auto current_speed=Dot3(input.movement_velocity_480,uphill);
    const auto factor=-(slope.Evaluate(amount)*speed.Evaluate(current_speed));
    const auto acceleration=SlidingClamp(Mul(downhill,(Bits(0xc11ccccd)*GravityScale())*factor),5);
    velocity_528=Madd(acceleration,Bits(0x3d4ccccd),Mul(velocity_528,.95f));const auto threshold=Bits(0x3c23d70b);
    if(threshold>Dot3(acceleration,acceleration))velocity_528=Mul(velocity_528,.9f);
    if(input.contact_direction_400)
    {
        const auto direction=Mul(*input.contact_direction_400,-1);const auto projection=Dot3(velocity_528,SlidingUnit(direction));
        if(projection>0)velocity_528=Sub(velocity_528,Mul(direction,projection));
    }
    active_710=Dot3(velocity_528,velocity_528)>threshold;
}
void BipedSurfaceState::UpdateSurface(const BipedSurfaceInput& input)
{
    using namespace biped_math;const Vec4 up{0,1,0,0};if((input.flags&1)==0)return;
    source_normal=input.normal;auto target=input.normal;
    if((input.flags&4)!=0)
    {
        const auto delta=Sub(input.edge_point,input.origin),right=UnitOr(Cross(up,delta),{});
        const auto candidate=UnitOr(Cross(delta,right),input.normal);const auto limit=45.0f*Bits(0x3c8efa35);
        const auto first=LimitAngle(candidate,input.normal,limit),second=LimitAngle(input.edge_normal,input.normal,limit);
        const auto lateral=Mul(right,Dot(right,input.normal));target=UnitOr(Sub(input.normal,lateral),up);
        if(first[1]>target[1])target=first;if(second[1]>target[1])target=second;
        const auto remaining=Clamp(1.0f-Dot(lateral,lateral),0,1);target=Madd(target,Root(remaining),lateral);
    }
    const auto angle=std::abs(WrapAngle(UnsignedAngle(surface_normal,target)));
    if(angle<Bits(0x3f490fdb)||target[1]>Bits(0x3f35c28f))surface_normal=UnitOr(Madd(surface_normal,.5f,Mul(target,.5f)),surface_normal);
}
void BipedSurfaceState::UpdateSpring(const BipedSpringInput& input)
{
    using namespace biped_math;const Vec4 up{0,1,0,0};const auto blend=Clamp(Length(input.velocity)*.125f,0,1);
    const auto candidate=Madd(surface_normal,blend,Mul(up,1.0f-blend));
    const auto limited=LimitAngle(candidate,surface_normal,36.0f*Bits(0x3c8efa35)),target=UnitOr(limited,input.up);
    auto desired=Mul(Sub(target,spring_normal),Bits(0x3e4ccccd));desired=ClampSurfaceAxis(desired,input.spring_right,Bits(0xbccccccd),Bits(0x3ccccccd));
    auto acceleration=Sub(desired,spring_delta);acceleration=ClampSurfaceAxis(acceleration,input.spring_right,Bits(0xbbc49ba6),Bits(0x3bc49ba6));
    acceleration=ClampSurfaceAxis(acceleration,input.spring_forward,Bits(0xbd4ccccd),Bits(0x3d4ccccd));
    spring_delta=biped_math::Add(spring_delta,acceleration);spring_normal=UnitOr(biped_math::Add(spring_normal,spring_delta),spring_normal);
    const auto lean_target=input.suppress_lean?Vec4{}:Madd(input.forward,input.forward_delta*Bits(0x3d23d70a),Mul(input.right,input.right_delta*Bits(0x3f333333)));
    lean=Madd(lean_target,Bits(0x3d4ccccd),Mul(lean,Bits(0x3f733333)));final_up=UnitOr(biped_math::Add(lean,spring_normal),spring_normal);
}
void BipedFrameOutput::Update(Vec4 forward,Vec4 up,Vec4 projection,Vec4 position)
{
    using namespace biped_math;
    const auto cross=Cross(up,forward);const auto right=Mul(cross,Inverse(Dot3(cross,cross)));
    const auto front=Cross(right,projection);const auto normalized_front=Mul(front,Inverse(Dot3(front,front)));
    frame=OrthonormalizeSkeletonFrame(Mat4{{right,up,normalized_front,frame[3]}});
    Vec4 change{};for(std::size_t n=0;n<4;++n)change[n]=(position[n]-frame[3][n])*60.0f-velocity[n];
    change[1]=Select(change[1]- -1.0f,change[1],-1);velocity=biped_math::Add(velocity,change);frame[3]=Madd(velocity,Step(),frame[3]);
}
void UpdateBipedPosition(Vec4& position,BipedPositionInput input)
{
    using namespace biped_math;const auto up=input.projection_axis_416;auto origin=input.previous_origin_112;
    if(input.use_override_711)origin=input.override_origin_592;
    else if((input.contact_flags_176&1)!=0&&Dot3(Sub(input.contact_origin_0,origin),up)>0)origin=input.contact_origin_0;
    if((input.contact_flags_176&2)!=0)
    {
        const auto contact_height=Dot3(Sub(input.contact_origin_96,origin),up),frame_height=Dot3(Sub(input.frame_position_176,origin),up);
        auto height=Select(contact_height-frame_height,contact_height,frame_height);height=Select(height-.3f,.3f,height);
        if(!(height<=0))origin=Madd(up,height,origin);
    }
    const auto delta=Sub(input.animation_position_272,origin);const auto projection=Dot3(up,delta);const auto planar=Sub(delta,Mul(up,projection));
    const auto target=Madd(up,.95f,biped_math::Add(origin,planar)),change=Sub(target,position);const auto height=Dot3(change,up);
    const auto lower=Select(-.1f-height,-.1f,height),bounded=Select(.1f-lower,lower,.1f),correction=bounded-height;
    position=biped_math::Add(position,Madd(up,correction,change));
}
}
