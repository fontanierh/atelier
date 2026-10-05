// SPDX-License-Identifier: Apache-2.0
#include "PlayerInputPhase.h"
#include "GravityScale.h"
#include "StockSettingsReader.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float F(std::uint32_t w) {float f;std::memcpy(&f,&w,4);return f;}
std::uint32_t W(float f) {std::uint32_t w;std::memcpy(&w,&f,4);return w;}
Vec4 Floats(RawVector v) {Vec4 f;for (std::size_t i=0;i<4;++i) f[i]=F(v[i]);return f;}
RawVector Words(Vec4 v) {RawVector w;for (std::size_t i=0;i<4;++i) w[i]=W(v[i]);return w;}
void Replace(std::uint32_t& w,unsigned bit,bool set) {w=(w&~(1u<<bit))|(std::uint32_t(set)<<bit);}
void Byte(std::uint32_t& w,unsigned bit,std::uint8_t value) {w=(w&~(1u<<bit))|(std::uint32_t(value&1)<<bit);}
void Transfer(std::uint32_t& w,unsigned bit,std::uint32_t source,unsigned source_bit) {w=(w&~(1u<<bit))|(((source>>source_bit)&1)<<bit);}
float Select(float test,float nonnegative,float negative) {return test>=-0.0f ? nonnegative : negative;}
bool Service(bool ok,InputPhaseError& error) {if (!ok) error.kind=InputPhaseError::Kind::Service;return ok;}
void PublishPlayerFlags(PlayerInputState& p,ProcessedPhysicsInput& o)
{
    Transfer(o.flags_2472,14,p.flags_1296,27);Transfer(o.flags_2488,26,p.flags_1296,20);
    o.vectors_880_896_912_928_944[3]=p.queued_vector_1280;Transfer(o.flags_2488,22,p.flags_1296,18);
    Transfer(o.flags_2480,16,p.flags_1296,17);p.queued_vector_1280={};p.flags_1296&=~(1u<<20);
}
void PublishPacket(const AnimationInputPacket& p,ProcessedPhysicsInput& o)
{
    ProcessedPacketFields f{o.flags_2468,o.flags_2476,o.timestep_2604,o.scalar_2668,o.vector_1520,o.matrix_1536,o.byte_1600,o.truck_tightness_2760,o.scalar_2764};
    PublishAnimationPacket(p.publication,f);o.flags_2468=f.flags_2468;o.flags_2476=f.flags_2476;o.timestep_2604=f.timestep;o.scalar_2668=f.scalar_2668;o.vector_1520=f.vector_1520;o.matrix_1536=f.matrix_1536;o.byte_1600=f.byte_1600;o.truck_tightness_2760=f.truck_tightness;o.scalar_2764=f.scalar_2764;
}
bool SelectSurface(const PlayerInputState& p,const AnimationInputPacket& packet,std::uint32_t requested,ProcessedPhysicsInput& o,InputPhaseError& error)
{
    const auto index=packet.state_variant_10928;
    if (index>=p.state_variants_1408.size()) {o.state_variant_index_2528=index;error.kind=InputPhaseError::Kind::InvalidStateVariant;error.state_variant=index;return false;}
    o.state_variant_ref_2548=NativeRelativeReference{NativeReferenceBase::Player,std::uint16_t(0x580+0x10*index)};o.state_variant_index_2528=index;
    if (p.state_variants_1408[index].surface_override_enabled_60!=0)
    {if (requested>=1&&requested<=3) requested=1;else if (requested==5) requested=3;else if (requested==13) requested=2;}
    const auto mode=requested>=1&&requested<=5 ? requested : requested==6 ? 3u : 1u;
    constexpr std::array<std::uint16_t,5> primary{24,40,56,72,88},secondary{104,116,128,140,152};
    o.surface_mode_2540=mode;o.surface_primary_ref_2544=NativeRelativeReference{NativeReferenceBase::SurfaceSelector,primary[mode-1]};o.surface_secondary_ref_2552=NativeRelativeReference{NativeReferenceBase::SurfaceSelector,secondary[mode-1]};return true;
}
void PublishExternal(PlayerInputState& p,const AnimationInputPacket& packet,ProcessedPhysicsInput& o)
{
    if (packet.use_external_physics_10688!=0)
    {
        o.flags_2472|=1u<<29;o.external_physics_1616.CopyFrom(packet.external_physics_10512);
        if ((o.external_physics_1616.flags&(1u<<26))!=0) p.external_physics_cache_1008.CopyFrom(packet.external_physics_10512);
        else
        {
            for (std::size_t i=5;i<9;++i) o.external_physics_1616.vectors[i]=p.external_physics_cache_1008.vectors[i];
            o.external_physics_1616.vectors[9]=p.external_physics_cache_1008.vectors[9];Transfer(o.external_physics_1616.flags,27,p.external_physics_cache_1008.flags,27);o.external_physics_1616.flags|=1u<<26;
        }
    }
    Byte(o.flags_2472,28,packet.external_physics_flag_10689);
}
void PublishState(PlayerInputState& p,const PhysicalPlayerInput& f,const AnimationInputPacket& packet,std::uint32_t state,ProcessedPhysicsInput& o)
{
    Transfer(o.flags_2468,13,p.flags_1296,31);Replace(o.flags_2468,18,(o.flags_2468&(1u<<2))!=0||o.probe_1792.byte_104!=0);
    p.frames_since_teleport_1328=(p.flags_1296&(1u<<29))!=0 ? 0u : p.frames_since_teleport_1328+1u;o.frames_since_teleport_2584=p.frames_since_teleport_1328;p.flags_1296&=~(1u<<29);
    o.state_count_2564=p.state_count_1312;o.state_timer_2664=p.state_timer_1344;o.update_count_2568=p.update_count_1316;
    Byte(o.flags_2472,12,packet.flag_10373);Byte(o.flags_2468,0,packet.flag_10786);Byte(o.flags_2472,31,packet.flag_10787);
    o.state_2508=state;o.state_2504=state;o.category_2512=f.state.category_12;
    Byte(o.flags_2472,30,f.state.flag_61);Byte(o.flags_2472,18,f.state.flag_69);Byte(o.flags_2480,31,f.state.flag_74);
    o.grind_words_2532_2536=f.grinds.words_136_140;o.category_2516=f.state.category_12;o.player_state_value_2520=p.state_value_1336;
}
void PublishPhysical(const PhysicalPlayerInput& f,const AnimationInputPacket& p,ProcessedPhysicsInput& o)
{
    o.vectors_400_416={f.skateboard.vector_80,f.skateboard.vector_96};o.scalar_2736=f.skateboard.scalar_172;o.scalar_2612=f.skateboard.scalar_168;o.scalar_2656=f.skateboard.scalar_164;o.scalar_2652=f.skateboard.scalar_160;
    o.vectors_720_784_800_816_832_864[0]=f.skateboard.vector_64;o.vectors_720_784_800_816_832_864[1]=f.skateboard.vector_128;o.vectors_720_784_800_816_832_864[2]=f.skateboard.vector_144;
    o.vectors_624_640_656_672[0]=p.vector_10816;o.vectors_624_640_656_672[1]=p.vector_10832;Transfer(o.flags_2476,6,p.flags_10932,31);Transfer(o.flags_2476,5,p.flags_10932,30);Transfer(o.flags_2476,4,p.flags_10932,29);
    o.scalar_2696=p.scalar_10912;o.vectors_624_640_656_672[2]=p.vector_10848;o.scalar_2700=p.scalar_10916;o.vectors_624_640_656_672[3]=p.vector_10864;
    Byte(o.flags_2480,0,p.flag_10369);o.vectors_880_896_912_928_944[0]=p.vector_10880;o.vectors_880_896_912_928_944[1]=p.vector_10896;Transfer(o.flags_2488,24,p.flags_10932,22);
    o.vectors_544_560_592_608[2]=f.reckoning.vector_64;o.vectors_880_896_912_928_944[4]=f.reckoning.vector_144;Byte(o.flags_2488,21,f.reckoning.flag_164);
    o.vectors_544_560_592_608[3]=f.air.use_air_reckoning_452!=0 ? f.air.vector_160 : f.reckoning.vector_16;o.vectors_544_560_592_608[0]=f.reckoning.vector_96;o.vectors_544_560_592_608[1]=f.board_reckoning_side_176;
    o.vectors_464_480_496_512_528[0]=f.ground.vector_96;o.vectors_464_480_496_512_528[4]=f.ground.vector_64;o.vectors_720_784_800_816_832_864[4]=f.ground.vector_128;
    Byte(o.flags_2476,27,f.ground.flag_317);Byte(o.flags_2476,23,f.ground.flag_318);o.air_scalar_2772=f.air.scalar_184;
    Byte(o.flags_2476,26,f.air.flag_441);Byte(o.flags_2476,0,f.air.flag_446);Byte(o.flags_2480,25,f.air.flag_447);Byte(o.flags_2480,24,f.air.flag_448);
    Transfer(o.flags_2480,30,f.component_1832_word_1876,28);Byte(o.flags_2468,9,f.grinds.flag_318);Byte(o.flags_2468,8,f.grinds.flag_322);
    Byte(o.flags_2468,15,f.collision.flag_3478);Byte(o.flags_2468,16,f.collision.flag_3475);Byte(o.flags_2468,17,f.collision.flag_3472);o.wheel_count_2556=f.collision.wheel_count_0;Byte(o.flags_2468,14,f.collision.flag_3477);
    o.collision_scalar_2924=f.collision.scalar_28;Byte(o.flags_2488,30,f.collision.flag_3481);Byte(o.flags_2472,11,f.physics.flag_32);o.vectors_720_784_800_816_832_864[3]=f.physics.vector_16;
    Byte(o.flags_2472,9,f.skeleton.flag_597);Byte(o.flags_2480,10,f.skeleton.flag_600);Byte(o.flags_2480,9,f.skeleton.flag_601);o.filtered_state_2524=f.filtered_state_0;
    Byte(o.flags_2476,21,f.off_board.flag_304);Replace(o.flags_2476,17,f.off_board.scalar_32<=0.0f);Byte(o.flags_2480,15,f.off_board.flag_311);Byte(o.flags_2476,16,f.off_board.flag_315);Byte(o.flags_2476,8,f.off_board.flag_316);
    o.off_board_scalar_2832=f.off_board.scalar_32;Byte(o.flags_2480,1,f.off_board.flag_318);Byte(o.flags_2484,23,f.off_board.flag_314);o.vectors_880_896_912_928_944[2]=f.off_board.vector_64;Byte(o.flags_2484,16,f.off_board.flag_328);
    const auto wheel=f.collision.wheel_contact_3296_3299;const bool tail=wheel[2]!=0||wheel[3]!=0,nose=wheel[0]!=0||wheel[1]!=0,left=wheel[2]!=0||wheel[0]!=0,right=wheel[3]!=0||wheel[1]!=0,switched=(o.flags_2468&(1u<<20))!=0;
    Replace(o.flags_2472,27,switched ? nose : tail);Replace(o.flags_2472,26,switched ? tail : nose);Replace(o.flags_2472,25,switched ? right : left);Replace(o.flags_2472,24,switched ? left : right);
}
void UpdateTimers(PlayerInputState& p,const PhysicalPlayerInput& f,ProcessedPhysicsInput& o)
{
    if (f.state.state_16==104) {p.skitch_timer_1376=2.0f;p.skitch_value_1372=f.state.skitch_value_40;}
    if (p.skitch_timer_1376>0.0f) {p.skitch_timer_1376-=o.timestep_2604;o.skitch_value_2592=p.skitch_value_1372;}
    if (f.ground.scalar_292>0.0f) p.ground_timer_1380=f.ground.scalar_292;
    if (p.ground_timer_1380>0.0f) {p.ground_timer_1380-=o.timestep_2604;o.ground_timer_2848=p.ground_timer_1380;o.skitch_value_2592=p.skitch_value_1372;}
    if (f.ground.scalar_296>0.0f) p.secondary_ground_timer_1384=f.ground.scalar_296;
    if (p.secondary_ground_timer_1384>0.0f) {p.secondary_ground_timer_1384-=o.timestep_2604;o.secondary_ground_timer_2852=p.secondary_ground_timer_1384;}
}
void PostSkeleton(PlayerInputState& p,const PhysicalPlayerInput& f,ProcessedPhysicsInput& o)
{
    if ((o.flags_2472&(1u<<21))!=0) Byte(o.flags_2472,21,f.state.flag_66);
    Replace(o.flags_2476,3,p.skitch_timer_1376>0.0f||((o.flags_2476&(1u<<22))!=0&&f.ground.scalar_276>=0.0f));
    p.time_since_last_input_1348=(o.flags_2472&(1u<<23))!=0 ? p.time_since_last_input_1348+o.timestep_2604 : 0.0f;o.time_since_last_input_2748=p.time_since_last_input_1348;
    p.prepared_jump_velocity_1184=(o.flags_2468&(1u<<21))!=0 ? o.vectors_400_416[1] : PlayerPreparedJumpVelocity({o.vectors_400_416[1],p.prepared_jump_velocity_1184});
    p.spin_same_direction_frames_1324=o.spin_input_2672*p.previous_spin_input_1360<=0.0f ? 0u : p.spin_same_direction_frames_1324+1u;p.previous_spin_input_1360=o.spin_input_2672;
    o.spin_same_direction_frames_2580=p.spin_same_direction_frames_1324;o.prepared_jump_704=p.prepared_jump_velocity_1184;o.crouch_delta_2780=o.crouch_2776-p.previous_crouch_1364;p.previous_crouch_1364=o.crouch_2776;
}
}
GroundHistoryResult PlayerGroundHistory(GroundHistoryRequest r)
{
    const auto old=Floats(r.previous_position),current=Floats(r.current_position),previous=Floats(r.previous_filtered_delta);
    Vec4 delta,filtered;for (std::size_t i=0;i<4;++i) delta[i]=current[i]-old[i];
    float reciprocal=ReciprocalEstimate(F(r.timestep_bits));for (unsigned i=0;i<2;++i) reciprocal=std::fma(reciprocal,std::fma(-reciprocal,F(r.timestep_bits),1.0f),reciprocal);
    const float retention=F(0x3f733333),change=1.0f-retention;
    for (std::size_t i=0;i<4;++i) filtered[i]=std::fma(previous[i],retention,reciprocal*(delta[i]*change));
    return {Words(delta),Words(filtered)};
}
RawVector PlayerPreparedJumpVelocity(PrepareJumpRequest r)
{
    const auto velocity=Floats(r.skateboard_vector),previous=Floats(r.previous_velocity);
    const float squared=Dot3(velocity,velocity),inverse=InverseLengthSquared(squared,2),length=squared==0.0f ? 0.0f : squared*inverse;
    Vec4 direction{},result;if (length>F(0x358637bd)) for (std::size_t i=0;i<4;++i) direction[i]=velocity[i]*inverse;
    const float acceleration=F(W(direction[1])^0x80000000)*(F(0x411ccccd)*GravityScale());
    for (std::size_t i=0;i<4;++i) result[i]=std::fma(direction[i]*acceleration,F(0x3c888889),previous[i]);
    return Words(result);
}
bool StartPlayerInputPhase(PlayerInputState& p,PhysicalPlayerInput& f,const AnimationInputPacket& packet,ProcessedPhysicsInput& o,InputPhaseServices& s,InputContinuation& continuation,InputPhaseError& error)
{
    error={};const auto captured_state=f.state.state_16;const auto decremented=p.manager_1856_counter_320-1u;p.manager_1856_counter_320=decremented>=0x80000000 ? 0u : decremented;
    if (!Service(s.UpdatePreInputManager(p,f,error.service),error)) return false;
    p.manager_1852_flag_256=0;const auto captured_category=f.state.category_12;
    if (!Service(s.ResetProcessedInput(o,error.service),error)) return false;
    PublishPlayerFlags(p,o);
    std::uint32_t query=0;
    if (!Service(s.ActorQuery56(query,error.service),error)) return false;
    o.actor_query_2948=query;
    if (!Service(s.ActorQuery44(query,error.service),error)) return false;
    o.actor_query_2952=query;
    const bool braking=packet.force_braking_10796!=0&&std::int32_t(p.state_count_1312)>5&&f.skateboard.scalar_160<F(0x3dcccccd)&&f.state.state_16==100&&std::int32_t(f.collision.wheel_count_0)>2;
    Replace(o.flags_2476,24,braking);o.probe_1792=p.probe;
    if (!Service(s.ResetPlayerProbe(p,f,error.service),error)) return false;
    Byte(o.flags_2484,26,f.collision.flag_215);Byte(o.flags_2484,22,f.collision.flag_216);o.vectors_720_784_800_816_832_864[5]=p.manager_1852_vector_176;PublishPacket(packet,o);o.state_identifier_2496=f.state.identifier_8;
    if (!Service(s.CheckTeleport(p,f,o,error.service),error)) return false;
    continuation={captured_state,captured_category};return true;
}
bool FinishPlayerInputPhase(InputContinuation continuation,PlayerInputState& p,PhysicalPlayerInput& f,const AnimationInputPacket& packet,ProcessedPhysicsInput& o,InputPhaseServices& s,InputPhaseError& error)
{
    error={};const auto category=continuation.captured_category;Transfer(o.flags_2472,10,p.flags_1296,29);bool available=false;
    if (!Service(s.ActorInputAvailable(available,error.service),error)) return false;
    if (available)
    {
        if (packet.suppress_transition_10376!=0) o.transition_2636=0.0f;
        else {float v=0;if (!Service(s.TransitionAction(v,error.service),error)) return false;const float lower=Select(-1.0f-v,-1.0f,v);o.transition_2636=Select(1.0f-lower,lower,1.0f);}
    }
    const float previous=p.signed_ground_time_1356;p.signed_ground_time_1356=f.state.signed_ground_step_84!=0 ? Select(previous,previous,0.0f)+F(0x3c888889) : Select(previous,0.0f,previous)-F(0x3c888889);o.signed_ground_time_2756=p.signed_ground_time_1356;
    if (category==100) {o.flags_2472|=1u<<13;++p.grounded_frames_1300;p.time_on_ground_1352+=o.timestep_2604;Replace(p.flags_1296,31,std::int32_t(p.grounded_frames_1300)>6);}
    else {p.time_on_ground_1352=0.0f;p.grounded_frames_1300=0;}
    o.time_on_ground_2752=p.time_on_ground_1352;
    if (!SelectSurface(p,packet,f.surface_default_mode,o,error)) return false;
    Byte(o.flags_2476,2,packet.flag_10370);PublishExternal(p,packet,o);PublishState(p,f,packet,continuation.captured_state,o);PublishPhysical(f,packet,o);UpdateTimers(p,f,o);
    if (category==500) {p.current_ground_position_1216=f.skeleton.anim_to_world_11920[3];p.time_off_board_1368+=F(0x3c888889);}
    else {RawVector position{};if (!Service(s.CalculateGroundPosition(f,position,error.service),error)) return false;p.current_ground_position_1216=position;p.time_off_board_1368=0.0f;}
    o.time_off_board_2836=p.time_off_board_1368;o.effective_anim_transform_192=f.skeleton.anim_to_world_11920;
    if ((o.flags_2476&(1u<<2))!=0) for (auto row:std::array<unsigned,2>{0,2}) for (auto& v:o.effective_anim_transform_192[row]) v=W(-F(v));
    if (category!=200&&category!=600&&p.ground_history_frames_1304>0)
    {
        const auto old=p.previous_ground_position_1200;p.previous_ground_position_1200=p.current_ground_position_1216;
        if (o.frames_since_teleport_2584>1) {const auto r=PlayerGroundHistory({old,p.current_ground_position_1216,p.damped_ground_delta_1248,W(o.timestep_2604)});p.ground_delta_1232=r.delta;p.damped_ground_delta_1248=r.filtered_delta;}
    }
    o.vectors_464_480_496_512_528[1]=p.previous_ground_position_1200;o.vectors_464_480_496_512_528[2]=p.current_ground_position_1216;o.vectors_464_480_496_512_528[3]=p.damped_ground_delta_1248;
    if (!Service(s.PrepareBoardToolkit(p,f,o,error.service),error)) return false;
    o.line_tests_960_1008_1056={p.left_line_test_1536,p.right_line_test_1584,p.hips_line_test_1488};if (o.line_tests_960_1008_1056[0].valid!=0) o.left_surface_2596=o.line_tests_960_1008_1056[0].surface;if (o.line_tests_960_1008_1056[1].valid!=0) o.right_surface_2600=o.line_tests_960_1008_1056[1].surface;
    if (!Service(s.ProcessSkeleton(packet,f,o,error.service),error)) return false;
    PostSkeleton(p,f,o);return Service(s.UpdateGrindManager(p,f,o,error.service),error);
}
bool ProcessPlayerInputPhase(PlayerInputState& p,PhysicalPlayerInput& f,const AnimationInputPacket& packet,ProcessedPhysicsInput& o,InputPhaseServices& s,InputPhaseError& error)
{InputContinuation c;return StartPlayerInputPhase(p,f,packet,o,s,c,error)&&FinishPlayerInputPhase(c,p,f,packet,o,s,error);}
bool LoadPlayerInputState(const SettingsDatabase& data,PlayerInputState& output,std::string& error)
{
    PlayerInputState p;p.flags_1296=0xe00c0000;p.ground_history_frames_1304=100;p.external_physics_cache_1008.vectors[8].fill(0xbf800000);StockSettingsReader reader(data);constexpr std::array<std::string_view,5> modes{"easy","normal","hardcore","motorized","test"};
    for (std::size_t i=0;i<5;++i) {bool enabled=false;if (!reader.Boolean("physics_mode",modes[i],"Hash_5548109D7B0CB70C",enabled,error)) return false;p.state_variants_1408[i].surface_override_enabled_60=std::uint8_t(enabled);}
    output=p;error.clear();return true;
}
void ResetProcessedPhysicsInput(ProcessedPhysicsInput& input)
{
    ProcessedPhysicsInput r;r.effective_anim_transform_192={RawVector{0x3f800000,0,0,0},RawVector{0,0x3f800000,0,0},RawVector{0,0,0x3f800000,0},RawVector{}};r.vector_1520=input.vector_1520;r.matrix_1536=input.matrix_1536;r.byte_1600=input.byte_1600;r.external_physics_1616=input.external_physics_1616;r.probe_1792=input.probe_1792;
    r.flags_2468=0x2000|(input.flags_2468&8);r.flags_2488=input.flags_2488&0x001fffff;r.state_variant_index_2528=1;r.grind_words_2532_2536={0xffffffff,0};r.timestep_2604=F(0x3c888889);r.gravity_2648=(F(0xc11ccccd)*GravityScale());r.actor_query_2952=0xffffffff;r.external_physics_1616.flags&=0x01ffffff;r.vectors_544_560_592_608[0]={0,0x3f800000,0,0};r.vectors_720_784_800_816_832_864[4]=input.vectors_720_784_800_816_832_864[4];input=r;
}
void ResetPhysicalPlayerOutputs(PhysicalPlayerInput& out)
{
    PhysicalPlayerInput r;r.surface_default_mode=out.surface_default_mode;r.component_1832_word_1876=out.component_1832_word_1876;r.skeleton.anim_to_world_11920=out.skeleton.anim_to_world_11920;r.air.handplant_flags_324=out.air.handplant_flags_324&~0xb0000000;r.air.landing_normal_144={0,0x3f800000,0,0};r.air.selected_trajectory_240[3].fill(0xbf800000);r.reckoning.vector_96={0,0x3f800000,0,0};r.ground.vector_64={0,0x3f800000,0,0};r.ground.vector_80=r.ground.vector_64;r.ground.vector_96=r.ground.vector_64;r.ground.scalar_276=-1.0f;r.grinds.words_136_140={0xffffffff,0};out=r;
}
}
