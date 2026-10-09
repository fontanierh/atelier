#include "CameraPublication.h"
#include <charconv>
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
namespace {
Vec4 FromRaw(RawVector raw) {
  Vec4 result;
  for (std::size_t i = 0; i < 4; ++i)
    result[i] = Bits(raw[i]);
  return result;
}
std::string DebugFloat(float value) {
  if (std::isnan(value))
    return "NaN";
  if (std::isinf(value))
    return std::signbit(value) ? "-inf" : "inf";
  char buffer[64];
  const auto converted = std::to_chars(buffer, buffer + sizeof(buffer), value);
  std::string text(buffer, converted.ptr);
  const auto exponent = text.find('e');
  if (exponent != std::string::npos) {
    auto first = exponent + 1;
    if (first < text.size() && text[first] == '+')
      text.erase(first, 1);
    if (first < text.size() && text[first] == '-')
      ++first;
    while (first + 1 < text.size() && text[first] == '0')
      text.erase(first, 1);
  } else if (text.find('.') == std::string::npos)
    text += ".0";
  return text;
}
std::string DebugVector(Vec4 value) {
  std::string text = "[";
  for (std::size_t i = 0; i < 4; ++i) {
    if (i)
      text += ", ";
    text += DebugFloat(value[i]);
  }
  return text + "]";
}
std::string DebugRaw(RawVector value) {
  std::string text = "[";
  for (std::size_t i = 0; i < 4; ++i) {
    if (i)
      text += ", ";
    text += std::to_string(value[i]);
  }
  return text + "]";
}
bool Finite3(Vec4 value) {
  return std::isfinite(value[0]) && std::isfinite(value[1]) &&
         std::isfinite(value[2]);
}
} // namespace
Mat4 EffectiveCameraSkeletonRoot(Mat4 root, std::uint32_t flags_2476) {
  if ((flags_2476 & 4) != 0) {
    for (auto &lane : root[0])
      lane = -lane;
    for (auto &lane : root[2])
      lane = -lane;
  }
  return root;
}
bool PublishCameraSubject(const CameraPublicationFrame &frame,
                          const CameraPublicationInputs &input,
                          CameraSubjectSnapshot &output, std::string &error) {
  const auto &p = frame.physical;
  const auto &processed = frame.processed;
  if (!frame.toolkit) {
    error = "Camera publication requires the completed player input toolkit";
    return false;
  }
  const auto ground =
      frame.ground.Output(processed, frame.animation_input, *frame.toolkit);
  const auto deck =
      frame.physics.board.PartTransforms()[std::size_t(BoardBodyId::Deck)];
  Mat4 physical_transform{};
  for (std::size_t column = 0; column < 3; ++column)
    for (std::size_t lane = 0; lane < 3; ++lane)
      physical_transform[column][lane] =
          frame.physics.riding.motion.effective_basis.columns[column][lane];
  physical_transform[3] = {deck.translation.x, deck.translation.y,
                           deck.translation.z, 0.0f};
  const auto skeleton_root = EffectiveCameraSkeletonRoot(
      frame.physics.roots.animation_to_world, processed.flags_2476);
  const auto &record = frame.physics.skeleton.record;
  const auto com = FromRaw(p.reckoning.vector_64),
             up = FromRaw(p.reckoning.vector_96);
  const auto velocity = FromRaw(p.skateboard.vector_80),
             acceleration = FromRaw(p.skateboard.vector_64);
  const auto finite = [&](std::string_view name, Vec4 value) {
    if (Finite3(value))
      return true;
    error = "Camera subject owner published non-finite " + std::string(name) +
            ": " + DebugVector(value) +
            "; state=" + std::to_string(processed.state_2508) +
            "; category=" + std::to_string(processed.category_2512);
    return false;
  };
  if (!finite("centre_of_mass", com) || !finite("reckoning_up", up) ||
      !finite("damped_centre_of_mass", input.damped_com_80) ||
      !finite("ground_up", input.ground_up_80))
    return false;
  for (const auto &column : skeleton_root)
    if (!finite("skeleton_root", column))
      return false;
  const std::array<std::pair<std::size_t, std::string_view>, 4> checked{
      {{1, "head"}, {15, "left_foot"}, {19, "right_foot"}, {23, "hips"}}};
  for (const auto &entry : checked)
    if (!finite(entry.second, record.pose[entry.first][3]))
      return false;
  if (!Finite3(velocity) || !Finite3(acceleration)) {
    error = "Camera received non-finite board motion publication: velocity=" +
            DebugVector(velocity) +
            "; acceleration=" + DebugVector(acceleration) +
            "; raw_velocity=" + DebugRaw(p.skateboard.vector_80) +
            "; raw_acceleration=" + DebugRaw(p.skateboard.vector_64);
    return false;
  }
  const auto last_ground_up = FromRaw(p.ground.vector_96);
  const auto category = p.state.category_12, state = p.state.state_16;
  const auto &off = input.offboard;
  const auto &air = input.air;
  const bool alternate = off.use_trajectory_331 != 0;
  const auto launch_position =
      alternate ? off.launch_position_176 : air.launch_position_48;
  const auto launch_normal = alternate ? off.launch_normal_160 : last_ground_up;
  const auto landing_position =
      alternate ? off.landing_position_208 : air.landing_position_16;
  const auto landing_normal =
      alternate ? off.landing_normal_192 : air.landing_normal_32;
  const auto apex_position = alternate ? off.apex_240 : air.apex_0;
  const auto heading = alternate ? off.heading_224 : air.heading_80;
  const auto trajectory_time = alternate ? off.time_152 : air.time_176;
  const auto trajectory_duration =
      alternate ? off.duration_92 : air.duration_180;
  const auto apex_time = alternate ? off.apex_time_156 : air.apex_time_196;
  const auto grinding = input.grinds.grinding_316;
  std::array<float, 2> look;
  for (std::size_t i = 0; i < 2; ++i)
    look[i] = input.preferences.invert_look[i] ? -input.look_552_556[i]
                                               : input.look_552_556[i];
  ManagerSubject subject;
  subject.rig = {physical_transform,
                 skeleton_root,
                 record.pose[23][3],
                 last_ground_up,
                 {},
                 input.context,
                 frame.ground.pumping.pump_acceleration,
                 input.state.height_32,
                 std::uint8_t(category == 100),
                 grinding,
                 alternate ? std::uint8_t(1) : p.air.known_air_valid_437,
                 input.state.wiping_out_59,
                 input.state.physically_pushing_55,
                 std::uint8_t(ground.skateboard_motion_4.is_at_pushable_speed),
                 std::uint8_t(category == 500),
                 p.air.use_air_reckoning_452,
                 input.state.flag_81,
                 std::uint8_t(input.events.broken_bone_duration_200 > 0.0f &&
                              (input.events.capabilities_204 & 4) != 0),
                 0};
  subject.anchors = Anchors{}.entries;
  subject.compass = {};
  subject.board_offset_direction = up;
  subject.ground_normal = input.ground_up_80;
  subject.launch_position = launch_position;
  subject.launch_normal = launch_normal;
  subject.landing_position = landing_position;
  subject.landing_normal = landing_normal;
  subject.apex_position = apex_position;
  subject.direction_424 = input.grinds.direction_0;
  subject.look = look;
  subject.steering = {
      input.animation.conditioned_turn[4], input.animation.conditioned_turn[3],
      input.animation.input_turn_64, input.animation.input_kickturn_68};
  subject.trajectory_time = trajectory_time;
  subject.trajectory_duration = trajectory_duration;
  subject.apex_time = apex_time;
  subject.value_512 = input.preferences.value_32;
  subject.value_516 = input.ground_scalar_288;
  subject.reset = input.state.reset_62;
  subject.flag_556 = air.flag_440;
  subject.stance_560 = input.animation.stance_155;
  subject.stance_592 = input.animation.skater_animation_stance;
  subject.flag_652 = input.state.flag_79;
  subject.shake_variant = input.preferences.shake_variant;
  subject.special_effect = 0;
  subject.flag_684 = off.object_held_304;
  CameraSubjectSnapshot result;
  result.tick = input.tick;
  result.subject = subject;
  result.pose = {physical_transform,
                 skeleton_root,
                 com,
                 input.damped_com_80,
                 input.state.wiping_out_59 != 0,
                 input.state.use_skeleton_root_75 != 0};
  result.anchors = {physical_transform[3],
                    velocity,
                    acceleration,
                    up,
                    com,
                    input.damped_com_80,
                    skeleton_root[1],
                    input.grinds.camera_target_96,
                    grinding != 0,
                    input.state.reset_62 != 0};
  result.reference_points = {record.pose[1][3],
                             record.pose[23][3],
                             record.pose[15][3],
                             record.pose[19][3],
                             skeleton_root[3],
                             com,
                             input.damped_com_80,
                             input.grinds.camera_target_96,
                             {},
                             {},
                             grinding};
  result.compass = {skeleton_root[2], input.collision_look_target_64, velocity,
                    heading, state == 103};
  result.graph = {input.animation.time_since_input_128,
                  input.animation.wipeout_tweak_148,
                  category == 200,
                  input.events.preparing_52 != 0,
                  input.state.manual_60 != 0 && input.events.intent_51 == 0,
                  state == 501,
                  input.animation.running_out_160 != 0,
                  state == 601,
                  state == 600,
                  input.events.hippy_jump_322 != 0,
                  off.hurdle_317 != 0,
                  input.events.trick_125 != 0,
                  state == 502,
                  state == 104,
                  input.events.dropping_in_63 != 0 && off.dropping_in_334 != 0,
                  p.air.scalar_184};
  output = std::move(result);
  error.clear();
  return true;
}
} // namespace atelier::skate::camera
