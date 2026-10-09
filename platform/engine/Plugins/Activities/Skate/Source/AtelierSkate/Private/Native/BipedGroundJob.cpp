#include "BipedGroundState.h"
#include "OffboardControllerMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
BipedGroundPrepared PrepareBipedGroundJob(OffboardContactPrefix& retained,float& timer,const BipedGroundPrepareInput& input,OffboardGroundGeometry& owner)
{
    using namespace biped_math;timer+=Step();bool both_feet=true;
    if(input.contact.readiness>0){retained=input.contact.prefix;both_feet=(retained.flags_176&0x30)==0x30;}
    else if(input.previous_state!=501&&input.third_line_position){retained.flags_176=1;retained.position=*input.third_line_position;retained.normal=input.frame[1];}
    const bool suppress=static_cast<std::int32_t>(input.frames_since_teleport)<20;if(suppress)retained.flags_176&=~8u;const auto copied=retained;
    const auto xyz=[](Vec4 v){return Vec3{v[0],v[1],v[2]};};
    const auto geometry=owner.Consume({OffboardGroundQueryFrame(input.frame),xyz(retained.position),retained.flags_176,retained.distance_172,xyz(copied.normal)});
    if(!both_feet&&!geometry.state_753&&(retained.flags_176&8)==0)timer=0;
    const auto animation_position=Madd(input.processed_velocity,Step(),input.processed_position);BipedGroundJob job{};
    job.contact_position=copied.position;job.contact_normal={geometry.input_up_416.x,geometry.input_up_416.y,geometry.input_up_416.z,copied.normal[3]};
    job.support_frame=copied.support_frame;job.target_position=copied.target_position;job.target_normal=copied.target_normal;job.edge_position=copied.edge_position;job.edge_normal=copied.edge_normal;
    job.flags=copied.flags_176;job.support_id=copied.support_180;job.collision_displacements=input.collision_displacements;job.animation_motion=input.animation_motion;job.animation_velocity=input.animation_velocity;
    job.desired_direction=input.controls.state_656;job.animation_position=animation_position;job.requested_duration=input.requested_duration;job.mirrored=(input.flags_2476&4)!=0;job.requested_phase=input.requested_phase;job.override_duration=input.override_duration;
    job.animation_directed=(input.flags_2488&0x08000000)!=0;job.movement=input.controls.state_708;job.steering=input.controls.state_712;job.sprint_pressed=(input.flags_2484&0x20000)!=0;job.suppress_lean=(input.flags_2480&0x80)!=0;
    job.suppress_minimum=suppress;job.target_frame_present=geometry.state_752;job.edge_active=geometry.state_753;job.target_frame=OffboardGroundNativeFrame(geometry.frame_768);job.ignore_obstacle=(input.flags_2472&0x10000000)!=0;return {job,geometry};
}
Mat4 SyncBipedGroundFrames(BipedGroundState& state,OffboardContactPrefix contact,BipedGroundResult result)
{
    using namespace biped_math;state.flags_144_to_150[3]=result.sliding;state.frame_80=result.physical_frame;
    if((contact.flags_176&1)!=0)
    {
        const auto delta=Sub(contact.position,state.frame_80[3]);const auto height=Dot(delta,state.frame_80[1]);
        if(!(height<=0))state.frame_80[3]=Madd(state.frame_80[1],height,state.frame_80[3]);
    }
    auto animation=result.animation_frame;
    if(state.flags_144_to_150[6])
    {
        state.duration_180-=Step();if(!(state.duration_180>0)){state.duration_180=0;state.flags_144_to_150[6]=false;}state.angle_172*=Bits(0x3f666666);
        const auto angle=std::fma(-state.angular_velocity_176,state.duration_180,state.angle_172);const auto sc=SinCos(angle);
        // Active ground_job uses geometric W=0, unlike the uncalled Services
        // facade's native permutation scratch lane in ground_sync::sync.
        const auto forward=Madd({sc.first,0,sc.second,0},animation[2][2],Madd({0,1,0,0},animation[2][1],Mul({sc.second,0,-sc.first,0},animation[2][0])));
        const auto right=Unit(Cross(animation[1],forward));animation[0]=right;animation[1]=Unit(Cross(forward,right));animation[2]=forward;
    }
    return animation;
}
}
