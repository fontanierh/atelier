#include "WipeoutControls.h"
#include "WipeoutPhysicalMath.h"
#include "WipeoutOrientation.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
namespace
{
constexpr Vec4 Up{{0,1,0,0}};
Vec4 Rotate(Vec4 q,Vec4 v){const auto first=Cross(q,v),middle=Madd(v,q[3],first);return Madd(Cross(q,middle),2,v);}
Vec4 Transform(const Mat4& frame,Vec4 v){return Madd(frame[2],v[2],Madd(frame[1],v[1],Scale(frame[0],v[0])));}
Vec4 AlignmentUp(float x,float y)
{
    const float radians=Word(0x3c8efa35);const auto a=SinCos((x*radians)*0.5f),b=SinCos((y*radians)*0.5f),c=SinCos(0);
    const float sx=a.first,cx=a.second,sy=b.first,cy=b.second,sz=c.first,cz=c.second;
    const float cxcz=cx*cz,sxcz=sx*cz,sxsz=sx*sz,cxsz=cx*sz;
    const float qy=std::fma(cy,sxsz,sy*cxcz),qw=std::fma(cy,cxcz,sy*sxsz),qz=cy*cxsz-sy*sxcz,qx=cy*sxcz-sy*cxsz;
    return Rotate({qx,qy,qz,qw},Up);
}
float RetainInput(float input,float previous,float inertia){return std::fabs(input)>=std::fabs(previous)?input:(1.0f-inertia)*input+previous*inertia;}
Vec4 HorizontalAlignment(const WipeoutControlProfile& p,const Mat4& effective,Vec4 direction,Vec4 tilt)
{
    const auto local=NormalizeOr(p.horizontal_axis,{1,0,0,0}),world=Transform(effective,local);auto target=Rotate(tilt,NormalizeOr(Cross(direction,Up),{}));
    if(!p.horizontal_directed)target=Scale(target,Dot3(world,target)>0?1.0f:-1.0f);
    const auto axis=NormalizeOr(Cross(local,target),{});if(!(Dot3(axis,axis)>0.9f))return {};
    const float angle=WipeoutWrapAngle(WipeoutProjectedAngle(world,target,axis)),limit=Word(0x3f490fdb);return Scale(axis,Clamp(angle,-limit,limit)*0.8f);
}
}
void PrepareWipeoutProfile(WipeoutPhysicalState& s,const std::array<WipeoutControlProfile,5>& profiles,std::array<float,2> gesture,std::array<float,2> input)
{
    const float x=gesture[0],z=gesture[1];const std::size_t selected=std::fabs(x)<0.2f&&std::fabs(z)<0.2f?0:std::fabs(x)<=std::fabs(z)?(z<=0?3:1):(x<=0?4:2);
    s.control_time+=Step();if(selected!=s.profile){s.control_time=0;s.profile=selected;s.retained_sideways_input=0;s.retained_forward_input=0;}
    auto flat=s.velocity;flat[1]=0;const auto normalized=NormalizeOr(flat,{});
    if(s.direction_initialized){const float follow=profiles[selected].direction_follow;s.forward=NormalizeOr(Madd(normalized,follow,Scale(s.forward,1.0f-follow)),{});}
    else{s.direction_initialized=true;s.forward=normalized;}
    s.right=Cross(Up,s.forward);const Vec4 controls{input[0],0,input[1],0};s.forward_input=Dot3(controls,s.forward);s.sideways_input=Dot3(controls,s.right);
}
void ApplyWipeoutProfileDrift(const WipeoutPhysicalState& s,SkeletonBody& body,const WipeoutControlProfile& p)
{
    if(s.retained_velocity_active)return;
    const auto desired=Madd(s.right,p.drift_sideways*s.sideways_input,Scale(s.forward,p.drift_forward*s.forward_input));
    Vec4 change;for(unsigned i=0;i<4;++i){std::uint32_t bits;std::memcpy(&bits,&s.velocity[i],4);change[i]=Word(bits^0x80000000)*p.drift_drag;}
    change[0]*=0.02f;change[2]*=0.02f;if(Dot3(s.velocity,NormalizeOr(desired,{}))<p.drift_maximum_speed)change=Add(change,desired);
    AddWipeoutBodyVelocity(body,Scale(change,Step()));
}
bool ControlWipeoutAir(WipeoutPhysicalState& s,SkeletonBody& body,Vec4 com,std::array<float,2> input,bool contact)
{
    const auto spine=NormalizeOr(Sub(body.record.pose[11][3],body.record.pose[23][3]),{});s.angular_velocity=WipeoutBodyAngularVelocity(body.record,body.definition.animation_masses.fractional);
    if(contact)return false;const auto direction=NormalizeOr(s.velocity,{});auto sideways=NormalizeOr(Cross(Up,spine),{});sideways[1]=0;sideways=NormalizeOr(sideways,{});
    const auto velocity_side=Cross(Up,direction);if(Dot3(velocity_side,sideways)<0)sideways=Scale(sideways,-1);
    const auto plane=NormalizeOr(velocity_side,{});auto projected=Sub(spine,Scale(plane,Dot3(plane,spine)));projected=NormalizeOr(projected,{});
    auto automatic=Scale(Cross(spine,projected),0.5f);const auto hips_up=body.record.pose[23][1];
    if(std::fabs(input[0])<0.5f&&hips_up[1]<0){auto next=Sub(hips_up,Scale(plane,Dot3(plane,hips_up)));next=NormalizeOr(next,{});automatic=Madd(Cross(hips_up,next),0.5f,automatic);}
    const float limit=8.0f*Word(0x3c8efa35);const auto side=Scale(sideways,limit*input[1]);Vec4 negative;
    for(unsigned i=0;i<4;++i){std::uint32_t bits;std::memcpy(&bits,&spine[i],4);negative[i]=Word(bits^0x80000000);}
    auto target=Add(Madd(negative,limit*input[0],side),automatic);target=Scale(target,Word(0x426fffff));
    const auto delta=Scale(Scale(Sub(target,s.angular_velocity),Word(0x4019999a)),Step());ApplyWipeoutTorque(body,com,LimitLength(delta,0.5f));return true;
}
void ControlWipeoutProfileAir(WipeoutPhysicalState& s,SkeletonBody& body,Vec4 com,const Mat4& effective,std::array<float,2> input,const WipeoutControlProfile& p)
{
    s.angular_velocity=WipeoutBodyAngularVelocity(body.record,body.definition.animation_masses.fractional);const float radians=Word(0x3c8efa35);
    const Vec4 tilt_input{(input[1]*p.tilt_degrees)*radians,0,(input[0]*p.tilt_degrees)*-radians,0};s.retained_tilt=Madd(tilt_input,0.05f,Scale(s.retained_tilt,0.95f));
    const float tilt_length=Length(s.retained_tilt);Vec4 tilt{0,0,0,1};if(tilt_length>0.01f){const auto sc=SinCos(tilt_length*0.5f);tilt=Scale(Scale(s.retained_tilt,Reciprocal(tilt_length)),sc.first);tilt[3]=sc.second;}
    const auto desired=Transform(effective,AlignmentUp(p.align_euler[0],p.align_euler[1])),side=NormalizeOr(s.right,{}),projected=Sub(s.velocity,Scale(side,Dot3(s.velocity,side)));
    const auto direction=Dot3(s.forward,projected)<=0?Normalize(Add(desired,{0,-100,0,0})):NormalizeOr(projected,desired);
    const auto tilted=Rotate(tilt,direction),axis=NormalizeOr(Cross(tilted,desired),desired);
    const float angle=WipeoutWrapAngle(WipeoutSignedAngle(tilted,desired,axis));const auto distance=p.align_with_velocity?Scale(Scale(axis,angle),p.torque_distance):Vec4{};
    const auto input_side=Rotate(tilt,desired),input_forward=Rotate(tilt,NormalizeOr(Cross(direction,Up),{}));
    s.retained_sideways_input=RetainInput(s.sideways_input,s.retained_sideways_input,p.spin_inertia);s.retained_forward_input=RetainInput(s.forward_input,s.retained_forward_input,p.spin_inertia);
    const float side_spin=p.sideways_spin*s.retained_sideways_input,forward_spin=p.forward_spin*s.retained_forward_input;
    auto spin=Madd(input_forward,forward_spin,Madd(input_side,side_spin,{}));if(Dot3(spin,s.angular_velocity)<=0)s.control_time=0;
    spin=Scale(spin,p.spin_vs_time.Evaluate(s.control_time));const auto horizontal=std::fabs(side_spin)<=0.1f?HorizontalAlignment(p,effective,direction,tilt):Vec4{};
    const auto control=Add(Madd(Sub(spin,s.angular_velocity),p.torque_velocity,distance),horizontal);ApplyWipeoutTorque(body,com,control);
}
void ControlWipeoutGround(WipeoutPhysicalState& s,SkeletonBody& body,Vec4 com,const Mat4& effective,Vec4 ground_axis,const WipeoutControlProfile& p,const Mat4& animation_to_world,const std::array<Mat4,24>& animation_pose)
{
    s.angular_velocity=WipeoutBodyAngularVelocity(body.record,body.definition.animation_masses.fractional);const float speed=Length(s.velocity);
    Vec4 rolling;for(unsigned i=0;i<4;++i){const float x=effective[0][i]*p.roll_axis[0],y=std::fma(effective[1][i],p.roll_axis[1],x);rolling[i]=std::fma(effective[2][i],p.roll_axis[2],y);}rolling=NormalizeOr(rolling,{});
    const auto left=ComposeSkeletonAffine(animation_to_world,animation_pose[3]),right=ComposeSkeletonAffine(animation_to_world,animation_pose[7]);const bool hands_close=Length(Sub(left[3],right[3]))<=0.6f;Vec4 alignment{};
    if(p.align_ground_with_velocity){const auto axis=NormalizeOr(Cross(ground_axis,s.velocity),{});if(Dot3(rolling,axis)<0)rolling=Scale(rolling,-1);const auto perpendicular=Cross(rolling,axis);
        const float sine=Clamp(Length(perpendicular),-0.9999f,0.9999f),angle=WipeoutWrapAngle(Asin(sine)),magnitude=Clamp(angle*1.2f,0,1);
        if(speed>2){const auto normal=NormalizeOr(perpendicular,{}),current=NormalizeOr(s.angular_velocity,{});alignment=Scale(Sub(Scale(normal,magnitude),Scale(normal,Dot3(current,normal))),p.ground_align_torque);}
    }
    Vec4 roll{};if(hands_close&&p.roll_on_ground&&speed>2){const auto current=NormalizeOr(s.angular_velocity,{});roll=Scale(Sub(Scale(Scale(rolling,1.5f),s.forward_input),Scale(rolling,Dot3(current,rolling))),p.ground_roll_torque);}
    ApplyWipeoutTorque(body,com,Add(alignment,roll));
}
}
