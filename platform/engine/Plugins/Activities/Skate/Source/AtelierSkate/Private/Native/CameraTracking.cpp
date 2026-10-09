#include "CameraTracking.h"
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
float Bits(std::uint32_t word) {
  float value;
  std::memcpy(&value, &word, 4);
  return value;
}
float Clamp(float v, float low, float high) {
  v = low - v >= 0 ? low : v;
  return high - v >= 0 ? v : high;
}
float FloorZero(float v) { return -v >= 0 ? 0 : v; }
float WrapVmx(float angle) {
  const float tau = Bits(0x40c90fdb), pi = Bits(0x40490fdb),
              turns = std::trunc(RefinedReciprocal(tau) * angle),
              reduced = std::fma(-turns, tau, angle);
  const float lower = reduced + pi >= 0 ? reduced : reduced + tau;
  return reduced - pi >= 0 ? reduced - tau : lower;
}
float AtanRatio(float numerator, float denominator) {
  const float initial = ReciprocalEstimate(denominator),
              inverse = std::fma(initial, std::fma(-initial, denominator, 1.0f),
                                 initial);
  float angle = Atan(std::fma(numerator, inverse, 0.0f));
  std::uint32_t word;
  std::memcpy(&word, &numerator, 4);
  const auto sign = word & 0x80000000;
  if (0 > denominator)
    angle = Bits(0x40490fdb | sign) + angle;
  if (denominator == 0)
    angle = Bits(0x3fc90fdb | sign);
  return angle;
}
float Interpolate(float low, float high, float fraction) {
  return low == high ? high : std::fma(high - low, fraction, low);
}
Vec4 Add(Vec4 a, Vec4 b) {
  for (std::size_t i = 0; i < 4; ++i)
    a[i] = a[i] + b[i];
  return a;
}
Vec4 Sub(Vec4 a, Vec4 b) {
  for (std::size_t i = 0; i < 4; ++i)
    a[i] = a[i] - b[i];
  return a;
}
Vec4 Mul(Vec4 v, float s) {
  for (float &x : v)
    x = x * s;
  return v;
}
Vec4 Madd(Vec4 v, float s, Vec4 a) {
  for (std::size_t i = 0; i < 4; ++i)
    v[i] = std::fma(v[i], s, a[i]);
  return v;
}
Vec4 Horizontal(Vec4 v) {
  v[1] = 0;
  return v;
}
float Length(Vec4 v) { return Length3(v); }
Vec4 Normalize(Vec4 v) { return Normalize3(v); }
Vec4 ClampMagnitude(Vec4 v, float limit) {
  const float length = Length(v);
  return length > limit ? Mul(v, limit / length) : v;
}
bool NormalizeAngle(float angle, float &result, std::string &error) {
  const float pi = Bits(0x40490fdb), tau = Bits(0x40c90fdb);
  if (angle >= -pi && angle < pi) {
    result = angle;
    return true;
  }
  const float turns = angle * Bits(0x3e22f983);
  if (!std::isfinite(turns) ||
      turns < float(std::numeric_limits<std::int32_t>::min()) ||
      double(turns) > double(std::numeric_limits<std::int32_t>::max())) {
    error = "Skate 3 exceptional angle integer conversion is unavailable: "
            "independent implementation required";
    return false;
  }
  const float count = float(static_cast<std::int32_t>(turns));
  const float reduced =
      float(-std::fma(double(count), double(tau), -double(angle)));
  result = reduced >= pi   ? reduced - tau
           : reduced < -pi ? reduced + tau
                           : reduced;
  return true;
}
float Angle(float value) {
  float result = std::numeric_limits<float>::quiet_NaN();
  std::string error;
  NormalizeAngle(value, result, error);
  return result;
}
float WrapFloor(float value) {
  return -std::fma(std::floor(std::fma(value, Bits(0x3e22f983), 0.5f)),
                   Bits(0x40c90fdb), -value);
}
float BlendAngle(float from, float to, float weight) {
  return WrapVmx(std::fma(WrapVmx(to - from), weight, from));
}
namespace {
float AsinLane(float value) {
  const float a = std::abs(value), cube = (value * value) * a;
  float p0 = std::fma(Bits(0x400b1889), a, Bits(0xc0d1360e));
  float p1 = std::fma(Bits(0x3e663246), a, Bits(0xbf983f2f));
  float p2 = std::fma(Bits(0xbed65553), a, Bits(0x408980bd));
  float p3 = std::fma(Bits(0xbd6dd42d), a, Bits(0x3f1dd7b6));
  p0 = std::fma(p0, a, Bits(0x40af6ad8));
  p1 = std::fma(p1, a, Bits(0x3fb58485));
  p2 = std::fma(p2, a, Bits(0xc08f6ad9));
  p3 = std::fma(p3, a, Bits(0xbfaf4418));
  const float left = std::fma(p1, cube, p0), right = std::fma(p3, cube, p2),
              radicand = Bits(0x3f800001) - a;
  float r = ReciprocalSquareRootEstimate(radicand);
  const float correction = std::fma(-(radicand * 0.5f), r * r, 0.5f);
  r = std::fma(r, correction, r);
  return std::fma(std::fma(-a, value, value) * right, r, value * left);
}
float UnitClamp(float value) {
  const float low = -1 > value ? -1 : value;
  return 1 < low ? 1 : low;
}
std::array<float, 3> Cross(std::array<float, 3> a, std::array<float, 3> b) {
  return {std::fma(-a[2], b[1], a[1] * b[2]),
          std::fma(-a[0], b[2], a[2] * b[0]),
          std::fma(-a[1], b[0], a[0] * b[1])};
}
std::array<float, 3> NormalizeArray(std::array<float, 3> v) {
  const auto out = Normalize(Vec4{v[0], v[1], v[2], 0});
  return {out[0], out[1], out[2]};
}
} // namespace
Vec4 DirectionToAngles(Vec4 direction) {
  const float magnitude = Length(Vec4{direction[0], 0, direction[2], 0});
  if (!(magnitude > Bits(0x38d1b717)))
    return {};
  const float inverse = RefinedReciprocal(magnitude),
              x = inverse * direction[0], z = inverse * direction[2];
  float component, base;
  if (x >= 0) {
    if (z >= 0) {
      component = x;
      base = 0;
    } else {
      component = -z;
      base = Bits(0x3fc90fdb);
    }
  } else if (z <= 0) {
    component = -x;
    base = Bits(0x40490fdb);
  } else {
    component = z;
    base = Bits(0x4096cbe4);
  }
  return {AsinLane(UnitClamp(direction[1])),
          Angle(AsinLane(UnitClamp(component)) + base), 0, 0};
}
float Heading(Vec4 v) {
  return v[1] > Bits(0x3f7ff2e5) ? 0 : AtanRatio(-v[0], v[2]);
}
void ScalarTracker::Update(float dt, float value, ScalarTrackerParameters p) {
  const float old = position, delta = value - old;
  target = value;
  if (p.overshoot_zeroes_velocity && velocity * delta < 0)
    velocity *= 0;
  const float v = velocity, inverse = 1 / dt;
  acceleration = std::fma(inverse, delta, -v) * inverse;
  const float magnitude = std::abs(delta);
  const float fraction =
      magnitude < p.delta_umbra ? 1
      : magnitude < p.delta_penumbra
          ? 1 - (magnitude - p.delta_umbra) / (p.delta_penumbra - p.delta_umbra)
          : 0;
  if (acceleration * delta > 0) {
    acceleration_clamp = Interpolate(p.acceleration_clamp_min,
                                     p.acceleration_clamp_max, fraction);
    const float a = std::abs(acceleration);
    if (a > acceleration_clamp)
      acceleration = (acceleration / a) * acceleration_clamp;
  }
  velocity = std::fma(acceleration, dt, v);
  const float speed = std::abs(velocity);
  if (speed > p.speed_clamp)
    velocity = (velocity / speed) * p.speed_clamp;
  const float next = std::fma(velocity, dt, old);
  smoothing = Interpolate(p.smoothing_min, p.smoothing_max, fraction);
  position = std::fma(next - old, 1 - smoothing, old);
}
bool AngleTracker::Update(float dt, float value, ScalarTrackerParameters p,
                          std::string &error) {
  auto &s = state;
  const float old = s.position;
  s.target = value;
  float delta;
  if (!NormalizeAngle(value - old, delta, error))
    return false;
  if (p.overshoot_zeroes_velocity && s.velocity * delta < 0)
    s.velocity *= 0;
  const float v = s.velocity, inverse = 1 / dt;
  s.acceleration = std::fma(inverse, delta, -v) * inverse;
  const float magnitude = std::abs(delta),
              fraction = magnitude < p.delta_umbra ? 1
                         : magnitude < p.delta_penumbra
                             ? 1 - (magnitude - p.delta_umbra) /
                                       (p.delta_penumbra - p.delta_umbra)
                             : 0;
  if (s.acceleration * delta > 0) {
    s.acceleration_clamp = Interpolate(p.acceleration_clamp_min,
                                       p.acceleration_clamp_max, fraction);
    const float a = std::abs(s.acceleration);
    if (a > s.acceleration_clamp)
      s.acceleration = (s.acceleration / a) * s.acceleration_clamp;
  }
  s.velocity = std::fma(s.acceleration, dt, v);
  const float speed = std::abs(s.velocity);
  if (speed > p.speed_clamp)
    s.velocity = (s.velocity / speed) * p.speed_clamp;
  float step, next, displacement, smoothed;
  if (!NormalizeAngle(s.velocity * dt, step, error) ||
      !NormalizeAngle(step + old, next, error))
    return false;
  s.smoothing = Interpolate(p.smoothing_min, p.smoothing_max, fraction);
  if (!NormalizeAngle(next - old, displacement, error) ||
      !NormalizeAngle(displacement * (1 - s.smoothing), smoothed, error) ||
      !NormalizeAngle(smoothed + old, s.position, error))
    return false;
  return true;
}
void VectorTracker::Update(float dt, Vec4 value, ScalarTrackerParameters p) {
  target = value;
  const auto old = position, delta = Sub(value, old);
  if (p.overshoot_zeroes_velocity && Dot3(delta, velocity) < 0)
    velocity = Mul(velocity, 0);
  const float inverse = RefinedReciprocal(dt);
  for (std::size_t i = 0; i < 4; ++i)
    acceleration[i] = (inverse * delta[i] - velocity[i]) * inverse;
  const float magnitude = Length(delta),
              fraction = magnitude < p.delta_umbra ? 1
                         : magnitude < p.delta_penumbra
                             ? 1 - (magnitude - p.delta_umbra) /
                                       (p.delta_penumbra - p.delta_umbra)
                             : 0;
  if (Dot3(acceleration, delta) > 0) {
    acceleration_clamp = Interpolate(p.acceleration_clamp_min,
                                     p.acceleration_clamp_max, fraction);
    acceleration = ClampMagnitude(acceleration, acceleration_clamp);
  }
  velocity = ClampMagnitude(Madd(acceleration, dt, velocity), p.speed_clamp);
  const auto next = Madd(velocity, dt, old);
  smoothing = Interpolate(p.smoothing_min, p.smoothing_max, fraction);
  position = Madd(Sub(next, old), 1 - smoothing, old);
}
ScalarTrackerParameters MirrorParameters(float speed, float acceleration) {
  return {0, 0, speed, acceleration, acceleration, 0.85f, 0.85f, true};
}
Quat QuaternionFromAngles(float pitch, float yaw, float roll) {
  const auto [sp, cp] = SinCos(pitch * 0.5f);
  const auto [sy, cy] = SinCos(yaw * 0.5f);
  const auto [sr, cr] = SinCos(roll * 0.5f);
  const float cp_cr = cp * cr, sp_cr = sp * cr, sp_sr = sp * sr,
              cp_sr = cp * sr;
  return {cy * sp_cr - sy * cp_sr, std::fma(cy, sp_sr, sy * cp_cr),
          cy * cp_sr - sy * sp_cr, std::fma(cy, cp_cr, sy * sp_sr)};
}
Basis3 BasisFromAngles(float pitch, float yaw, float roll) {
  const auto [sp, cp] = SinCos(pitch);
  const auto [sy, cy] = SinCos(yaw);
  const auto [sr, cr] = SinCos(roll);
  const float cp_sr = cp * sr, cp_cr = cp * cr, sp_sr = sp * sr,
              sp_cr = sp * cr;
  return {{{{cy * cr, cy * sr, -sy},
            {sy * sp_cr - cp_sr, std::fma(sy, sp_sr, cp_cr), cy * sp},
            {std::fma(sy, cp_cr, sp_sr), sy * cp_sr - sp_cr, cy * cp}}}};
}
Basis3 RotateAboutAxis(Basis3 basis, std::array<float, 3> axis, float angle) {
  const float cosine = Cos(angle), sine = Sin(angle), x = axis[0], y = axis[1],
              z = axis[2], sx = sine * x, sy = sine * y, sz = sine * z,
              one = 1 - cosine, tx = one * x, ty = one * y, tz = one * z;
  const std::array<std::array<float, 3>, 3> r{
      {{std::fma(x, tx, cosine), std::fma(tx, y, sz), tx * z - sy},
       {ty * x - sz, std::fma(ty, y, cosine), std::fma(ty, z, sx)},
       {std::fma(tz, x, sy), tz * y - sx, std::fma(z, tz, cosine)}}};
  for (auto &c : basis.columns) {
    const auto old = c;
    for (std::size_t i = 0; i < 3; ++i)
      c[i] = std::fma(r[2][i], old[2],
                      std::fma(r[1][i], old[1], r[0][i] * old[0]));
  }
  return basis;
}
Basis3 LookBasis(std::array<float, 3> at) {
  const auto right = NormalizeArray(Cross({0, 1, 0}, at)),
             up = NormalizeArray(Cross(at, right));
  return {{right, up, at}};
}
float SineBlend(float fraction) {
  return std::fma(Sin(std::fma(fraction, Bits(0x40490fdb), -Bits(0x3fc90fdb))),
                  0.5f, 0.5f);
}
Quat Slerp(Quat from, Quat to, float weight) {
  const float dot = Dot4(from, to);
  if (0 > dot)
    from = Mul(from, -1);
  const float absolute = 0 > dot ? -dot : dot;
  if (absolute > Bits(0x3f7f069e)) {
    const bool same = Dot4(from, to) > 0;
    Vec4 value;
    for (std::size_t i = 0; i < 4; ++i)
      value[i] = std::fma(same ? to[i] - from[i] : -(to[i] + from[i]), weight,
                          from[i]);
    return Normalize4(value);
  }
  const float angle = Acos(absolute), inverse = RefinedReciprocal(Sin(angle)),
              first = Sin((1 - weight) * angle) * inverse,
              second = Sin(weight * angle) * inverse;
  return Madd(to, second, Mul(from, first));
}
} // namespace atelier::skate::camera
