#include "AirTrajectoryLaunch.h"
#include "GravityScale.h"
#include "AirTrajectorySelectorMath.h"
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace M=air_trajectory_detail;
bool AdjustAirTrajectoryLaunchVelocity(AirLaunchInfo& info,AirSelectorInput input,const AirTrajectorySelectorSettings& s)
{
    const auto n=input.ground_normal,v=info.start_velocity;
    auto normal=M::Scale(n,Dot3(v,n));normal[1]=0;
    const auto combined=M::Add({0,v[1],0,0},normal),residual=M::Sub(v,combined);
    const float lean=VectorMin(VectorMax(input.directional_input-0.25f,-1),1);
    const auto aligned=M::Normalize(M::Sub(M::Up,M::Scale(n,lean*s.vert_jump_align_max_angle)));
    if (n[1]>=s.vert_jump_align_max_ground_normal_y) return false;
    if (M::Normalize(combined)[1]>s.vert_jump_align_min_direction_y)
    {
        const auto left=M::Scale(M::Add(M::Scale(aligned,M::Length(combined)),residual),s.vert_jump_align_factor);
        const auto right=M::Scale(M::Normalize(v),1-s.vert_jump_align_factor);
        info.start_velocity=M::Scale(M::Normalize(M::Add(left,right)),M::Length(v));return true;
    }
    if (!info.player_jumped&&input.previous_physics_state!=200)
    {
        const auto component=M::Scale(n,Dot3(v,n));
        info.start_velocity=M::Add(M::Scale(component,s.natural_air_off_verts_scalar),M::Sub(v,component));
    }
    return false;
}
std::vector<Vec4> AirTrajectoryCandidateVelocities(const AirLaunchInfo& info,const AirTrajectorySelectorSettings& s)
{
    const auto count=std::min<std::uint16_t>(info.trajectory_count,7);
    std::vector<Vec4> velocities;velocities.reserve(count);if (count==0) return velocities;
    const auto v=info.start_velocity;velocities.push_back(v);
    auto right=M::Normalize(M::Cross(M::Up,v)),forward=M::Normalize(M::Cross(right,M::Up));
    const float speed=M::Length(v);
    float cone_speed=info.player_jumped?M::Length(info.com_velocity):speed;
    const float radians=M::Bits(0x3c8efa35),x=info.cone_angle_x*radians;
    const float z=(s.cone_angle_z_vs_speed.Evaluate(cone_speed*0.05f)*info.cone_angle_z)*radians;
    cone_speed=VectorMin(VectorMax(cone_speed,s.speed_factor_min),s.speed_factor_max);
    right=M::Scale(right,Sin(x)*cone_speed);forward=M::Scale(forward,Sin(z)*cone_speed);
    if (count>1)
    {
        const float step=M::Bits(0x40c90fdb)/static_cast<float>(count-1);float angle=0;
        for (std::uint16_t i=1;i<count;++i)
        {
            const auto candidate=M::Madd(forward,Cos(angle),M::Madd(right,Sin(angle),v));
            velocities.push_back(M::Scale(M::Normalize(candidate),VectorMin(M::Length(candidate),speed)));angle+=step;
        }
    }
    return velocities;
}
AirTrajectoryLaunchBatch BuildAirTrajectoryLaunchBatch(const AirLaunchInfo& info,AirSelectorInput input,const AirTrajectorySelectorSettings& s)
{
    auto velocities=AirTrajectoryCandidateVelocities(info,s);
    const float ground=s.displacement_vs_ground_normal.Evaluate(std::fabs(input.ground_normal[1]));
    const float speed=s.displacement_vs_speed.Evaluate(input.board_vertical_velocity*0.1f),blend=VectorMax(speed,ground);
    const float height=Dot3(M::Sub(info.animation_com_position,input.contact_position),info.reckoning_transform[1])-s.trajectory_radius;
    const float displacement=VectorMin(height,s.trajectory_displacement)*(1-blend)+s.trajectory_displacement*blend;
    auto origin=M::Sub(info.animation_com_position,M::Scale(info.reckoning_transform[1],displacement));
    auto board_position=info.board_position;
    if (info.use_position_override) {origin=info.start_position_override;board_position=info.board_position_override;}
    const auto com_displacement=M::Sub(info.animation_com_position,origin);
    const float square=std::fma(info.start_velocity[1],info.start_velocity[1],-(s.trajectory_max_drop*(M::Bits(0xc19ccccd)*GravityScale())));
    const float root=square==0?0:square*InverseLengthSquared(square,2);
    const float duration=VectorMin((-info.start_velocity[1]-root)*(M::Bits(0xbdd0fac6)/GravityScale()),s.trajectory_max_time);
    std::vector<AirTrajectoryQueryRequest> requests;requests.reserve(velocities.size());
    for (const auto& velocity:velocities)
        requests.push_back({{M::Madd(velocity,info.timestep,origin),velocity,input.gravity,duration},
            s.trajectory_radius,s.trajectory_error_start,s.trajectory_error_end});
    return {std::move(requests),std::move(velocities),origin,board_position,
        M::Transform(info.reckoning_inverse,M::Sub(info.board_position,origin)),
        M::Transform(info.reckoning_inverse,com_displacement),com_displacement};
}
void AdjustAirTrajectoryVelocity(AirTrajectory& trajectory,std::int32_t frame,Vec4 adjustment,float maximum)
{
    if (frame<=0) return;
    const auto correction=M::Scale(adjustment,RefinedReciprocal(static_cast<float>(frame)*M::Step(),2));
    const float scalar=Dot3(correction,correction)>maximum*maximum?maximum/M::Length(correction):1;
    trajectory.velocity=M::Madd(correction,scalar,trajectory.velocity);
}
}
