#include "BodySpin.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
float Float(std::uint32_t w) {
  float v;
  std::memcpy(&v, &w, 4);
  return v;
}
float Get(const PhysicalBodySpinState &s, std::size_t offset) {
  return Float(s[offset / 4]);
}
void Set(PhysicalBodySpinState &s, std::size_t offset, float v) {
  std::memcpy(&s[offset / 4], &v, 4);
}
float Select(float test, float nonnegative, float negative) {
  return test >= 0.0f ? nonnegative : negative;
}
float Clamp(float value, float lower, float upper) {
  value = Select(lower - value, lower, value);
  return Select(upper - value, value, upper);
}
void UpdateInput(PhysicalBodySpinState &s, float input, float auto_spin,
                 std::uint8_t mode) {
  const float delta = input - Get(s, 120);
  const float derivative = std::fma(delta, 1.5f, Get(s, 124) * 0.0f);
  Set(s, 164, auto_spin);
  Set(s, 120, input);
  s[43] = (s[43] & 0x00ffffffu) | (std::uint32_t(mode) << 24);
  Set(s, 124, derivative);
  const float filtered =
      Clamp(derivative * input > 0.1f ? derivative : 0.0f, -1, 1);
  Set(s, 128, filtered);
  const auto index = s[42];
  Set(s, index * 4, filtered);
  s[42] = (index + 1) % 30;
}
void FinishGround(PhysicalBodySpinState &s, float input) {
  Set(s, 152, 0);
  Set(s, 144, 0);
  Set(s, 140, 0);
  Set(s, 132, std::fma(Get(s, 132), 0.8f, input * 0.2f));
}
void CalculateHistoryDerivative(PhysicalBodySpinState &s,
                                const PointGraph<8> &graph) {
  const std::size_t end = s[42];
  auto index = (end + 29) % 30;
  float time = 0, peak = 0;
  Set(s, 148, 0);
  Set(s, 156, 0);
  while (index != end) {
    time -= Float(0x3c888889);
    const float candidate = graph.Evaluate(time) * Get(s, index * 4);
    if (std::abs(candidate) > std::abs(peak)) {
      peak = candidate;
      Set(s, 156, time);
    }
    index = (index + 29) % 30;
  }
  Set(s, 148, peak);
}
void UpdateAir(PhysicalBodySpinState &s,
               const PhysicalBodySpinSettings &settings, float input,
               float auto_spin, std::uint8_t mode) {
  const std::size_t alternate = mode == 0 ? 1 : 0;
  if (Get(s, 152) == 0.0f)
    CalculateHistoryDerivative(s, settings.curves[3 + alternate]);
  const float time = Get(s, 152);
  const float normal_acceleration = settings.curves[alternate].Evaluate(time);
  const float auto_acceleration = settings.curves[2].Evaluate(time);
  const float derivative_gain = settings.curves[3 + alternate].Evaluate(time);
  const float candidate = derivative_gain * Get(s, 128);
  if (std::abs(candidate) > std::abs(Get(s, 148))) {
    Set(s, 148, candidate);
    Set(s, 156, time);
  }
  const float next_time = time + Float(0x3c888889);
  Set(s, 152, next_time);
  bool fade = true;
  for (float threshold : settings.input_fade_threshold)
    fade = fade && threshold > std::abs(Get(s, 120));
  if (fade) {
    const float faded = Get(s, 132) * 0.96f;
    Set(s, 132, faded);
    Set(s, 120, faded);
  } else
    Set(s, 132, std::fma(Get(s, 132), 0.8f, input * 0.2f));
  const float proportional =
      settings.curves[5 + alternate].Evaluate(next_time) * Get(s, 120);
  Set(s, 144, proportional);
  if (proportional * Get(s, 148) < 0.0f)
    Set(s, 148, 0);
  const float weight =
      std::fma(std::abs(Get(s, 148)), 1.0f - settings.derivative_floor,
               settings.derivative_floor);
  float target = -(weight * proportional), acceleration = normal_acceleration;
  const float old_speed = Get(s, 140);
  if (std::abs(auto_spin) > Float(0x37800000) &&
      (old_speed * auto_spin > 0.0f || std::abs(old_speed) < 0.02f)) {
    acceleration = auto_acceleration;
    target = Clamp(auto_spin, -2, 2);
  }
  const float limited = Select(settings.acceleration_limit - acceleration,
                               acceleration, settings.acceleration_limit);
  const float lower = old_speed > 0.0f ? -limited : -acceleration;
  const float upper = old_speed > 0.0f ? acceleration : limited;
  const float change = Clamp(target - old_speed, lower, upper),
              speed = old_speed + change;
  Set(s, 140, speed);
  Set(s, 160, (target - speed) - change);
}
bool Valid(const PhysicalBodySpinState &s, std::string &error) {
  if (s[42] >= 30) {
    error = "native derivative history index must be 0..30";
    return false;
  }
  error.clear();
  return true;
}
} // namespace
bool SetPhysicalBodySpinWords(PhysicalBodySpinState &output,
                              const PhysicalBodySpinState &words,
                              std::string &error) {
  if (!Valid(words, error))
    return false;
  output = words;
  return true;
}
float PhysicalBodySpinSpeed(const PhysicalBodySpinState &s) {
  return Get(s, 140);
}
bool UpdatePhysicalBodySpin(PhysicalBodySpinState &s,
                            const PhysicalBodySpinSettings &settings,
                            float input, float auto_spin, bool in_air,
                            std::uint8_t mode, std::string &error) {
  if (!Valid(s, error))
    return false;
  UpdateInput(s, input, auto_spin, mode);
  if (!in_air)
    FinishGround(s, input);
  else
    UpdateAir(s, settings, input, auto_spin, mode);
  return true;
}
bool UpdatePhysicalBodySpinGround(PhysicalBodySpinState &s, float input,
                                  std::string &error) {
  if (!Valid(s, error))
    return false;
  UpdateInput(s, input, 0, 0);
  FinishGround(s, input);
  return true;
}
} // namespace atelier::skate
