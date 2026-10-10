#include "WipeoutObservations.h"
#include <cstring>
namespace atelier::skate
{
namespace
{
float WipeoutFloat(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
Vec4 WipeoutVector(const RawVector& words)
{return {WipeoutFloat(words[0]),WipeoutFloat(words[1]),WipeoutFloat(words[2]),WipeoutFloat(words[3])};}
Vec4 WipeoutVector(Vec3 value){return {value.x,value.y,value.z,0};}
}
bool WipeoutObservations::Frame(WipeoutFrame& output,std::string& error) const
{
    const auto& p=processed;const auto& c=collision;const auto& b=board;WipeoutFrame f{};
    f.flags_2468=p.flags_2468;f.flags_2472=p.flags_2472;f.flags_2476=p.flags_2476;f.flags_2480=p.flags_2480;f.flags_2484=p.flags_2484;
    f.category=p.category_2512;f.timestep=p.timestep_2604;f.time_on_ground=p.time_on_ground_2752;f.speed=p.scalar_2652;
    f.animation_up=WipeoutVector(p.vectors_544_560_592_608[0]);f.landing_angle=p.scalar_2736;
    f.deck_velocity=WipeoutVector(p.vectors_400_416[0]);f.com_velocity=WipeoutVector(p.vectors_544_560_592_608[3]);
    std::memcpy(&f.jump_fix_frames,&jump_fix_frames,4);
    f.deck=deck;f.input_board=input_board;f.world_to_animation=world_to_animation;f.closing_velocity=WipeoutVector(b.closing_velocity);
    f.board_material_flags=b.collision_flags;f.board_contact=b.part_contact_count!=0;f.wheel_contact=b.wheel_contact_count!=0;
    f.board_contact_normal=WipeoutVector(b.overall_normal);f.opposing_contact=b.opposing_contact;
    for (std::size_t i=0;i<8;++i) f.regions_force[i]=c.regions[i].force;
    f.maximum_skater_force=c.maximum_skater_force;f.vehicle_force=c.maximum_group_8_force;f.group_8=c.flags.group_8;
    f.conflicting=c.flags.conflicting;f.compliant=c.flags.compliant;f.highest_normal=c.highest_normal;f.pose_error=pose_error;
    if (!maximum_pose_error) {error="Wipeout requires completed Skeleton pose-error feedback";return false;}
    f.maximum_pose_error=*maximum_pose_error;f.flip_active=air.flip_active;f.flip_requested_speed=air.flip_requested_speed;
    f.system_up_y=system_up_y;f.grind_selected=grind_locked_to_middle;f.grind_normal_valid=grind_normal.has_value();
    f.grind_normal=grind_normal.value_or(Vec4{0,1,0,0});output=f;error.clear();return true;
}
WipeoutRequestInput WipeoutRequestsFromProcessed(const ProcessedPhysicsInput& p)
{return {p.flags_2468,p.flags_2476,p.flags_2480,p.flags_2484,WipeoutFloat(p.vectors_544_560_592_608[0][1]),p.category_2512};}
}
