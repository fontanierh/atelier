#include "PlayerStateConditioning.h"
#include "GroundSurfaceRuntime.h"
#pragma clang fp contract(off)
namespace atelier::skate
{
std::uint32_t ConditionerCapabilityContext::Capabilities() const
{
    if(in_front_end)return 0;
    if(challenge_query_active&&challenge_configuration_enabled)return 0xfffffff7;
    if(hall_of_meat_enabled&&!challenge_query_active)return 0xfffff7f7;
    return 0x1c0;
}
bool PlayerStateConditioning::Load(const SettingsDatabase& data,std::string& error)
{
    return landing_settings.Load(data,error);
}
void PlayerStateConditioning::ResetFilteredForTeleport(){filtered.Reset();filtered_output.reset();}
bool PlayerStateConditioning::Publish(GrindRuntime& grind,GrindRuntimeOwners o,
    const PhysicalPlayerStateLifecycle& lifecycle,const std::optional<PhysicsGroundOutput>& ground,
    const KnownAirState& known_air,const PhysicsPosePacket& animation,std::string& error)
{
    const auto state=lifecycle.Active().state;
    const auto& riding=o.physical.riding;
    std::uint32_t surface=0;
    const std::array<bool,4> contacts{{riding.ground.parts[0].in_contact,riding.ground.parts[1].in_contact,
        riding.ground.parts[2].in_contact,riding.ground.parts[3].in_contact}};
    if(!ChoosePlayerGroundSurface(riding.wheel_lines.physics_surfaces,contacts,(riding.ground.collision_flags&(1u<<25))!=0,surface,error))return false;
    // The original chromosome publication runs on every completed frame and
    // precedes both fallible name reads and filtered-state writes.
    if(!grind.ConditionOutputs(o,animation.riding_fakie,error))return false;
    auto value=ResetFilteredGrindState();
    if(IsGrindState(state)&&!GrindRuntime::FilteredOutput(o.input.physical.grinds,value,error))return false;
    const auto result=filtered.Update({std::int32_t(PhysicalStateCategory(state)),std::int32_t(state),
        o.input.physical.collision.flag_3477!=0,std::int32_t(surface),ground&&ground->ground_32.wall_ride_exit,
        state==PhysicalStateId::KnownAir&&known_air.targeting_grind_213,
        o.input.physical.off_board.flag_320!=0,o.input.physical.off_board.flag_315!=0,
        value,grind.LastGrindDistance()});
    o.input.physical.filtered_state_0=std::uint32_t(result.category);filtered_output=result;return true;
}
void PlayerStateConditioning::PublishLandingQuality(const PhysicalSimulationRuntime& physics,PlayerInputRuntime& input,const AirReckoning& air)
{
    // These four false values are the explicit CURRENT host gameplay context,
    // not defaults for an absent front-end/challenge owner.
    input.physical.scoring.capabilities_204=ConditionerCapabilityContext{false,false,false,false}.Capabilities();
    const auto deck=physics.board.PartTransforms()[6];landing_quality={};
    if(filtered_output)
    {
        const auto n=physics.riding.ground.overall_normal,v=physics.riding.motion.linear_velocity;
        const auto z=deck.basis.columns[2];
        landing_quality.Update({std::uint32_t(filtered_output->previous_category),std::uint32_t(filtered_output->category),
            {n.x,n.y,n.z,0.0f},{v.x,v.y,v.z,0.0f},(input.processed.flags_2468&(1u<<20))!=0,
            {z[0],z[1],z[2],0.0f},air.state.spin_speed},landing_settings);
    }
}
}
