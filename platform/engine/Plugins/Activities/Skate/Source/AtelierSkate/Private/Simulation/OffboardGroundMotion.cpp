#include "OffboardControllerMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Mat4 UpdateBipedSupport(BipedGroundMotionState& s,const BipedGroundMotionInput& i)
{
    using namespace biped_math;auto delta=SkeletonIdentity;const Vec4 up{0,1,0,0};
    if((i.contact_flags_176&1)==0)return delta;
    if(s.support_id_352!=i.contact_id_180)
    {
        if(s.support_velocity_removed_715){s.velocity_480=biped_math::Add(s.velocity_480,s.predicted_support_velocity_272);s.speed_704=Length(s.velocity_480);}
        s.support_yaw_336=0;s.previous_support_yaw_340=0;s.predicted_support_yaw_344=0;s.support_acceleration_304={};
        s.predicted_support_velocity_272={};s.support_velocity_256={};s.support_id_352=i.contact_id_180;s.support_velocity_removed_715=false;
    }
    else
    {
        delta=Compose(InverseSkeletonRigid(s.previous_support_frame_192),i.contact_frame_32);
        const auto moved=TransformPoint(s.frame_0[3],delta),velocity=Mul(Sub(moved,s.frame_0[3]),Reciprocal(Step()));
        const auto acceleration=Madd(Sub(velocity,s.support_velocity_256),Reciprocal(Step()),s.support_acceleration_304);
        s.support_acceleration_304=Mul(acceleration,Bits(0x3f733333));s.support_velocity_256=velocity;
        s.predicted_support_velocity_272=biped_math::Add(velocity,Sub(velocity,s.previous_support_velocity_288));s.previous_support_velocity_288=velocity;
        const auto rotated=TransformVector(s.frame_0[2],delta),flat=Sub(rotated,Mul(up,Dot(rotated,up))),direction=UnitOr(flat,{});
        const auto sine=Clamp(Dot(Cross(s.frame_0[2],direction),up),-1,1),yaw=Asin(sine)*Bits(0x426fffff);
        s.support_yaw_336=yaw;s.predicted_support_yaw_344=std::fma(yaw,2.0f,-s.previous_support_yaw_340);s.previous_support_yaw_340=yaw;
        if(Dot(s.predicted_support_velocity_272,s.predicted_support_velocity_272)>Bits(0x3a83126f)&&!s.support_velocity_removed_715)
        {s.velocity_480=biped_math::Add(s.velocity_480,Mul(s.predicted_support_velocity_272,-1));s.support_velocity_removed_715=true;s.speed_704=Length(s.velocity_480);}
    }
    const auto& f=i.reference_frame_128;
    const Mat4 columns{{{f[0][0],f[1][0],f[2][0],0},{f[0][1],f[1][1],f[2][1],0},{f[0][2],f[1][2],f[2][2],0},{0,0,0,0}}};
    auto local=TransformVector(s.support_acceleration_304,columns);local[1]=0;if(i.mirrored_292){local[0]*=-1;local[2]*=-1;}
    auto request=Mul(local,Bits(0x3ccccccd));const auto magnitude=Length(request);if(!(magnitude<=1))request=Mul(request,1.0f/magnitude);
    s.filtered_local_acceleration_320=Madd(request,Bits(0x3d23d70a),Mul(s.filtered_local_acceleration_320,Bits(0x3f75c28f)));
    const auto speed=Length({s.support_velocity_256[0],0,s.support_velocity_256[2],s.support_velocity_256[0]})*Bits(0x3d4ccccd);
    const auto nonnegative=Select(-speed,0,speed);s.support_speed_348=Select(1.0f-nonnegative,nonnegative,1);
    s.previous_support_frame_192=i.contact_frame_32;return delta;
}
void RefreshBipedTarget(BipedGroundMotionState& s,const BipedGroundMotionInput& i)
{
    if(i.target_frame_present_352){s.target_frame_608=i.target_frame_368;s.target_frame_608[3]=biped_math::Madd(i.target_frame_368[0],biped_math::Bits(0x3e4ccccd),i.target_frame_368[3]);}
}
Vec4 BipedHeightAdjustment(const BipedGroundMotionState& s,const BipedGroundMotionInput& i,Vec4 position)
{return biped_math::Mul(s.frame_0[1],biped_math::Dot(biped_math::Sub(i.contact_position_0,position),s.frame_0[1])*biped_math::Bits(0x3d4ccccd));}
std::pair<Vec4,Vec4> BipedApproach(BipedGroundMotionState& s,const BipedGroundMotionInput& i,Vec4 position,const Mat4& delta)
{
    using namespace biped_math;auto step=Mul(s.velocity_480,Step());Vec4 height{};
    if(i.animation_directed_304)
    {
        const auto animation_speed=Length(i.animation_motion_224);const auto stationary=animation_speed<Bits(0x3a83126f);
        auto difference=Sub(s.target_frame_608[3],position);auto distance=Length(difference);
        if(!(s.target_scale_784>=0)){RefreshBipedTarget(s,i);difference=Sub(s.target_frame_608[3],position);distance=Length(difference);s.target_scale_784=distance/(stationary?i.requested_duration_288:animation_speed);}
        step={};if(!(distance<=Bits(0x3a83126f))){auto amount=s.target_scale_784*Step();if(!stationary)amount=Length(i.animation_motion_240)*amount;step=Mul(Mul(difference,Reciprocal(distance)),amount);}
        const auto sine=Clamp(Dot(Cross(s.target_frame_608[0],s.frame_0[2]),s.frame_0[1]),-1,1),angle=Asin(sine);
        const auto denominator=stationary?i.requested_duration_288*s.target_scale_784:s.target_scale_784*animation_speed;s.angular_velocity_688=0;
        if(!(denominator<=Bits(0x3a83126f)))s.angular_velocity_688=((1.0f-distance/denominator)*angle)*Bits(0x426fffff);
        s.target_frame_608=Compose(s.target_frame_608,delta);return {step,height};
    }
    s.target_scale_784=-1;RefreshBipedTarget(s,i);
    if((i.contact_flags_176&2)==0&&!i.obstacle_enabled_713){if((i.contact_flags_176&1)!=0)height=BipedHeightAdjustment(s,i,position);return {step,height};}
    Vec4 target;
    if(i.obstacle_enabled_713)target=i.obstacle_target_672;
    else
    {
        const auto side=UnitOr(Cross({0,1,0,0},s.frame_0[2]),s.frame_0[0]);const auto point=s.correction_enabled_711?i.correction_target_592:i.contact_target_96;
        target=Sub(point,Mul(side,Dot(Sub(point,position),side)));
    }
    auto difference=Sub(target,position);
    if(Dot(difference,difference)<Bits(0x37800000)||!(Dot(difference,s.velocity_480)>=-.5f))
    {const auto predicted=Madd(Mul(s.velocity_480,Step()),2,position);target={predicted[0],target[1],predicted[2],predicted[3]};}
    difference=Sub(target,position);const auto budget=Length(step),distance=Length(difference);
    if(!(distance<=budget))step=Mul(UnitOr(difference,{}),budget);
    else
    {
        const auto normal=i.obstacle_enabled_713?i.target_frame_368[1]:i.contact_normal_112;
        const auto angle=Bits(0x42340000)*Bits(0x3c8efa35);const auto limited=LimitAngle(normal,i.reference_frame_128[1],angle),unit=UnitOr(limited,{});
        const auto tangent=Sub(s.velocity_480,Mul(unit,Dot(s.velocity_480,unit)));step=Madd(UnitOr(tangent,{}),budget-distance,difference);
    }
    if(!(budget>=Bits(0x3c23d70a)))height=BipedHeightAdjustment(s,i,position);return {step,height};
}
Vec4 RotateBipedVector(Vec4 v,Vec4 axis,float angle)
{
    const auto sc=SinCos(angle);const auto s=sc.first,c=sc.second,t=1.0f-c;
    const auto x=axis[0],y=axis[1],z=axis[2],tx=t*x,ty=t*y,tz=t*z,sx=s*x,sy=s*y,sz=s*z;
    const Mat4 columns{{{std::fma(tx,x,c),std::fma(tx,y,sz),tx*z-sy,0},
        {ty*x-sz,std::fma(ty,y,c),std::fma(ty,z,sx),0},{std::fma(tz,x,sy),tz*y-sx,std::fma(tz,z,c),0},{0,0,0,0}}};
    return biped_math::TransformVector(v,columns);
}
void PublishBipedMotion(BipedGroundMotionState& s,Vec4 displacement)
{
    using namespace biped_math;s.published_frame_64=s.frame_0;if(!s.correction_enabled_711)return;
    const auto magnitude=Length(s.correction_576);
    if(magnitude<=Bits(0x3c23d70a)){s.correction_576={};s.correction_enabled_711=false;}
    else
    {
        const auto unit=Mul(s.correction_576,1.0f/magnitude);const auto proportional=magnitude*Bits(0xbd4ccccd),minimum=Bits(0xbba3d70a);
        const auto decay=Select(minimum-proportional,proportional,minimum),projected=Dot(displacement,unit),amount=Select(projected-decay,decay,projected);
        if(amount> -magnitude)s.correction_576=Madd(unit,amount,s.correction_576);else{s.correction_576={};s.correction_enabled_711=false;}
    }
    s.published_frame_64[3]=Sub(s.published_frame_64[3],s.correction_576);
}
}
void UpdateBipedGroundMotion(BipedGroundMotionState& state,const BipedGroundMotionInput& input)
{
    using namespace biped_math;const auto support_delta=UpdateBipedSupport(state,input);const auto old_position=state.frame_0[3];state.frame_0[3]={};
    const auto approach=BipedApproach(state,input,old_position,support_delta);
    auto displacement=biped_math::Add({},approach.first);displacement=biped_math::Add(displacement,approach.second);displacement=biped_math::Add(displacement,input.contact_displacement_384);
    displacement=Madd(input.velocity_addition_528,Step(),displacement);displacement=Madd(state.predicted_support_velocity_272,Step(),displacement);
    const auto angle=(state.angular_velocity_688+state.predicted_support_yaw_344)*Step();const auto axis=state.frame_0[1];
    for(auto& row:state.frame_0)row=RotateBipedVector(row,axis,angle);
    state.frame_0[0]=Unit(Cross(input.desired_up_544,state.frame_0[2]));state.frame_0[1]=input.desired_up_544;state.frame_0[2]=Unit(Cross(state.frame_0[0],input.desired_up_544));
    state.frame_0=OrthonormalizeSkeletonFrame(state.frame_0);state.frame_0[3]=biped_math::Add(old_position,displacement);PublishBipedMotion(state,displacement);
}
}
