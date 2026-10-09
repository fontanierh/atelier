#include "JointBuild.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::uint32_t Word(float value){std::uint32_t word;std::memcpy(&word,&value,4);return word;}
Vec3 Add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
std::array<float,3> Array(Vec3 v){return {v.x,v.y,v.z};}
Vec3 Vector(const std::uint32_t* p){return {Float(p[0]),Float(p[1]),Float(p[2])};}
Quat Quaternion(const std::uint32_t* p){return {Float(p[0]),Float(p[1]),Float(p[2]),Float(p[3])};}
struct Parameters
{
    Vec3 position_allowance,velocity_allowance;
    float twist_velocity,swing_velocity,swing_threshold,twist_threshold;
    std::uint32_t swing_mode,twist_mode;
};
struct AngularRows {std::array<Vec3,3> axes;std::array<float,3> low,high;};
AngularRows Angular(const Parameters& p,Basis3 a,Basis3 b,constraint_frame::QuaternionRows rqd)
{
    // Preserve the frozen reconstruction's matrix product. Its retail RQD
    // gather rounding path was not independently decoded in the source.
    const auto ac=constraint_frame::Columns(a),bc=constraint_frame::Columns(b);
    std::array<std::array<float,3>,3> relative{};
    for(std::size_t row=0;row<3;++row)for(std::size_t column=0;column<3;++column)relative[row][column]=Dot3(ac[row],bc[column]);
    const float infinity=Float(0x7f7fffff);
    AngularRows r{bc,{-infinity,-infinity,-infinity},{infinity,infinity,infinity}};
    if(p.swing_mode==0)
    {
        r.axes[1]=rqd.axes[1];r.axes[2]=rqd.axes[2];
        r.low[1]=2.0f*rqd.relative[1];r.high[1]=r.low[1];r.low[2]=2.0f*rqd.relative[2];r.high[2]=r.low[2];
    }
    else if(p.swing_mode==1)
    {
        if(!(relative[0][0]>=Float(0x3f7fff58)))
        {
            const float z=relative[0][2],y=relative[0][1],squared=std::fma(y,y,z*z);
            const float root=squared*InverseLengthSquared(squared);
            const float inverse=RefinedReciprocal(squared==0.0f?0.0f:root)*1.0f;
            r.axes[1]=Scale(Cross3(ac[0],bc[0]),inverse);r.axes[2]=Cross3(r.axes[1],ac[0]);
            r.low[1]=(p.swing_threshold-relative[0][0])*inverse;
        }
    }
    else if(p.swing_mode==2||p.swing_mode==3)
    {
        r.axes[1]=bc[1];
        if(p.twist_mode==0){r.axes[2]=rqd.axes[2];r.low[2]=2.0f*rqd.relative[2];r.high[2]=r.low[2];}
        else{r.axes[2]=Cross3(ac[0],r.axes[1]);r.low[2]=-relative[0][1];r.high[2]=r.low[2];}
        if(p.swing_mode==2)
        {
            const float denominator=relative[0][2];
            if(denominator!=0.0f)
            {
                const float correction=RefinedReciprocal(denominator)*(p.swing_threshold-relative[0][0]);
                if(denominator<0.0f)r.high[1]=correction;else r.low[1]=correction;
            }
        }
    }
    if(p.twist_mode==0){r.axes[0]=rqd.axes[0];r.low[0]=2.0f*rqd.relative[0];r.high[0]=r.low[0];}
    else if(p.twist_mode==1)
    {
        r.axes[0]=ac[0];const float denominator=relative[2][1]-relative[1][2];
        if(denominator!=0.0f)
        {
            const float numerator=(1.0f+relative[0][0])*p.twist_threshold-(relative[1][1]+relative[2][2]);
            const float correction=RefinedReciprocal(denominator)*numerator;
            if(denominator<0.0f)r.high[0]=correction;else r.low[0]=correction;
        }
    }
    return r;
}
void Write(std::array<std::uint32_t,96>& out,std::size_t vector,std::array<float,4> values)
{for(std::size_t i=0;i<4;++i)out[vector*4+i]=Word(values[i]);}
void InertiaColumns(std::array<std::uint32_t,96>& out,std::size_t vector,PackedWorldInverseInertia t,float mass)
{
    Write(out,vector,{t.full.x,t.full.y,t.full.z,mass});
    Write(out,vector+1,{t.full.y,t.split.y,t.split.z,mass});
    Write(out,vector+2,{t.full.z,t.split.z,t.split.x,mass});
}
}
std::array<std::uint32_t,96> BuildJoint(const JointBuildInput& input)
{
    const auto& words=input.parameters;const auto& frames=input.frames;const auto& a=input.body_a;const auto& b=input.body_b;
    const Parameters p{Vector(words.data()),Vector(words.data()+4),Float(words[8]),Float(words[9]),
        Float(words[12]),Float(words[13]),words[14],words[15]};
    const auto qa=constraint_frame::Compose(a.orientation,Quaternion(frames.data()));
    const auto qb=constraint_frame::Compose(b.orientation,Quaternion(frames.data()+8));
    const auto qlinear=constraint_frame::Compose(b.orientation,Quaternion(frames.data()+16));
    const auto arm_a=constraint_frame::TransformDirection(a.basis,Vector(frames.data()+4));
    const auto arm_b=constraint_frame::TransformDirection(b.basis,Vector(frames.data()+12));
    const auto linear_axes=constraint_frame::Columns(constraint_frame::Basis(qlinear));
    const auto angular=Angular(p,constraint_frame::Basis(qa),constraint_frame::Basis(qb),constraint_frame::Rows(qa,qb));
    const float inverse_a=(a.state&4)?a.inverse_mass:0.0f,inverse_b=(b.state&4)?b.inverse_mass:0.0f;
    const auto inertia_a=(a.state&4)?a.world_inverse_inertia:PackedWorldInverseInertia{};
    const auto inertia_b=(b.state&4)?b.world_inverse_inertia:PackedWorldInverseInertia{};
    std::array<float,3> linear_inverse{},angular_inverse{};
    for(std::size_t i=0;i<3;++i)
    {
        const auto av=Cross3(arm_a,linear_axes[i]),bv=Cross3(arm_b,linear_axes[i]);
        const auto ia=constraint_frame::MultiplyInertiaFromZero(inertia_a,av),ib=constraint_frame::MultiplyInertiaFromZero(inertia_b,bv);
        const float x=std::fma(bv.x,ib.x,std::fma(av.x,ia.x,0.0f));
        const float y=std::fma(bv.y,ib.y,std::fma(av.y,ia.y,0.0f));
        const float z=std::fma(bv.z,ib.z,std::fma(av.z,ia.z,0.0f));
        linear_inverse[i]=ReciprocalEstimate((z+y)+(x+(inverse_a+inverse_b)));
        const auto axis=angular.axes[i];
        const auto response=Add(constraint_frame::MultiplyInertiaFromZero(inertia_a,axis),constraint_frame::MultiplyInertiaFromZero(inertia_b,axis));
        const float ax=std::fma(axis.x,response.x,0.0f),ay=std::fma(axis.y,response.y,0.0f),az=std::fma(axis.z,response.z,0.0f);
        angular_inverse[i]=0.5f*ReciprocalEstimate(az+(ax+ay));
    }
    const float dt=input.time_step;
    const auto displacement_a=Scale(Madd(constraint_frame::PointRate(a.force_acceleration,a.torque_acceleration,arm_a),dt,
        constraint_frame::PointRate(a.linear_velocity,a.angular_velocity,arm_a)),dt);
    const auto displacement_b=Scale(Madd(constraint_frame::PointRate(b.force_acceleration,b.torque_acceleration,arm_b),dt,
        constraint_frame::PointRate(b.linear_velocity,b.angular_velocity,arm_b)),dt);
    const auto rate=constraint_frame::Project(Subtract(displacement_b,displacement_a),linear_axes);
    const auto separation=constraint_frame::Project(Subtract(Add(Add(b.center_of_mass,arm_b),displacement_b),
        Add(Add(a.center_of_mass,arm_a),displacement_a)),linear_axes);
    const auto position_allowance=Array(p.position_allowance),velocity_allowance=Array(p.velocity_allowance);
    std::array<float,3> linear_low{},linear_high{},angular_low{},angular_high{};
    for(std::size_t i=0;i<3;++i)
    {
        const float dl=separation[i]-position_allowance[i],dh=separation[i]+position_allowance[i];
        const float vl=rate[i]-velocity_allowance[i]*dt,vh=rate[i]+velocity_allowance[i]*dt;
        linear_low[i]=VectorMax(dl,VectorMin(vl,dh))*linear_inverse[i];
        linear_high[i]=VectorMin(dh,VectorMax(vh,dl))*linear_inverse[i];
    }
    const auto relative_rate=Subtract(Madd(b.torque_acceleration,dt,Subtract(b.angular_velocity,a.angular_velocity)),Scale(a.torque_acceleration,dt));
    const auto angular_displacement=constraint_frame::Project(Scale(relative_rate,dt),angular.axes);
    const std::array<float,3> angular_allowance{p.twist_velocity,p.swing_velocity,p.swing_velocity};
    for(std::size_t i=0;i<3;++i)
    {
        const float pl=angular.low[i]+angular_displacement[i],ph=angular.high[i]+angular_displacement[i];
        const float vl=angular_displacement[i]-angular_allowance[i]*dt,vh=std::fma(angular_allowance[i],dt,angular_displacement[i]);
        angular_low[i]=VectorMax(pl,VectorMin(vl,ph))*angular_inverse[i];
        angular_high[i]=VectorMin(ph,VectorMax(vh,pl))*angular_inverse[i];
    }
    std::array<std::uint32_t,96> out{};
    Write(out,0,{arm_a.x,arm_a.y,arm_a.z,Float(a.reaction_address)});Write(out,1,{arm_b.x,arm_b.y,arm_b.z,Float(b.reaction_address)});
    for(std::size_t component=0;component<3;++component)
    {
        std::array<float,4> lp{},ap{};
        for(std::size_t row=0;row<3;++row){lp[row]=Array(linear_axes[row])[component]*linear_inverse[row];ap[row]=Array(angular.axes[row])[component]*angular_inverse[row];}
        Write(out,4+component*2,lp);Write(out,5+component*2,ap);
    }
    out[27]=Word(angular_low[0]);out[31]=Word(angular_low[1]);out[35]=Word(angular_high[0]);out[39]=Word(angular_high[1]);
    Write(out,10,{linear_low[0],linear_low[1],linear_low[2],angular_low[2]});Write(out,11,{linear_high[0],linear_high[1],linear_high[2],angular_high[2]});
    Write(out,12,{linear_axes[0].x,linear_axes[0].y,linear_axes[0].z,Float(input.joint_address)});
    Write(out,13,{linear_axes[1].x,linear_axes[1].y,linear_axes[1].z,linear_axes[1].x});
    Write(out,14,{linear_axes[2].x,linear_axes[2].y,linear_axes[2].z,linear_axes[0].y});
    for(std::size_t i=0;i<3;++i)Write(out,15+i,{angular.axes[i].x,angular.axes[i].y,angular.axes[i].z,angular.axes[i].x});
    InertiaColumns(out,18,inertia_a,inverse_a);InertiaColumns(out,21,inertia_b,inverse_b);return out;
}
}
