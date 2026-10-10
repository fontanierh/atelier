#pragma once
#include "CameraShots.h"
namespace atelier::skate::camera {
struct ShakeSamples {
  std::vector<Vec4> rotations, translations;
};
struct ShakeSettings {
  Mat4 amplitude_curve{}, frequency_curve{};
  float impulse_magnitude = 0, impulse_minimum_velocity = 0,
        impulse_maximum_velocity = 0, impulse_frequency = 0, impulse_decay = 0;
  float amplitude_minimum = 0, amplitude_maximum = 0, amplitude_top_speed = 0,
        frequency_minimum = 0, frequency_maximum = 0, frequency_top_speed = 0;
  float data_frames_per_second = 0, translation_multiplier = 0,
        rotation_multiplier = 0, dutch_multiplier = 0;
};
struct ShakeEffect {
  Vec4 translation{};
  float time = 0, impulse = 0, weight = 0;
  bool LandingImpulse(Vec4 normal, Vec4 velocity, ShakeSettings settings);
  bool Update(float dt, float speed, float distance, Basis3 basis, bool enabled,
              const ShakeSamples &samples, ShakeSettings settings,
              Basis3 &result, std::string &error);
};
struct LookSettings {
  float heading_offset_degrees = 0, heading_speed = 0,
        elevation_offset_degrees = 0, elevation_speed = 0;
};
struct LookInput {
  float elevation = 0, heading = 0;
  void Update(std::array<float, 2> input, LookSettings settings);
};
struct FrameSettings {
  float maximum_pitch_degrees = 0, roll_response = 0;
};
struct FrameSubject {
  std::array<Vec4, 10> positions{};
  Vec4 board_offset_direction{};
};
struct FrameComposer {
  float roll = 0;
  Vec4 reference{};
  float yaw = 0, pitch = 0;
  Quat Compose(float dt, float fraction, float mirror, Shot from, Shot to,
               Vec4 fallback_reference, Vec4 camera_position,
               FrameSubject subject, FrameSettings settings);
  Quat Single(Shot shot, Vec4 fallback_reference, Vec4 camera_position,
              float mirror, FrameSubject subject, FrameSettings settings);
};
Quat QuaternionFromBasis(Basis3 basis);
struct SlowMotionSettings {
  PointGraph<16> timescale;
  float fps_at_scale_one = 0;
  struct SimulationRateRequest Request(float progress) const;
};
struct SimulationRateRequest {
  float timestep = 0;
  std::uint32_t ticks = 0;
};
struct SlowMotionController {
  float elapsed = 0, air_duration = 0, time_before_prediction = 0;
  bool latched_prediction = false;
  static std::pair<SlowMotionController, SimulationRateRequest>
  Begin(SlowMotionSettings settings);
  SimulationRateRequest Update(float dt, float duration,
                               SlowMotionSettings settings);
  static SimulationRateRequest End();
};
struct CameraFrame {
  Basis3 basis;
  Vec4 position{};
  Basis3 previous_basis;
  Vec4 previous_position{}, linear_velocity{}, angular_velocity{},
      shake_translation{};
  bool discontinuity = false;
  float field_of_view_degrees = 0, opacity = 1, blur = 1;
  CameraFrame();
  bool Motion(float dt, Basis3 value, Vec4 point, std::string &error);
};
float LensFieldOfView(float lens, float aspect);
} // namespace atelier::skate::camera
