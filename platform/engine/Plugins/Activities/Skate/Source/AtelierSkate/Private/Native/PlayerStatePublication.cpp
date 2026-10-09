#include "PlayerStatePublication.h"
#include <cassert>
#include <cstring>
namespace atelier::skate
{
namespace
{
RawVector Words(const Vec4& value)
{RawVector words;std::memcpy(words.data(),value.data(),sizeof(words));return words;}
void CheckSharedOwners(const PlayerStatePublicationOwners& o)
{
    static_cast<void>(o); // The same source-only checks also compile with NDEBUG.
    // Identity checks only: no physical values or histories are reconstructed.
    assert(&o.shared.physical==&o.air.physical&& &o.shared.physical==&o.biped.physical
        && &o.shared.physical==&o.landing.shared.physical&& &o.shared.physical==&o.grind.physical
        && &o.shared.physical==&o.wipeout.physical);
    assert(&o.shared.input==&o.grind.input&& &o.shared.input==&o.wipeout.input);
    assert(&o.shared.input.processed==&o.air.processed&& &o.shared.input.processed==&o.biped.processed
        && &o.shared.input.processed==&o.landing.shared.processed);
    assert(&o.shared.input.physical==&o.biped.publication&& &o.shared.input.physical==&o.landing.shared.publication);
    assert(&o.shared.input.toolkit==&o.air.toolkit&& &o.shared.input.toolkit==&o.biped.toolkit
        && &o.shared.input.toolkit==&o.landing.shared.toolkit);
    assert(&o.air.ground==&o.biped.ground&& &o.air.ground==&o.grind.ground&& &o.air.ground==&o.wipeout.ground);
    assert(&o.shared.ground_lifecycle==&o.air.life&& &o.shared.ground_lifecycle==&o.biped.life
        && &o.shared.ground_lifecycle==&o.landing.shared.life&& &o.shared.ground_lifecycle==&o.grind.life
        && &o.shared.ground_lifecycle==&o.wipeout.life);
    assert(&o.shared.skeleton_input==&o.air.skeleton_input&& &o.shared.skeleton_input==&o.biped.skeleton_input
        && &o.shared.skeleton_input==&o.grind.skeleton_input&& &o.shared.skeleton_input==&o.wipeout.skeleton_input);
    assert(&o.shared.animation_input==&o.air.animation_input&& &o.shared.animation_input==&o.biped.animation_input
        && &o.shared.animation_input==&o.grind.animation_input&& &o.shared.animation_input==&o.wipeout.animation_input);
    assert(&o.shared.ik==&o.air.ik&& &o.shared.ik==&o.biped.ik&& &o.shared.ik==&o.grind.ik&& &o.shared.ik==&o.wipeout.ik);
    assert(&o.shared.wipeout==&o.air.wipeout.state&& &o.shared.wipeout==&o.biped.wipeout.state
        && &o.shared.wipeout==&o.grind.wipeout&& &o.shared.wipeout==&o.wipeout.wipeout.state);
    assert(&o.air.animated==&o.biped.animated&& &o.air.animated==&o.grind.animated&& &o.air.animated==&o.wipeout.animated);
    assert(&o.air.packet==&o.landing.pose&& &o.air.packet.hierarchy==&o.biped.hierarchy
        && &o.air.packet.hierarchy==&o.grind.globals&& &o.air.packet.hierarchy==&o.wipeout.globals);
    assert(&o.air.post.jump_reference==&o.shared.state.post.jump_reference
        && &o.air.post.jump_fix_frames==&o.shared.state.post.jump_fix_frames);
    assert(&o.air.ground_runtime==&o.grind.ground_runtime&& &o.air.trajectory==&o.grind.trajectory
        && &o.air.skeleton_air==&o.biped.skeleton_air&& &o.air.skeleton_air==&o.grind.skeleton_air
        && &o.air.air_reckoning==&o.biped.air_reckoning&& &o.air.air_reckoning==&o.grind.air_reckoning);
    assert(&o.landing.biped==&o.biped_ground&& &o.biped.feet==&o.landing.shared.feet
        && &o.biped.landing==&o.landing.shared.landing);
}
void PublishPossession(PlayerStatePublicationOwners o)
{
    const auto out=o.shared.physical.PublishPossession(BindPlayerBoardPossession(o.shared),
        o.shared.input.toolkit?std::optional<Mat4>(o.shared.input.toolkit->deck):std::nullopt);
    auto& p=o.shared.input.physical.off_board;
    p.angle_36=out.angle_36;p.angle_40=out.angle_40;p.flag_311=std::uint8_t(out.held_311);
    p.free_board_312=std::uint8_t(out.free_312);p.returning_board_313=std::uint8_t(out.returning_313);
    p.hiding_board_321=std::uint8_t(out.hiding_321);p.dropping_board_322=std::uint8_t(out.flag_322);
    p.retrieving_board_323=std::uint8_t(out.flag_323);p.flag_324=std::uint8_t(out.flag_324);
}
bool SupportedFill(PhysicalStateId state)
{
    if(IsGrindState(state)||state==PhysicalStateId::Nonspecific)return true;
    switch(state)
    {
    case PhysicalStateId::PhysicsGround:case PhysicalStateId::PhysicsAir:
    case PhysicalStateId::FootPlant:case PhysicalStateId::Boneless:case PhysicalStateId::HandPlant:
    case PhysicalStateId::RevertGround:case PhysicalStateId::KnownAir:case PhysicalStateId::BipedAir:
    case PhysicalStateId::BipedGround:case PhysicalStateId::OffBoardPushing:
    case PhysicalStateId::GroundAnimation:case PhysicalStateId::SlideGround:
    case PhysicalStateId::WipeoutGround:case PhysicalStateId::Teleporting:
    case PhysicalStateId::LandingOnDeck:return true;
    default:return false;
    }
}
}
bool PublishPlayerPhysicalState(PlayerStatePublicationOwners o,std::string& error)
{
    CheckSharedOwners(o);
    const auto state=o.shared.state.Current();
    PublishPossession(o);
    auto& physical=o.shared.input.physical;
    const auto& biped=o.biped_ground.controller.state;
    physical.off_board.vector_64=Words(biped.frame_output.velocity);
    physical.off_board.cadence_phase_80=biped.cadence.phase.phase;
    physical.off_board.locomotion_state_84=biped.cadence.locomotion_index;
    if(!SupportedFill(state))
    {error="FillPhysOut requires the actual "+std::string(PhysicalStateName(state))+" output owner";return false;}
    if(state==PhysicalStateId::KnownAir)
    {KnownAirOutput output;if(!o.known_air.Fill(o.air,physical.air,output,error))return false;}
    if(state==PhysicalStateId::BipedAir)o.biped_air.Fill(o.biped);
    if(state==PhysicalStateId::LandingOnDeck&&!o.landing_on_deck.Fill(o.landing,error))return false;
    if((IsGrindState(state)||state==PhysicalStateId::Nonspecific)&&!o.grind_runtime.Fill(o.grind,error))return false;
    std::optional<BipedStatePublication> offboard_ground;
    if(state==PhysicalStateId::BipedGround||state==PhysicalStateId::OffBoardPushing)
    {BipedStatePublication output;if(!o.biped_ground.Fill(o.biped,output,error))return false;offboard_ground=output;}
    const auto& p=o.shared.input.processed;
    if(!o.shared.input.toolkit){error="State output requires actual board toolkit";return false;}
    std::optional<PhysicsGroundOutput> output;
    if(state==PhysicalStateId::PhysicsGround)
        output=o.air.ground.Output(p,o.shared.animation_input,*o.shared.input.toolkit);
    auto& player=o.shared.input.player;
    auto& host=o.shared.state;
    host.state_count=player.state_count_1312;host.update_count=player.update_count_1316;
    auto& flags=host.state_flags;flags.fill(false);
    const auto set=[&flags](std::size_t offset,bool value){flags[offset-52]=value;};
    set(52,(p.flags_2468&(1u<<30))!=0);set(54,(p.flags_2468&(1u<<29))!=0);
    set(55,(p.flags_2468&(1u<<25))!=0);set(56,(p.flags_2468&(1u<<27))!=0);
    set(57,(p.flags_2468&(1u<<26))!=0);set(58,(p.flags_2468&(1u<<28))!=0);
    set(59,(p.flags_2468&(1u<<18))!=0);set(60,o.shared.animation_input.fields.balance!=0.0f);
    set(62,(p.flags_2472&(1u<<10))!=0);
    set(63,state==PhysicalStateId::LandingOnDeck&&o.landing_on_deck.state.RequestsBoardFlip());
    set(66,state==PhysicalStateId::RevertGround&&o.revert.active);
    set(65,o.air.wipeout.RequestsWipeout(p));set(78,o.air.wipeout.RequestsRunout(p));
    set(71,(player.flags_1296&(1u<<24))!=0);set(73,(p.flags_2476&(1u<<24))!=0);
    set(74,state==PhysicalStateId::HandPlant&&o.handplant.continuation);
    set(75,PhysicalStateCategory(state)==500);set(76,std::uint32_t(state)==500);
    if(p.state_identifier_2496==500)player.dismount_request_frames_1332=3;
    const bool dismount_requested=player.dismount_request_frames_1332>0;
    if(dismount_requested)--player.dismount_request_frames_1332;
    set(77,dismount_requested);set(79,p.state_variant_index_2528==3);
    set(80,(p.flags_2484&(1u<<21))!=0);set(83,o.air.footplant.perform||o.air.footplant.flag_627);
    if(output)
    {
        set(84,output->state_28.flag_84);set(86,output->state_28.has_world_grab_intent_without_object);
        if(output->state_28.manual_correction_write_78)set(78,*output->state_28.manual_correction_write_78);
    }
    set(87,(p.flags_2484&(1u<<10))!=0);
    if(offboard_ground)set(86,offboard_ground->flag_86);
    if(state==PhysicalStateId::SlideGround)set(84,o.slide.wall_riding);
    physical.component_1832_word_1876=o.handplant.flags;
    physical.air.handplant_position_304=Words(o.handplant.anchor);
    physical.air.handplant_time_320=o.handplant.phase;
    physical.air.flag_446=std::uint8_t((o.handplant.flags&0x80000000u)!=0);
    o.air.footplant.Publish(physical.air);
    physical.off_board.flag_308=std::uint8_t((p.flags_2480&(1u<<19))!=0);
    const auto& selection=o.air.trajectory.selector.Selection();
    physical.air.flag_444=std::uint8_t(selection&&selection->wall_ride);
    physical.air.flag_441=std::uint8_t(o.air.air_reckoning.state.flip_active);
    if(state==PhysicalStateId::GroundAnimation)o.ground_animation.Fill(p,physical.air);
    physical.state=CurrentStateFields{};
    physical.state.category_12=PhysicalStateCategory(state);physical.state.state_16=std::uint32_t(state);
    physical.state.flag_66=std::uint8_t(state==PhysicalStateId::RevertGround&&o.revert.active);
    physical.state.flag_74=std::uint8_t(state==PhysicalStateId::HandPlant&&o.handplant.continuation);
    physical.state.flag_69=std::uint8_t(host.selector.request_teleport);
    set(69,physical.state.flag_69!=0);
    if(offboard_ground)
    {physical.state.counter_36=offboard_ground->word_36;physical.state.skitch_value_40=offboard_ground->word_40;}
    if(output)
    {
        physical.state.skitch_value_40=output->state_28.grab_spline_object_id;
        physical.state.signed_ground_step_84=std::uint8_t(output->state_28.flag_84);
        physical.ground.vector_128=Words(output->ground_32.anti_flip_torque);
        physical.ground.scalar_276=output->ground_32.time_to_skitch;
        physical.ground.flag_317=std::uint8_t(output->ground_32.anti_flip_nudge_present);
        physical.ground.flag_318=std::uint8_t(output->ground_32.is_pinning);
        physical.off_board.flag_304=std::uint8_t(output->is_grabbing_object_72_304);
        physical.animation.manual_opposition_168=std::uint8_t(output->manual_opposition_56_168);
    }
    else if(state==PhysicalStateId::PhysicsAir)o.air_runtime.Fill(physical.air);
    else if(state==PhysicalStateId::SlideGround)physical.state.signed_ground_step_84=std::uint8_t(o.slide.wall_riding);
    physical.air.handplant_flags_324=(physical.air.handplant_flags_324&0x0fffffffu)
        |(physical.component_1832_word_1876&0xf0000000u);
    if(output&&output->velocity_projection_36)
    {
        physical.reckoning.vector_144=Words(output->velocity_projection_36->velocity_without_axis_component);
        physical.reckoning.flag_164=std::uint8_t(output->velocity_projection_36->active);
    }
    if(!host.conditioning.Publish(o.grind_runtime,o.grind,host.lifecycle,output,o.known_air.state,o.air.packet,error))return false;
    host.ground_output=output;
    if(state==PhysicalStateId::WipeoutGround)PublishWipeoutPlayerState(o);
    if(state==PhysicalStateId::Teleporting)o.teleport.PublishOutput(physical);
    error.clear();return true;
}
void PublishWipeoutPlayerState(PlayerStatePublicationOwners o)
{
    const auto output=o.wipeout_runtime.Fill(o.wipeout);
    auto& physical=o.shared.input.physical;auto& skeleton=physical.skeleton;
    skeleton.over_599=std::uint8_t(output.over_599);skeleton.scalar_544=output.scalar_544;
    skeleton.no_support_time_548=output.no_support_time_548;skeleton.response_strength_580=output.response_strength_580;
    skeleton.extra_weight_584=output.extra_weight_584;skeleton.time_until_teleport_576=output.time_until_teleport_576;
    skeleton.teleport_pending_604=std::uint8_t(output.teleport_pending_604);
    skeleton.hips_right_angle_496=output.hips_right_angle_496;skeleton.hips_up_angle_500=output.hips_up_angle_500;
    if(output.response_change_588)
    {skeleton.response_change_588=*output.response_change_588;skeleton.response_changed_605=1;}
    physical.animation.collision_time_144=output.collision_time_144;physical.animation.profile_148=output.profile_148;
    physical.collision.flag_3479=std::uint8_t(output.material_ten_3479);
    physical.collision.flag_3480=std::uint8_t(output.material_eleven_3480);
    physical.collision.flag_3483=std::uint8_t(output.imminent_surface_twelve_3483);
    physical.collision.predicted_position_64=Words(output.predicted_position_64);
    if(output.retained_air_velocity_160)
    {physical.air.vector_160=Words(*output.retained_air_velocity_160);physical.air.use_air_reckoning_452=1;}
    physical.state.surface_height_32=output.surface_height_32;
    auto& flags=o.shared.state.state_flags;
    flags[72-52]=output.can_leave_72;flags[81-52]=output.special_surface_81;
    flags[82-52]=output.below_surface_82;flags[83-52]=output.surface_height_valid_83;
    if(output.teleport_countdown_68)flags[68-52]=true;
    if(output.request_teleport_69){flags[69-52]=true;physical.state.flag_69=1;}
}
}
