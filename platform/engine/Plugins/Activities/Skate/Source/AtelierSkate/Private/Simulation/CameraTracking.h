#pragma once
#include "SimulationMath.h"
#include <optional>
#include <string>

namespace atelier::skate::camera {
float Bits(std::uint32_t word);
float Clamp(float value, float minimum, float maximum);
float FloorZero(float value);
float Interpolate(float minimum, float maximum, float fraction);
float WrapVmx(float angle);
bool NormalizeAngle(float angle, float &result, std::string &error);
float Angle(float angle);
Vec4 DirectionToAngles(Vec4 direction);
Vec4 Add(Vec4 a, Vec4 b);
Vec4 Sub(Vec4 a, Vec4 b);
Vec4 Mul(Vec4 value, float scalar);
Vec4 Madd(Vec4 value, float scalar, Vec4 addend);
Vec4 Horizontal(Vec4 value);
Vec4 ClampMagnitude(Vec4 value, float limit);
Vec4 Normalize(Vec4 value);
float Length(Vec4 value);
float Heading(Vec4 value);
float AtanRatio(float x, float z);
float WrapFloor(float value);
float BlendAngle(float from, float to, float weight);
Quat QuaternionFromAngles(float pitch, float yaw, float roll);
Basis3 BasisFromAngles(float pitch, float yaw, float roll);
Basis3 RotateAboutAxis(Basis3 basis, std::array<float, 3> axis, float angle);
Basis3 LookBasis(std::array<float, 3> at);
Quat Slerp(Quat from, Quat to, float weight);
float SineBlend(float fraction);
struct ScalarTrackerParameters {
  float delta_umbra = 0, delta_penumbra = 0, speed_clamp = 0;
  float acceleration_clamp_min = 0, acceleration_clamp_max = 0;
  float smoothing_min = 0, smoothing_max = 0;
  bool overshoot_zeroes_velocity = false;
};
struct ScalarTracker {
  float target = 0, position = 0, velocity = 0, acceleration = 0,
        acceleration_clamp = 0, smoothing = 0;
  void Update(float dt, float value, ScalarTrackerParameters parameters);
};
struct AngleTracker {
  ScalarTracker state;
  bool Update(float dt, float value, ScalarTrackerParameters parameters,
              std::string &error);
};
struct VectorTracker {
  Vec4 target{}, position{}, velocity{}, acceleration{};
  float acceleration_clamp = 0, smoothing = 0;
  void Update(float dt, Vec4 value, ScalarTrackerParameters parameters);
};
ScalarTrackerParameters MirrorParameters(float speed, float acceleration);
} // namespace atelier::skate::camera
