// SPDX-License-Identifier: Apache-2.0
#include "PlayerStateCoordinator.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
namespace atelier::skate
{
namespace
{
Vec4 Value(const RawVector& raw)
{Vec4 value;std::memcpy(value.data(),raw.data(),sizeof(value));return value;}
Mat4 Value(const RawMatrix& raw)
{Mat4 value;for(std::size_t n=0;n<4;++n)value[n]=Value(raw[n]);return value;}
// The original host's core Calls asserts the capability and publishes binding
// history; actual retained physical Exit/Enter runs afterwards in Set below.
class CoreCalls final : public PhysicalStateCalls
{
    const PlayerStateRegistry& registry;
public:
    explicit CoreCalls(const PlayerStateRegistry& r):registry(r){}
    PhysicalStateId GetType(StateBinding state) override{return state.state;}
    void Exit(StateCall call) override{if(!registry.Capability(call.state.state).has_exit)std::abort();}
    void Enter(StateCall call) override{if(!registry.Capability(call.state.state).has_enter)std::abort();}
};
class ControllerActions final : public SkateboardControllerActions
{
    BoardPossessionTransition& transition;
public:
    explicit ControllerActions(BoardPossessionTransition& t):transition(t){}
    void HoldSkateboard() override{transition.Hold();}
    void LetGoOfSkateboard() override{transition.LetGo();}
};
}
BoardPossessionProcessed BindPlayerBoardPossession(PlayerStateCoordinatorOwners owners)
{
    const auto& p=owners.input.processed;
    return {owners.input.toolkit?owners.input.toolkit->deck:owners.physical.DeckFrame(),
        Value(p.effective_anim_transform_192),Value(p.vectors_544_560_592_608[2]),
        Value(p.vectors_880_896_912_928_944[2]),Value(p.vectors_400_416[0]),
        Value(p.vectors_464_480_496_512_528[0]),p.flags_2476,p.flags_2480,p.flags_2488};
}
BoardPossessionObserveInput BindPlayerBoardPossessionObservation(PlayerStateCoordinatorOwners owners)
{
    auto& f=owners.physical;
    return {BindPlayerBoardPossession(owners),
        owners.input.toolkit?std::optional<Mat4>(owners.input.toolkit->deck):std::nullopt,
        f.riding.ground,f.riding.wheel_lines,f.skeleton.record,f.collision_feedback,
        f.drive_frames,f.roots.animation_to_world};
}
bool SetPlayerPhysicalState(PlayerStateCoordinatorOwners owners,PhysicalStateId requested,
    PlayerStatePhaseDispatch& phases,std::string& error)
{
    auto& state=owners.state;state.requested_state=requested;
    const auto current=state.Current();
    if(current==requested){error.clear();return true;}
    auto& f=owners.physical;auto& p=owners.input.processed;
    const auto observation=ObserveBoardPossession(f.board,BindPlayerBoardPossessionObservation(owners));
    if(!state.registry.CanTransition(current,requested))
    {
        error="Physical state transition "+std::string(PhysicalStateName(current))+" -> "
            +std::string(PhysicalStateName(requested))+" requires its native Enter/Exit production adapter";
        return false;
    }
    auto& player=owners.input.player;
    StateChangeData data{{player.state_count_1312,player.state_value_1336,player.state_timer_1344},
        {p.flags_2480,std::uint32_t(requested),p.state_2504,p.state_2508,p.category_2512,
            p.category_2516,p.player_state_value_2520,p.state_count_2564,p.state_timer_2664},
        f.controller_fields};
    LiveBoardPossessionEffects effects(f.board,owners.ground_lifecycle.board_animated_290,
        f.board_wiping_out,f.possession_live,f.settings.board.collision,p.timestep_2604);
    BoardPossessionTransition transition(f.possession,observation,effects,data.skateboard_controller);
    ControllerActions actions(transition);CoreCalls calls(state.registry);
    StateBinding result{};std::uint32_t unknown=0;
    if(!state.lifecycle.SetPhysicsState(std::uint32_t(requested),data,calls,actions,result,unknown))
    {error="Unknown physical state "+std::to_string(unknown);return false;}
    transition.Finish(data.skateboard_controller);
    f.possession_live.PublishVolumes(f.settings.board.collision);
    player.state_count_1312=data.player.word_1312;
    player.state_value_1336=data.player.previous_category_latch_1336;
    player.state_timer_1344=data.player.scalar_1344;
    p.flags_2480=data.processed.flags_2480;
    p.state_2504=data.processed.previous_state_2504;
    p.state_2508=data.processed.current_state_2508;
    p.category_2512=data.processed.current_category_2512;
    p.category_2516=data.processed.previous_category_2516;
    p.player_state_value_2520=data.processed.previous_category_latch_2520;
    p.state_count_2564=data.processed.word_2564;
    p.state_timer_2664=data.processed.scalar_2664;
    f.controller_fields=data.skateboard_controller;
    if(!owners.input.toolkit)
        owners.input.toolkit=BoardToolkit::FromBoard(f.board,p.flags_2468,p.scalar_2612,
            Value(p.vectors_464_480_496_512_528[0]),{0,1,0,0});
    if(!phases.Exit(current,requested,error)||!phases.Enter(requested,error))return false;
    return owners.exchange.RequestState(requested,error);
}
bool InitializePlayerPhysicalState(PlayerStateCoordinatorOwners owners,
    PlayerStatePhaseDispatch& phases,std::string& error)
{
    if(owners.state.initialized){error.clear();return true;}
    if(!SetPlayerPhysicalState(owners,PhysicalStateId::PhysicsGround,phases,error))return false;
    owners.state.initialized=true;error.clear();return true;
}
bool SelectPlayerPhysicalState(PlayerStateCoordinatorOwners owners,const ProcessedPhysicsSnapshot& snapshot,
    PlayerStatePhaseDispatch& phases,std::string& error)
{
    assert(snapshot.tick==owners.physical.ticks);
    const auto& p=snapshot.input;const auto& state=owners.state;
    StateSelectionInput input{{p.grind.family_1248,p.grind.valid_1488,
        static_cast<std::int32_t>(p.external_physics_1616.flags),p.flags_2468,p.flags_2472,
        p.flags_2476,p.flags_2480,p.flags_2484,p.flags_2488,p.category_2512,
        static_cast<std::int32_t>(p.wheel_count_2556),state.post.state_frames,p.state_timer_2664,
        owners.animation_input.fields.slide,owners.animation_input.extra.revert_direction,
        p.air_scalar_2772,p.grind.flags_1516},owners.physical.riding.ground.wheel_contact_count,
        {owners.physical.riding.wheel_lines.minimum_distance,
            owners.physical.riding.ground.time_without_wheel_contact},
        {owners.skeleton_input.force_mode,owners.physical.drive_frames[0][2][1],state.animated_board_threshold},
        state.skitching_off_ground,state.normal_off_ground};
    const auto current=owners.state.Current();PhysicalStateId requested;
    if(!owners.state.selector.Calculate(current,input,requested,error))return false;
    owners.state.requested_state=requested;
    if(requested!=current)
    {
        owners.input.player.ground_history_frames_1304=100;
        if(!SetPlayerPhysicalState(owners,requested,phases,error))return false;
    }
    owners.wipeout.ClearAfterSelection();error.clear();return true;
}
}
