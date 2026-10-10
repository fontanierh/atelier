#include "BipedRuntimeOwners.h"
#include "OffboardAirMath.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{Vec4 Value(RawVector words){Vec4 v;std::memcpy(v.data(),words.data(),16);return v;}}
SkeletonInputCollision BipedRuntimeCollision(const PhysicalSimulationRuntime& p)
{return {p.collision_feedback.flags.compliant,p.collision_feedback.flags.has_impulse,p.collision_pose_error,p.skeleton_collision.partial_ragdoll,p.collision_feedback.drive_weight};}
OffboardAirContext BipedRuntimeAirContext(const ProcessedPhysicsInput& p)
{return {p.actor_query_2948,static_cast<std::int32_t>(p.actor_query_2952),Value(p.vectors_544_560_592_608[0]),Value(p.effective_anim_transform_192[2])};}
Vec4 BipedRuntimeGravity(const PhysicalSimulationRuntime& p)
{const auto v=p.settings.board.step.simulation.gravity_acceleration;return {v.x,v.y,v.z,0};}
Mat4 EffectiveBipedAirFrame(Mat4 frame,std::uint32_t flags)
{if((flags&4)!=0)for(unsigned n:{0u,2u})for(float& v:frame[n])v=-v;return frame;}
bool BipedRuntimeLaunchInput(BipedRuntimeOwners v,std::optional<OffboardDepartureGeometry> geometry,const char* missing,
    OffboardAirLaunchInput& out,std::string& error)
{
    if(!v.toolkit){error=missing;return false;}const auto& p=v.processed;
    out={v.toolkit->deck[3],Value(p.effective_anim_transform_192[2]),Value(p.vectors_544_560_592_608[0]),Value(p.vectors_544_560_592_608[2]),Value(p.vectors_544_560_592_608[3]),Value(p.vectors_880_896_912_928_944[2]),geometry,p.flags_2472,p.flags_2476,p.flags_2480,p.state_2504,p.state_2508,p.category_2512,p.category_2516,v.animation_input.extra.biped_world_x,v.animation_input.extra.biped_world_z};
    error.clear();return true;
}
}
