#include "SkeletonCollisionFeedback.h"
#include "BoardGroundAngle.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
Vec4 Scale(Vec4 v,float s){for(auto& x:v)x*=s;return v;}
Vec4 Sub(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]-=b[i];return a;}
Vec4 Add(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]+=b[i];return a;}
Vec4 Cross(Vec4 a,Vec4 b)
{return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1]),std::fma(-a[3],b[3],a[3]*b[3])};}
Vec4 Normalize(Vec4 v)
{
    const float square=Dot3(v,v),inverse=InverseLengthSquared(square,2);
    const float size=square==0.0f ? 0.0f:square*inverse;return size>1.0e-6f ? Scale(v,inverse):Vec4{};
}
Vec4 ClampLength(Vec4 v,float maximum)
{
    const float size=Length3(v);if(size<Float(0x37800000))return v;
    const float bounded=maximum-size>=0.0f ? size:maximum;return Scale(Scale(v,bounded),RefinedReciprocal(size,2));
}
float Maximum(float a,float b){return a-b>=0.0f ? a:b;}
float Mass(SkeletonContactBody body){return 1.0f/(body.state_flags==1 ? 0.001f:body.inverse_mass);}
float SignedAngle(Vec4 av,Vec4 bv,Vec4 uv)
{
    Vec3 a{av[0],av[1],av[2]},b{bv[0],bv[1],bv[2]},up{uv[0],uv[1],uv[2]};
    const float sa=Dot3(a,a),sb=Dot3(b,b);if(!(sa>0.0001f && sb>0.0001f))return 0;
    const float angle=BoardGroundAngleBetween(a,b),ia=InverseLengthSquared(sa,1),ib=InverseLengthSquared(sb,1);
    a={a.x*ia,a.y*ia,a.z*ia};b={b.x*ib,b.y*ib,b.z*ib};
    const Vec3 cross{std::fma(-a.z,b.y,a.y*b.z),std::fma(-a.x,b.z,a.z*b.x),std::fma(-a.y,b.x,a.x*b.y)};
    return Dot3(cross,up)<0.0f ? Float(0x40c90fdb)-angle:angle;
}
constexpr std::array<std::size_t,24> Region{{std::size_t(-1),0,1,2,2,2,1,3,3,3,1,1,1,1,1,6,6,4,4,7,7,5,5,1}};
}
SkeletonCollisionFeedback::SkeletonCollisionFeedback(SkeletonFeedbackSettings input):settings(input),compliant(input.body.compliant)
{
    planes.reserve(20);
    specific={{{23,input.groin_offset,{},input.groin_radius*input.groin_radius,false,false},
        {1,input.face_offset,{},input.face_radius*input.face_radius,false,false}}};
}
void SkeletonCollisionFeedback::Reset()
{
    const auto points=specific;const auto old_compliant=compliant;const bool any=flags.any;
    *this=SkeletonCollisionFeedback(settings);specific=points;compliant=old_compliant;flags.any=any;
}
void SkeletonCollisionFeedback::SetUpNormal(){Reset();priority=settings.body.priority;compliant=settings.body.compliant;}
void SkeletonCollisionFeedback::BeginFrame(const SkeletonCollisionInput& input)
{
    timer-=input.dt;wipeout_times[2]+=input.dt;flags={};flags.ragdoll=input.ragdoll;planes.clear();maximum_priority=0;
    maximum_skater_force=0;other_skater=-1;maximum_group_8_force=0;maximum_group_11_force=0;material_12_height=0;
    highest_normal={0,-1,0,0};foot_normal={};material_normals={{{0,-1,0,0},{0,-1,0,0}}};
    for(std::size_t part=0;part<24;++part){contact_age[part]-=input.dt;current[part]=false;bones[part]={};}
    for(auto& region:regions){const auto material=region.material_flags;region={};region.material_flags=material;}
    if(!input.ragdoll)wipeout_times={};
    for(auto& point:specific)
    {
        point.recent=point.recent && input.ragdoll;point.current=false;
        if(point.part>=input.physical.pose.size())std::abort();point.world_point=TransformSkeletonPoint(input.physical.pose[point.part],point.local_point);
    }
    if(input.request_partial_ragdoll)timer=settings.body.effect_time;
}
bool SkeletonCollisionFeedback::IgnoreGround(const SkeletonCollisionInput& input,const SkeletonContactReport& report) const
{
    if(input.ragdoll || (input.disable_ground_filter && !input.category_600))return false;
    const float distance=Dot3(input.plane_normal,Sub(report.point,input.plane_point));
    const float threshold=input.offboard ? 0.3f:settings.ground_plane_max_distance;
    return distance<threshold && (input.offboard || std::fabs(Dot3(report.normal,input.plane_normal))>settings.ground_plane_max_angle);
}
void SkeletonCollisionFeedback::ObserveNormal(bool ragdoll,const SkeletonContactReport& report,std::uint32_t material)
{
    const auto normal=report.normal;if(normal[1]>highest_normal[1])highest_normal=normal;
    if(ragdoll)
    {
        if(material==10 && normal[1]>material_normals[0][1]){material_normals[0]=normal;flags.material_10=true;}
        else if(material==11 && normal[1]>material_normals[1][1]){material_normals[1]=normal;flags.material_11=true;}
    }
    else if((report.part==15 || report.part==19) && normal[1]>foot_normal[1])foot_normal=normal;
}
void SkeletonCollisionFeedback::RecordForce(const SkeletonContactReport& report,bool is_specific,Vec4 relative,float force,float weighted_force)
{
    auto& bone=bones[report.part];auto& region=regions[Region[report.part]];
    const float previous=is_specific ? bone.specific_force:bone.force;
    const auto tangent=force>previous || force>region.force ? Cross(relative,report.normal):Vec4{};
    if(force>previous)
    {
        if(is_specific){bone.specific_force=force;bone.specific_normal=report.normal;bone.specific_tangent=tangent;bone.specific_tag=report.tag;}
        else {bone.force=force;bone.normal=report.normal;bone.tangent=tangent;bone.point=report.point;bone.tag=report.tag;}
        constexpr std::array<std::uint32_t,3> groups{{8,11,5}};
        for(std::size_t i=0;i<3;++i)bone.groups[i]=bone.groups[i] || report.other_group==groups[i];
        bone.groups[3]=bone.groups[3] || (report.other_group!=8 && report.other_group!=11 && report.other_group!=5);
    }
    if(force>region.force)region={force,weighted_force,Length3(tangent),report.tag&0x7fu,report.normal,report.part};
}
bool SkeletonCollisionFeedback::CheckConflicting(const SkeletonCollisionInput& input) const
{
    for(std::size_t i=0;i<regions.size();++i)
    {
        const auto& a=regions[i];if(!a.part || !(a.force>0.0f))continue;if(*a.part>=24)std::abort();if(!compliant[*a.part])continue;
        for(std::size_t j=0;j<regions.size();++j)
        {
            const auto& b=regions[j];if(!b.part || i==j || !(b.force>0.0f))continue;if(*b.part>=24)std::abort();if(!compliant[*b.part])continue;
            if(Dot3(a.normal,b.normal)<-0.7f && Dot3(Sub(input.body_frames[*b.part][3],input.body_frames[*a.part][3]),a.normal)<0.0f)return true;
        }
    }
    return false;
}
bool SkeletonCollisionFeedback::CheckImpaled() const
{
    for(std::size_t i=1;i<23;++i)
    {
        const auto& a=bones[i];if(!(a.force>0.0f))continue;
        for(std::size_t j=i+1;j<24;++j){const auto& b=bones[j];if(b.force>0.0f && Dot3(a.normal,b.normal)<-0.99f && std::fabs(Dot3(a.normal,Sub(a.point,b.point)))<0.03f)return true;}
    }
    return false;
}
void SkeletonCollisionFeedback::Update(const SkeletonCollisionInput& input,const std::vector<SkeletonContactReport>& reports)
{
    BeginFrame(input);const float reference_speed=Length3(input.reference_velocity);const auto direction=Normalize(input.reference_velocity);
    for(const auto& report:reports)
    {
        if(report.part>=24){assert(report.part<24 && "SkeletonCollision report part exceeds native24-part array");std::abort();}
        const auto part=report.part;const auto material=(report.tag>>7)&31u;flags.any=true;
        if(report.other_group==4 && (part==15 || part==16 || part==19 || part==20))flags.foot_board=true;
        if(material==6)flags.material_6=true;if(material==12){flags.material_12=true;material_12_height=report.point[1];}
        if(IgnoreGround(input,report))continue;ObserveNormal(input.ragdoll,report,material);
        bool is_specific=false;
        for(auto& point:specific){const auto delta=Sub(report.point,point.world_point);if(part==point.part && Dot3(delta,delta)<point.radius_squared){point.current=true;point.recent=true;is_specific=true;}}
        if(planes.size()>=20)continue;
        contact_age[part]=0;current[part]=true;
        if(priority[part]>maximum_priority){maximum_priority=priority[part];planes.clear();}
        if(priority[part]==maximum_priority)planes.push_back({report.normal,part});
        const float ma=Mass(report.body_a),mb=Mass(report.body_b),other_mass=report.side_a ? mb:ma;
        const bool small=other_mass>0.0001f && other_mass<settings.small_object_mass;
        const float factor=((mb+ma)/(mb*ma))*Float(0x3991a2b5);
        const float weighted_force=Length3(Scale(report.solved_vector,factor))*input.part_weights[part];
        const auto part_velocity=input.physical.velocities[part];Vec4 own_velocity;
        if(input.ragdoll)own_velocity=Scale(Add(input.com_velocity,part_velocity),0.5f);
        else if(input.offboard || input.entering_offboard){own_velocity=input.com_velocity;own_velocity[1]=0;}
        else own_velocity=ClampLength(Scale(direction,Dot3(part_velocity,direction)),reference_speed);
        const auto other=report.side_a ? report.body_b:report.body_a;const auto relative=Sub(other.linear_velocity,own_velocity);
        float force=std::fabs(Dot3(relative,report.normal));if(small)force*=0.5f;
        switch(report.other_group)
        {
        case 5:force*=input.ai_collision_scalar ? settings.ai_scalar:settings.skater_scalar;maximum_skater_force=Maximum(maximum_skater_force,force);if(report.other_entity)other_skater=*report.other_entity;flags.nonboard=true;break;
        case 8:flags.group_8=true;maximum_group_8_force=Maximum(maximum_group_8_force,force);flags.nonboard=true;break;
        case 11:maximum_group_11_force=Maximum(maximum_group_11_force,force);flags.nonboard=true;break;
        case 4:break;
        default:flags.nonboard=true;
        }
        if(part>0){RecordForce(report,is_specific,relative,force,weighted_force);timer=settings.body.effect_time;}
        if(!compliant[part] || small)flags.noncompliant=true;else flags.compliant=true;
        flags.has_impulse=flags.compliant || input.offboard;
    }
    if(input.ragdoll)flags.impaled=CheckImpaled();else flags.conflicting=CheckConflicting(input);
    const float duration=settings.body.effect_time;
    if(duration==0.0f)drive_weight=1;
    else {const float ratio=timer/duration,low=-ratio>=0.0f ? 0.0f:ratio;drive_weight=1.0f-((1.0f-low>=0.0f) ? low:1.0f);}
    flags.recovering=drive_weight<1.0f;
}
Vec4 SkeletonCollisionFeedback::FilterError(Vec4 error,Vec4 axis) const
{
    const auto projected=Sub(error,Scale(axis,Dot3(error,axis))),direction=Normalize(projected);
    if(Dot3(direction,direction)<0.1f)return projected;
    const float half_pi=Float(0x3fc90fdb);float minimum=half_pi,maximum=-half_pi;bool found=false;
    for(const auto& plane:planes)
    {
        const auto normal=Normalize(Sub(plane.normal,Scale(axis,Dot3(plane.normal,axis))));if(Dot3(normal,normal)<0.1f)continue;
        const float angle=SignedAngle(direction,normal,axis),turns=angle*Float(0x3e22f983),fractional=turns-std::floor(turns);
        const float centered=fractional-(fractional>0.5f ? 1.0f:0.0f),wrapped=centered*Float(0x40c90fdb);
        if(wrapped>-half_pi && wrapped<half_pi){if(wrapped<minimum)minimum=wrapped;if(wrapped>maximum)maximum=wrapped;found=true;}
    }
    const float angle=(maximum+minimum)*0.5f,magnitude=found ? Cos(angle):0.0f,c=Cos(angle),s=Sin(angle);
    const float x=axis[0],y=axis[1],z=axis[2],sx=s*x,sy=s*y,sz=s*z,t=1.0f-c,tx=t*x,ty=t*y,tz=t*z;
    const std::array<std::array<float,3>,3> rotation{{{std::fma(x,tx,c),std::fma(tx,y,sz),tx*z-sy},
        {ty*x-sz,std::fma(ty,y,c),std::fma(ty,z,sx)},{std::fma(tz,x,sy),tz*y-sx,std::fma(z,tz,c)}}};Vec4 result{};
    for(std::size_t i=0;i<3;++i)result[i]=std::fma(rotation[2][i],projected[2],std::fma(rotation[1][i],projected[1],rotation[0][i]*projected[0]))*magnitude;
    return result;
}
}
