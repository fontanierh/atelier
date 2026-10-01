// SPDX-License-Identifier: Apache-2.0
#include "CameraOutputRuntime.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
namespace {
std::uint8_t Bit(std::uint32_t value, unsigned shift) {
  return (value >> shift) & 1;
}
Vec4 FromRaw(RawVector raw) {
  Vec4 result;
  for (std::size_t i = 0; i < 4; ++i)
    result[i] = Bits(raw[i]);
  return result;
}
CameraOffboardOutput OffboardOutput(const OffBoardOutputFields &output) {
  return {output.scalar_92,
          output.scalar_152,
          output.scalar_156,
          FromRaw(output.vector_160),
          FromRaw(output.vector_176),
          FromRaw(output.vector_192),
          FromRaw(output.vector_208),
          FromRaw(output.vector_224),
          FromRaw(output.vector_240),
          output.flag_308,
          output.hippy_hurdling_317,
          output.trajectory_valid_331,
          output.flag_334};
}
class StaticWorld final : public MovingObstacleProvider {
public:
  std::size_t Collect(Vec4, Vec4, float,
                      std::array<PathObstacle, 50> &) override {
    return 0;
  }
};
} // namespace
CameraPublicationInputs PublishCameraOutput(
    const CameraPublicationFrame &frame, const PhysicalOutputSnapshot &output,
    CameraPreferences preferences, std::uint8_t skater_animation_stance,
    std::uint32_t context, std::uint64_t tick) {
  const auto &p = frame.processed;
  const auto &physical = frame.physical;
  const auto &fields = frame.animation_input.fields;
  const auto intents = frame.animation_input.output.flags;
  const auto &packet = frame.animation.packet;
  return {
      tick,
      {physical.state.surface_height_32, Bit(p.flags_2468, 25),
       Bit(p.flags_2468, 18), std::uint8_t(fields.balance != 0.0f),
       Bit(p.flags_2472, 10), std::uint8_t(physical.state.category_12 == 500),
       std::uint8_t(p.state_variant_index_2528 == 3),
       std::uint8_t(frame.state_flag_81)},
      {frame.feedback.conditioned_turn, fields.turn, p.spin_input_2672,
       p.time_since_last_input_2748, physical.animation.profile_148,
       std::uint8_t(packet.riding_fakie), Bit(p.flags_2480, 2),
       skater_animation_stance},
      {FromRaw(physical.air.trajectory_apex_0),
       FromRaw(physical.air.collision_position_16),
       FromRaw(physical.air.landing_normal_32),
       FromRaw(physical.air.selector_vector_48),
       FromRaw(physical.air.landing_heading_80), physical.air.time_in_state_176,
       physical.air.collision_time_180, physical.air.time_to_apex_196,
       Bit(p.flags_2468, 22)},
      OffboardOutput(physical.off_board),
      {FromRaw(physical.grinds.direction_0),
       FromRaw(physical.grinds.camera_target_96), physical.grinds.grinding_316},
      {Bit(intents, 28), Bit(intents, 27), Bit(intents, 22),
       Bit(p.flags_2480, 11), physical.ground.hippy_jumping_322, 0.0f,
       physical.scoring.capabilities_204},
      frame.centre_of_mass.position,
      {output.ground_normal.x, output.ground_normal.y, output.ground_normal.z,
       0.0f},
      0.0f,
      {frame.animation_input.extra.look_x, frame.animation_input.extra.look_y},
      {output.predicted_position.x, output.predicted_position.y,
       output.predicted_position.z, 0.0f},
      preferences,
      context};
}
bool AdvanceCameraOutput(const CameraPublicationFrame &frame,
                         const SimulationExchange &exchange,
                         CameraRuntime &camera, CameraOutputResult &result,
                         std::string &error) {
  const auto *output = exchange.Output();
  if (!output) {
    error = "Camera requires the completed physical output snapshot";
    return false;
  }
  if (frame.physics.ticks == 0) {
    error = "Camera received physical output before the first completed tick";
    return false;
  }
  const auto completed_tick = frame.physics.ticks - 1;
  if (output->tick != completed_tick || output->state != frame.selected_state) {
    error = "Camera received stale physical output: output_tick=" +
            std::to_string(output->tick) +
            ", completed_tick=" + std::to_string(completed_tick) +
            ", output_state=" + std::string(PhysicalStateName(output->state)) +
            ", selected_state=" +
            std::string(PhysicalStateName(frame.selected_state));
    return false;
  }
  const auto inputs = PublishCameraOutput(
      frame, *output, {{false, false}, 0, 0.0f},
      std::uint8_t(frame.animation.Stance().second), 1, output->tick);
  CameraSubjectSnapshot snapshot;
  if (!PublishCameraSubject(frame, inputs, snapshot, error))
    return false;
  const CameraGraphEnvironment environment{1, false, false, false, {}};
  const auto &simulation = frame.physics.settings.board.step.simulation;
  const auto gravity = simulation.gravity_acceleration;
  StaticWorld moving;
  CameraFrame output_frame;
  if (!camera.Advance(simulation.time_step, std::move(snapshot),
                      frame.physics.world,
                      {gravity.x, gravity.y, gravity.z, 0.0f}, environment,
                      moving, output_frame, error))
    return false;
  result = {output_frame, &camera.simulation_rate_requests};
  error.clear();
  return true;
}
} // namespace atelier::skate::camera
