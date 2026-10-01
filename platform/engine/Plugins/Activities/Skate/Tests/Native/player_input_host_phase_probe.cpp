// SPDX-License-Identifier: Apache-2.0
// Appended to a read-only copy of the complete common-publication fixture.
#include "PlayerInputHostPhase.h"
namespace input_host_detail
{
// GENERATED_TRAJECTORY_READERS
// GENERATED_READERS
// GENERATED_INPUT_OBSERVERS
// GENERATED_GRIND_OBSERVERS
struct Actions final:ActionMap
{
    std::array<float,18> values{};std::vector<std::uint32_t> calls;
    float Value(std::uint32_t action) override
    {calls.push_back(action);if(action<64||action>81)std::abort();return values[action-64];}
    std::uint8_t State(std::uint32_t action) override{return std::uint8_t(Value(action)!=0);}
};
void Snapshot(BipedOutput& o,const PlayerInputRuntime& input,const GroundRuntime& ground,const AirTrajectoryRuntime& trajectory)
{
    o.Word(1);Block(o,[&]{
        const auto& r=input;o.Word(trajectory.selector.GrindLockedToMiddle());o.Word(trajectory.selector.Valid());o.Word(r.grind->previous_air_target);o.Word(r.physical.state.flag_61);
        o.Word(bool(r.toolkit));if(r.toolkit){const auto& t=*r.toolkit;for(auto m:{t.deck,t.effective,t.inverse_effective})o.Matrix(m);for(auto v:{t.side,t.up,t.forward,t.horizontal_forward,t.transverse_up,t.forward_velocity,t.travel_direction,t.filtered_normal})o.Floats(v);o.Floats(std::array<float,3>{t.absolute_speed,t.control_sign,t.total_mass});}
        o.Word(bool(r.PendingTeleport()));if(r.PendingTeleport())o.Matrix(*r.PendingTeleport());
        for(auto v:{r.dynamic_normal.normal,r.dynamic_normal.delta,r.dynamic_normal.acceleration,r.dynamic_normal.last_contact_normal})o.Vector(v);
        const auto& s=r.NormalSettings();for(auto v:{s.speed_damping,s.up_vector_damping,s.maximum_delta,s.speed_scale})o.Float(v);o.Curve(s.maximum_delta_vs_speed);
        o.Word(r.pre_input.pending_geometry);HostObserve(o,r.pre_input.result);for(auto v:r.pre_input.result_counts)o.Word(v);
        HostObserveState(o,*r.grind);o.Word(bool(r.pending_grind));if(r.pending_grind)HostObservePending(o,*r.pending_grind);
        o.Word(bool(r.grind_observation));if(r.grind_observation)common_publication::ManagerOut(o,*r.grind_observation);
        o.Floats(ground.retained_board_normal);
    });
}
bool Advance(BipedInput& i,BipedOutput& o,PlayerInputHostPhaseOwners owners,
    PhysicsPosePacket& pose,bool& teleported,std::string& error)
{
    const auto publication=ReadAnimationPacketFields(i);const auto external=ReadExternalPhysicsInput(i);
    const auto packet=ReadPacket(i,publication,external);PacketAttributes attributes;
    const auto n=i.Word();for(unsigned k=0;k<n;++k)attributes.Append(i.Attribute());
    std::vector<AnimationAttribute> active;for(std::size_t k=0;k<attributes.Size();++k)active.push_back(attributes[k]);
    Actions actions;actions.values=i.Floats<18>();const bool available=i.Word()!=0;
    const bool okay=AdvancePlayerInputHostPhase(owners,{packet,pose,active,actions,available},teleported,error);
    o.Word(teleported);o.Word(std::uint32_t(actions.calls.size()));for(auto action:actions.calls)o.Word(action);return okay;
}
bool ConsumePending(PlayerStatePublicationOwners owners,const PlayerGrindMaterials& materials,std::string& error)
{
    auto& input=owners.shared.input;auto& physical=owners.shared.physical;
    if(!input.pending_grind){error="Proof caller has no actual pending grind work";return false;}
    auto pending=std::move(input.pending_grind);const auto& e=owners.shared.animation_input.extra;
    PlayerGrindLiveHost live(physical.board,physical.settings.board,materials);std::optional<PlayerGrindPostResult> result;
    if(!input.grind->PostUpdate(input.processed,physical.world,std::move(*pending),
        {physical.DeckFrame(),owners.shared.animation_input.fields.balance,e.grind_translation,e.grind_stability_nudge,e.grind_up_down,e.grind_grab_min_height},live,result,error))return false;
    input.grind_observation=std::make_unique<PlayerGrindObservation>(result->observation);owners.grind_runtime.Observe(result->observation);
    for(auto reason:result->wipeout_reasons)owners.shared.wipeout.Request(reason,0);return true;
}
}
