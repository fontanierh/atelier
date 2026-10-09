#include "AnimationPhaseRuntime.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate {
namespace {
float Decode(std::uint32_t word) {
  float out;
  std::memcpy(&out, &word, 4);
  return out;
}
Vec4 Decode(RawVector words) {
  Vec4 out;
  std::memcpy(out.data(), words.data(), sizeof(out));
  return out;
}
Vec4 Lanes(Vec3 v) { return {v.x, v.y, v.z, 0.0f}; }
Vec4 Axis(std::array<float, 3> v) { return {v[0], v[1], v[2], 0.0f}; }
Vec3 Xyz(Vec4 v) { return {v[0], v[1], v[2]}; }
void Append(IntentMap &intents, const std::vector<ControllerIntent> &values) {
  for (const auto &v : values)
    intents.Insert(v.name, v.value);
}
} // namespace
bool AdvanceAnimationPhase(AnimationPhaseOwners o,
                           AnimationPhaseControls controls,
                           const AnimationStockGraphs &graphs,
                           const AnimationProfile &profile, float time_step,
                           AnimationPhaseOutput &output, std::string &error) {
  auto &actor = o.animation;
  auto &motion = actor.motion;
  auto &extra = actor.complete_motion.physical;
  motion.score_packet = {};
  const auto &p = o.input.processed;
  const auto &physical = o.input.physical;
  motion.physical.manual_exit = physical.animation.manual_opposition_168 != 0;
  motion.deck_yaw_pitch = std::array<float, 2>{
      physical.skeleton.deck_yaw_536, physical.skeleton.deck_pitch_540};
  extra.offboard_cadence_phase = physical.off_board.cadence_phase_80;
  motion.physical.offboard_locomotion_state =
      physical.off_board.locomotion_state_84;
  motion.physical.ground_slope_type = physical.off_board.kind_88;
  motion.physical.biped_ground_thin = physical.off_board.flag_330 != 0;
  actor.action.physical_inputs.dropping_in =
      physical.grinds.dropping_in_324 != 0;
  const auto deck = o.physics.board.PartTransforms()[6];
  const auto stance = actor.Stance();
  const bool fakie = stance.first, mirrored = stance.second;
  extra.toggle_board = MotionGraphToggleBoardPhysical{
      physical.off_board.flag_304 != 0,
      physical.off_board.flag_311 != 0,
      physical.off_board.free_board_312 != 0,
      o.state_flags[87 - 52],
      physical.off_board.returning_board_313 != 0,
      physical.off_board.angle_36,
      physical.off_board.angle_40};
  motion.physical.holding_board = extra.toggle_board->holding_board;
  motion.physical.free_board = extra.toggle_board->free_board;
  extra.runout =
      MotionGraphRunoutObservation{physical.off_board.trajectory_valid_331 != 0,
                                   Decode(physical.off_board.vector_64),
                                   Decode(physical.reckoning.vector_16),
                                   Decode(physical.reckoning.vector_96),
                                   o.physics.drive_frames[0][0],
                                   mirrored};
  const auto &feedback = o.feedback;
  motion.wipeout_condition_inputs = MotionGraphWipeoutConditionInputs{
      physical.skeleton.over_599 != 0,
      physical.animation.collision_time_144,
      physical.skeleton.no_support_time_548,
      physical.animation.profile_148,
      o.state_flags[82 - 52],
      o.physics.skeleton.record.pose[23][1][1],
      physical.skeleton.hips_right_angle_496,
      physical.skeleton.hips_up_angle_500};
  motion.landing_inputs =
      MotionGraphLandingInputs{feedback.crouching.animation_height_72,
                               o.conditioning.landing_quality.spin_92,
                               o.conditioning.landing_quality.landing_type_96,
                               motion.riding.last_good_landing_velocity};
  motion.prelanding_inputs = MotionGraphPrelandingInputs{
      physical.air.flag_444 != 0,
      Decode(physical.air.landing_normal_144[1]),
      o.feedback_owner.published_previous_lateral_tilt[0],
      Decode(physical.reckoning.vector_16[1]),
      physical.off_board.flag_316 != 0,
      physical.off_board.flag_319 != 0,
      physical.off_board.scalar_32,
      physical.air.known_air_valid_437 != 0,
      Decode(physical.air.landing_normal_32[1]),
      physical.air.scalar_184,
      feedback.crouching.animation_height_72};
  const auto toes = o.ik.PhysicalToePositions(o.physics.skeleton.record);
  extra.air_leg =
      AnimationAirLegPhysical{Decode(physical.reckoning.vector_16),
                              Decode(physical.reckoning.vector_64),
                              Decode(physical.reckoning.vector_96),
                              toes[0],
                              toes[1],
                              feedback.crouching.animation_height_72,
                              physical.off_board.flag_316 != 0,
                              physical.air.scalar_184};
  actor.action.condition_inputs.physics_requests_dismount =
      o.state_flags[77 - 52];
  actor.action.condition_inputs.physical_state_16 = physical.state.state_16;
  MotionGraphGameplayInputs gameplay;
  gameplay.state = physical.state.state_16;
  gameplay.wants_runout = o.state_flags[78 - 52];
  gameplay.physics_wiping = o.state_flags[59 - 52];
  gameplay.body_flipping = physical.air.flag_441 != 0;
  gameplay.bumped = feedback.bumped;
  gameplay.wants_wipeout = o.state_flags[63 - 52] || o.state_flags[65 - 52];
  gameplay.grabbing_object = physical.off_board.flag_304 != 0;
  gameplay.retrieving_board = physical.off_board.retrieving_board_323 != 0;
  gameplay.dropping_board = physical.off_board.dropping_board_322 != 0;
  gameplay.in_biped_air = physical.off_board.flag_328 != 0;
  gameplay.hippy_hurdling = physical.off_board.hippy_hurdling_317 != 0;
  gameplay.handplant_flags = physical.air.handplant_flags_324;
  gameplay.handplant_time = physical.air.handplant_time_320;
  gameplay.handplant_thresholds = o.handplant.AnimationThresholds();
  gameplay.footplant_active = physical.air.flag_448 != 0;
  gameplay.footplant_duration = physical.air.footplant_duration_212;
  gameplay.footplant_contact_time = physical.air.footplant_contact_time_208;
  gameplay.time_to_skitch = physical.ground.scalar_276;
  gameplay.skitch_transition_time = profile.skitch_transition_time;
  gameplay.time_to_land = physical.air.scalar_184;
  gameplay.time_to_land_valid = physical.air.known_air_valid_437 != 0;
  gameplay.offboard_trajectory_time = physical.off_board.trajectory_time_120;
  gameplay.offboard_trajectory_valid =
      physical.off_board.trajectory_valid_331 != 0;
  gameplay.trucks_or_deck_contact =
      physical.collision.flag_3472 != 0 || physical.collision.flag_3475 != 0;
  gameplay.offboard_time_to_land = physical.off_board.scalar_32;
  gameplay.offboard_air_scalar_92 = physical.off_board.scalar_92;
  gameplay.offboard_air_translation = Decode(physical.off_board.vector_96);
  gameplay.offboard_landing_normal = Decode(physical.off_board.vector_192);
  gameplay.offboard_committed_to_motion = physical.off_board.flag_329 != 0;
  gameplay.offboard_obstacle_distance = physical.off_board.scalar_112;
  gameplay.offboard_edge_distance = physical.off_board.distance_116;
  gameplay.reached_apex = Decode(physical.reckoning.vector_16[1]) < 0.0f;
  gameplay.can_land_on_board = physical.off_board.flag_316 != 0;
  gameplay.landing_turning = physical.off_board.flag_318 != 0;
  gameplay.grind_contact =
      physical.grinds.flag_318 != 0 || physical.grinds.flag_322 != 0;
  gameplay.wheel_contact =
      std::any_of(physical.collision.wheel_contact_3296_3299.begin(),
                  physical.collision.wheel_contact_3296_3299.end(),
                  [](std::uint8_t v) { return v != 0; });
  gameplay.tricks_blocked_on_stairs = false;
  gameplay.moving_object = physical.state.state_16 == 502;
  motion.physical.gameplay = gameplay;
  actor.action.physical_inputs.gameplay_conditions = motion.physical.gameplay;
  extra.landing_velocity = MotionGraphLandingVelocityPublication{
      o.physics.board_frames.com_velocity,
      Lanes(o.physics.riding.reckoning.up)};
  motion.reckoning_z = o.physics.riding.reckoning_frames.ground[2];
  motion.reckoning_ground = o.physics.riding.reckoning_frames.ground;
  extra.bump_acceleration = feedback.ground_acceleration;
  motion.gesture_physical = MotionGraphCharacterGesturePhysical{
      (p.flags_2480 & 0x1000) != 0, physical.state.category_12 == 500,
      profile.gesture_selections, profile.suppress_up_gesture,
      profile.gesture_force_brake_bypass};
  const bool interaction = (p.category_2512 == 100 || p.category_2512 == 500) &&
                           p.probe_1792.bytes_72_73[0] != 0 &&
                           (p.flags_2476 & 0x400000) != 0;
  Vec4 direction{};
  if (interaction) {
    const auto point = Decode(
        p.probe_1792.vectors_16_32_48[(p.flags_2484 & 0x40000) != 0 ? 0 : 1]);
    const auto &inverse = o.physics.roots.world_to_animation;
    for (std::size_t lane = 0; lane < 4; ++lane)
      direction[lane] = std::fma(
          inverse[2][lane], point[2],
          std::fma(inverse[1][lane], point[1],
                   std::fma(inverse[0][lane], point[0], inverse[3][lane])));
  }
  motion.shove_physical = MotionGraphShovePhysical{
      interaction, direction, physical.state.category_12 == 500,
      physical.off_board.flag_311 != 0, feedback.crouching.animation_height_72};
  AnimationStatePublication grind;
  if (!PublishAnimationState(
          physical, o.conditioning.filtered_output,
          feedback.crouching.animation_height_72, mirrored,
          Xyz(Axis(o.physics.riding.motion.effective_basis.columns[2])), grind,
          error))
    return false;
  extra.grind = grind.grind;
  motion.grind_condition_inputs = grind.grind_conditions;
  GraphConditionInputs conditions;
  conditions.speeds = GraphSpeedInputs{o.physics.riding.motion.ground_speed,
                                       o.physics.riding.motion.forward_speed,
                                       o.physics.riding.heading_adjust_factor};
  conditions.physical_state = grind.conditions;
  conditions.time_since_last_input = p.time_since_last_input_2748;
  conditions.mirrored = mirrored;
  conditions.riding_fakie = fakie;
  conditions.push_brake =
      GraphPushBrakeInputs{o.physics.riding.ground.wheel_normal.y,
                           o.ik.state.contacts.support_failed_this_update,
                           profile.maximum_ground_angle_degrees};
  // Native ActionHost stores these two separately in the source; the existing
  // shared native condition record carries both publications through Advance.
  conditions.physics_requests_dismount = o.state_flags[77 - 52];
  conditions.physical_state_16 = physical.state.state_16;
  Vec4 effective_z = o.physics.roots.animation_to_world[2];
  if ((p.flags_2476 & 4) != 0)
    for (auto &v : effective_z)
      v = -v;
  Vec4 effective_x = o.physics.roots.animation_to_world[0];
  if ((p.flags_2476 & 4) != 0)
    for (auto &v : effective_x)
      v = -v;
  motion.riding_condition_inputs = MotionGraphRidingConditionInputs{
      Decode(physical.reckoning.vector_16), effective_x, effective_z,
      deck.basis.columns[1][1], o.physics.riding.ground.wheel_normal.y};
  motion.hold_fakie = o.trainer.hold_fakie;
  const auto deck_position = o.physics.board.Bodies()[6].rates.position;
  const AnimationPhysical observations{
      conditions,
      feedback,
      {o.physics.riding.reckoning_frames.lateral_tilt[0],
       o.air_reckoning.state.spin_speed, physical.filtered_state_0},
      {physical.filtered_state_0, physical.state.state_16,
       motion.flags.doing_trick, effective_z,
       Lanes(o.physics.riding.motion.linear_velocity),
       o.centre_of_mass.velocity, o.physics.riding.motion.ground_speed},
      {actor.packet.regular_stance, actor.packet.riding_switch},
      {o.physics.skeleton.record.pose[15][3],
       o.physics.skeleton.record.pose[19][3], Lanes(deck_position),
       Axis(deck.basis.columns[1]), Axis(deck.basis.columns[2]),
       (p.flags_2468 & (1u << 20)) != 0},
      physical.off_board.flag_311 != 0,
      physical.state.category_12 == 500,
      motion.riding.time_since_teleport};
  IntentMap action_intents = controls.action_intents;
  Append(action_intents, ProduceGrind(controls.controller));
  const auto &contact = o.biped_controller.state.contact;
  for (const auto &v : ProduceOffboardAnalog(
           controls.controller,
           {effective_z, contact.active ? std::optional<Vec4>(contact.direction)
                                        : std::nullopt}))
    action_intents.Insert(v.name, v.value);
  Append(action_intents,
         ProduceOffboardDiscrete(controls.controller, controls.actor_flags,
                                 physical.air.use_air_reckoning_452 != 0));
  AnimationPhaseOutput next;
  if (!actor.Advance(graphs, time_step, action_intents, observations,
                     next.reset, error))
    return false;
  next.Publish(actor.packet, profile, controls.actor_flags);
  if (const auto reply = o.teleport.TakeReply())
    next.PublishExternalReset(*reply);
  output = std::move(next);
  error.clear();
  return true;
}
void PublishAnimationPhaseFeedback(AnimationFeedbackOwners o) {
  o.conditioning.PublishLandingQuality(o.physics, o.input, o.air_reckoning);
  const auto deck = o.physics.board.PartTransforms()[6];
  o.publication = o.conditioner.Update(
      o.physics.riding.motion, o.ground.pumping, o.ground.wobble,
      {Xyz(o.physics.board_frames.centre_of_mass),
       o.physics.riding.reckoning.up, deck.translation,
       o.physics.riding.reckoning_frames.target_lean_angle},
      {o.input.processed.flags_2468, o.animation_input.fields.turn,
       o.animation.packet.mirrored},
      {o.physics.DeckFrame(), o.physics.riding.reckoning_frames.ground,
       Lanes(o.physics.riding.ground.accelerations[6])},
      o.physics.riding.reckoning_frames.lateral_tilt);
}
} // namespace atelier::skate
