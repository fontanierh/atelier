// SPDX-License-Identifier: Apache-2.0
#include "PlayerInputHostPhase.h"
#include <cassert>
#include <cstring>
namespace atelier::skate
{
namespace
{
Mat4 Value(RawMatrix raw)
{Mat4 value;std::memcpy(value.data(),raw.data(),sizeof(value));return value;}
void ResetPossession(PlayerStateCoordinatorOwners owners)
{
    auto& f=owners.physical;
    ResetBoardPossessionForTeleport(f.possession,f.possession_live,f.board,f.settings.board.collision,
        f.board_wiping_out,owners.ground_lifecycle.board_animated_290,f.controller_fields,
        BindPlayerBoardPossessionObservation(owners),owners.input.processed.timestep_2604);
}
class TeleportCalls final:public PlayerInputTeleportServices
{
    PlayerTeleportRuntime& runtime;
    PlayerTeleportFrame frame;
public:
    TeleportCalls(PlayerTeleportRuntime& r,PlayerTeleportFrame f):runtime(r),frame(f){}
    bool Teleport(PlayerInputOwners owners,Mat4 target,PlayerInputState& player,
        PhysicalPlayerInput& physical,ProcessedPhysicsInput& processed,std::string& error) override
    {return runtime.ResetPlayer(owners,target,player,physical,processed,frame,error);}
};
}
SkeletonInputCollision BindSkeletonInputCollision(const PhysicalSimulationRuntime& f)
{
    return {f.collision_feedback.flags.compliant,f.collision_feedback.flags.has_impulse,
        f.collision_pose_error,f.skeleton_collision.partial_ragdoll,f.collision_feedback.drive_weight};
}
bool AdvancePlayerInputHostPhase(PlayerInputHostPhaseOwners owners,PlayerInputHostPhaseFrame frame,
    bool& output_teleported,std::string& error)
{
    assert(&owners.player.physical==&owners.input.physical);
    assert(&owners.player.skeleton_input==&owners.input.skeleton_input);
    assert(&owners.player.ik==&owners.input.ik && &owners.player.animation_input==&owners.input.animation_input);
    auto& input=owners.player.input;auto& f=owners.player.physical;
    owners.contact.BeginInput();
    owners.landing_deck.manager.can_land_256=false;
    std::memcpy(input.player.manager_1852_vector_176.data(),owners.landing_deck.manager.ik_offset_176.data(),16);
    PlayerInputHostFrame host{0,0,frame.input_available,frame.actions.Value(71),f.DeckFrame(),
        owners.player.state.selector.post_grind_jump_counter};
    if(input.physical.state.flag_61!=0)
    {
        if(!input.physical.teleport_output)
        {error="Teleport State61 requires its published reset transform";return false;}
        host.published_board_transform=Value(input.physical.teleport_output->transform);
    }
    if(input.physical.state.flag_61!=0 || (input.player.flags_1296&(1u<<19))!=0 || input.PendingTeleport())
    {owners.selector.Reset();ResetPossession(owners.player);}
    auto collision=BindSkeletonInputCollision(f);bool teleported=false;
    const SkeletonInputPose pose{frame.pose.hierarchy,frame.attributes,frame.actions};
    TeleportCalls callbacks(owners.teleport,{frame.packet,pose,collision,teleported});
    const auto ground_frame=f.riding.reckoning_frames.ground;
    const auto air_targeting_grind=owners.trajectory.selector.GrindLockedToMiddle();
    std::optional<InputContinuation> continuation;
    if(!input.ProcessStage(owners.input,ground_frame,frame.packet,host,
        {pose,collision,air_targeting_grind},callbacks,{PlayerInputStage::Kind::ThroughTeleport,{}},
        owners.grind_world,continuation,error))return false;
    if(continuation)
    {
        std::optional<InputContinuation> ignored;
        if(!input.ProcessStage(owners.input,ground_frame,frame.packet,host,
            {pose,collision,air_targeting_grind},callbacks,{PlayerInputStage::Kind::AfterTeleport,*continuation},
            owners.grind_world,ignored,error))return false;
    }
    if(teleported)ResetPossession(owners.player);
    f.processed_flags_2468=input.processed.flags_2468;
    output_teleported=teleported;error.clear();return true;
}
}
