#include "PlayerStateRuntime.h"
#include "StockSettingsReader.h"
namespace atelier::skate
{
std::optional<PlayerStateRuntime> PlayerStateRuntime::Load(const SettingsDatabase& data,
    std::string_view mode,std::string& error)
{
    (void)mode;
    PlayerStateRuntime next;
    const StockSettingsReader read(data);
    const auto thresholds=[&](std::string_view category,TwoStageThresholds& out)
    {
        return read.Float(category,"default","NaturalAirMaxDist",out.field_856_primary,error)
            &&read.Float(category,"default","NaturalAirMinDist",out.field_856_secondary,error)
            &&read.Float(category,"default","NaturalAirTime",out.field_7692,error);
    };
    if(!thresholds("physics_airstates",next.normal_off_ground)
        ||!thresholds("physics_state_skitching",next.skitching_off_ground)
        ||!read.Float("physics_animation","default","MaxDeckZAxisYForAnimatedDeck",
            next.animated_board_threshold,error))return std::nullopt;
    error.clear();return next;
}
void PlayerStateRuntime::ResetForTeleport()
{
    conditioning.filtered.Reset();
    conditioning.filtered_output.reset();
    ground_output.reset();
    selector.nonspecific_collision_free_frames=0;
    selector.nonspecific_collision_frames=0;
    selector.something_colliding_frames=0;
    selector.two_wheel_counter=0;
    selector.three_wheel_counter=0;
    selector.post_grind_jump_counter=0;
    selector.air_frames=0;
    selector.teleport_countdown=10;
    selector.skitch_exit_countdown=0;
    post.trajectory_available=false;
}
}
