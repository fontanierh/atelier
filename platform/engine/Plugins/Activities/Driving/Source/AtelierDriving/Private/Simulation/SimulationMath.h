#pragma once

// Pure standard C++ maths for the vehicle simulation. The operation order and rounding are fixed so
// the same inputs produce the same state on every precise-IEEE build.

#include <cmath>
#include <cstdint>

namespace atelier::driving
{
inline constexpr float SIM_PI = 3.14159265358979323846f;
inline constexpr float SIM_TAU = 2.0f * SIM_PI;
// Correctly rounded degree/radian constants, rather than pi/180 computed in f32 (one ULP off).
inline constexpr float DEG_TO_RAD = 0.017453292519943295769236907684886f;
inline constexpr float RAD_TO_DEG = 57.2957795130823208767981548141051703f;

inline float finite_or(float x, float fallback)
{
    return std::isfinite(x) ? x : fallback;
}

inline float clamp(float x, float lo, float hi)
{
    if (x < lo)
    {
        return lo;
    }
    if (x > hi)
    {
        return hi;
    }
    return x;
}

inline float signum(float x)
{
    if (std::isnan(x))
    {
        return x;
    }
    if (x == 0.0f)
    {
        return std::signbit(x) ? -1.0f : 1.0f;
    }
    return x > 0.0f ? 1.0f : -1.0f;
}

inline float lerp(float a, float b, float t)
{
    return a + (b - a) * t;
}

inline float ramp(float x, float lo, float hi)
{
    if (hi - lo <= 0.0f)
    {
        return 0.0f;
    }
    return clamp((x - lo) / (hi - lo), 0.0f, 1.0f);
}

inline float table(const float* values, int count, float lo, float hi, float x)
{
    if (count <= 0)
    {
        return 0.0f;
    }
    if (count == 1)
    {
        return values[0];
    }
    const int last = count - 1;
    if (hi <= lo)
    {
        return values[0];
    }
    float pos = static_cast<float>(last) * (x - lo) / (hi - lo);
    pos = clamp(pos, 0.0f, static_cast<float>(last));
    const int i = static_cast<int>(std::floor(pos));
    const float t = pos - static_cast<float>(i);
    return lerp(values[i], values[i + 1 < last ? i + 1 : last], t);
}

inline float graph(const float (*points)[2], int count, float x)
{
    if (count <= 0)
    {
        return 0.0f;
    }
    if (x <= points[0][0])
    {
        return points[0][1];
    }
    if (x >= points[count - 1][0])
    {
        return points[count - 1][1];
    }
    for (int i = 0; i + 1 < count; ++i)
    {
        const float x0 = points[i][0];
        const float y0 = points[i][1];
        const float x1 = points[i + 1][0];
        const float y1 = points[i + 1][1];
        if (x <= x1)
        {
            if (x1 > x0)
            {
                return lerp(y0, y1, (x - x0) / (x1 - x0));
            }
            return y1;
        }
    }
    return points[count - 1][1];
}

inline float clamp_signed(float x, float limit)
{
    if (std::isfinite(x))
    {
        return clamp(x, -limit, limit);
    }
    return 0.0f;
}

inline void sin_cos(float x, float& s, float& c)
{
    s = std::sin(x);
    c = std::cos(x);
}

struct Vec3
{
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    static constexpr Vec3 splat(float v) { return {v, v, v}; }
    static constexpr Vec3 zero() { return {0.0f, 0.0f, 0.0f}; }
    float& operator[](int i) { return i == 0 ? x : (i == 1 ? y : z); }
    float operator[](int i) const { return i == 0 ? x : (i == 1 ? y : z); }
};

inline constexpr Vec3 VEC3_ZERO{0.0f, 0.0f, 0.0f};
inline constexpr Vec3 VEC3_ONE{1.0f, 1.0f, 1.0f};
inline constexpr Vec3 VEC3_X{1.0f, 0.0f, 0.0f};
inline constexpr Vec3 VEC3_Y{0.0f, 1.0f, 0.0f};
inline constexpr Vec3 VEC3_Z{0.0f, 0.0f, 1.0f};
inline constexpr Vec3 VEC3_NEG_Y{0.0f, -1.0f, 0.0f};

inline Vec3 operator+(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator-(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 operator-(Vec3 a) { return {-a.x, -a.y, -a.z}; }
inline Vec3 operator*(Vec3 a, Vec3 b) { return {a.x * b.x, a.y * b.y, a.z * b.z}; }
inline Vec3 operator*(Vec3 a, float s) { return {a.x * s, a.y * s, a.z * s}; }
inline Vec3 operator*(float s, Vec3 a) { return {s * a.x, s * a.y, s * a.z}; }
inline Vec3 operator/(Vec3 a, Vec3 b) { return {a.x / b.x, a.y / b.y, a.z / b.z}; }
inline Vec3 operator/(Vec3 a, float s) { return {a.x / s, a.y / s, a.z / s}; }
inline Vec3& operator+=(Vec3& a, Vec3 b) { a = a + b; return a; }
inline Vec3& operator-=(Vec3& a, Vec3 b) { a = a - b; return a; }
inline Vec3& operator*=(Vec3& a, float s) { a = a * s; return a; }
inline bool operator==(Vec3 a, Vec3 b) { return a.x == b.x && a.y == b.y && a.z == b.z; }

inline float dot(Vec3 a, Vec3 b)
{
    return (a.x * b.x) + (a.y * b.y) + (a.z * b.z);
}

inline Vec3 cross(Vec3 a, Vec3 b)
{
    return {a.y * b.z - b.y * a.z, a.z * b.x - b.z * a.x, a.x * b.y - b.x * a.y};
}

// The cross used to rotate a vector by a quaternion: the third product is fused.
inline Vec3 cross_fma(Vec3 a, Vec3 b)
{
    return {
        std::fma(-a.z, b.y, a.y * b.z),
        std::fma(-a.x, b.z, a.z * b.x),
        std::fma(-a.y, b.x, a.x * b.y),
    };
}

inline float length_squared(Vec3 a) { return dot(a, a); }
inline float length(Vec3 a) { return std::sqrt(dot(a, a)); }
inline float distance(Vec3 a, Vec3 b) { return length(a - b); }
inline float distance_squared(Vec3 a, Vec3 b) { return length_squared(a - b); }

inline Vec3 normalize(Vec3 a)
{
    const float inv = 1.0f / length(a);
    return a * inv;
}

inline Vec3 normalize_or_zero(Vec3 a)
{
    const float inv = 1.0f / length(a);
    if (std::isfinite(inv) && inv > 0.0f)
    {
        return a * inv;
    }
    return VEC3_ZERO;
}

inline bool try_normalize(Vec3 a, Vec3& out)
{
    const float inv = 1.0f / length(a);
    if (std::isfinite(inv) && inv > 0.0f)
    {
        out = a * inv;
        return true;
    }
    return false;
}

inline Vec3 abs(Vec3 a) { return {std::fabs(a.x), std::fabs(a.y), std::fabs(a.z)}; }
inline Vec3 min(Vec3 a, Vec3 b) { return {std::fmin(a.x, b.x), std::fmin(a.y, b.y), std::fmin(a.z, b.z)}; }
inline Vec3 max(Vec3 a, Vec3 b) { return {std::fmax(a.x, b.x), std::fmax(a.y, b.y), std::fmax(a.z, b.z)}; }
inline Vec3 clamp(Vec3 a, Vec3 lo, Vec3 hi) { return min(max(a, lo), hi); }
inline Vec3 select(const bool mask[3], Vec3 yes, Vec3 no)
{
    return {mask[0] ? yes.x : no.x, mask[1] ? yes.y : no.y, mask[2] ? yes.z : no.z};
}
inline float max_element(Vec3 a) { return std::fmax(std::fmax(a.x, a.y), a.z); }
inline float min_element(Vec3 a) { return std::fmin(std::fmin(a.x, a.y), a.z); }
inline bool is_finite(Vec3 a) { return std::isfinite(a.x) && std::isfinite(a.y) && std::isfinite(a.z); }
inline Vec3 any_orthonormal_vector(Vec3 a)
{
    const float sign = signum(a.z);
    const float k = -1.0f / (sign + a.z);
    const float b = a.x * a.y * k;
    return {b, sign + a.y * a.y * k, -a.y};
}

// Quaternion in (x, y, z, w) layout. Products keep the fixed arithmetic grouping.
struct Quat
{
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float w = 1.0f;
};

inline constexpr Quat QUAT_IDENTITY{0.0f, 0.0f, 0.0f, 1.0f};

inline Quat from_xyzw(float x, float y, float z, float w) { return {x, y, z, w}; }
inline Quat operator+(Quat a, Quat b) { return {a.x + b.x, a.y + b.y, a.z + b.z, a.w + b.w}; }
inline Quat operator-(Quat a) { return {-a.x, -a.y, -a.z, -a.w}; }
inline Quat operator*(Quat a, float s) { return {a.x * s, a.y * s, a.z * s, a.w * s}; }
inline Quat operator*(float s, Quat a) { return {s * a.x, s * a.y, s * a.z, s * a.w}; }

inline float quat_dot(Quat a, Quat b)
{
    return ((a.x * b.x) + (a.y * b.y)) + ((a.z * b.z) + (a.w * b.w));
}

inline float quat_length_squared(Quat q) { return quat_dot(q, q); }
inline float quat_length(Quat q) { return std::sqrt(quat_length_squared(q)); }
inline Quat quat_normalize(Quat q)
{
    const float inv = 1.0f / quat_length(q);
    return {q.x * inv, q.y * inv, q.z * inv, q.w * inv};
}
inline Quat conjugate(Quat q) { return {-q.x, -q.y, -q.z, q.w}; }

inline Quat quat_mul(Quat a, Quat b)
{
    const float x = ((a.w * b.x) + (a.x * b.w)) + ((a.y * b.z) - (a.z * b.y));
    const float y = ((a.w * b.y) - (a.x * b.z)) + ((a.y * b.w) + (a.z * b.x));
    const float z = ((a.w * b.z) + (a.x * b.y)) + (-(a.y * b.x) + (a.z * b.w));
    const float w = ((a.w * b.w) - (a.x * b.x)) + (-(a.y * b.y) - (a.z * b.z));
    return {x, y, z, w};
}

inline Quat operator*(Quat a, Quat b) { return quat_mul(a, b); }

inline Vec3 rotate(Quat q, Vec3 v)
{
    const Vec3 b{q.x, q.y, q.z};
    const float b2 = dot(b, b);
    const Vec3 t1 = v * ((q.w * q.w) - b2);
    const Vec3 t2 = b * (dot(v, b) * 2.0f);
    const Vec3 t3 = cross_fma(b, v) * (q.w * 2.0f);
    return (t1 + t2) + t3;
}

inline Vec3 operator*(Quat q, Vec3 v) { return rotate(q, v); }
inline Quat rotation_x(float angle)
{
    float s, c;
    sin_cos(angle * 0.5f, s, c);
    return {s, 0.0f, 0.0f, c};
}
inline Quat rotation_y(float angle)
{
    float s, c;
    sin_cos(angle * 0.5f, s, c);
    return {0.0f, s, 0.0f, c};
}
inline Quat rotation_z(float angle)
{
    float s, c;
    sin_cos(angle * 0.5f, s, c);
    return {0.0f, 0.0f, s, c};
}
inline Quat from_axis_angle(Vec3 axis, float angle)
{
    float s, c;
    sin_cos(angle * 0.5f, s, c);
    const Vec3 v = axis * s;
    return {v.x, v.y, v.z, c};
}
inline Quat from_rotation_arc(Vec3 from, Vec3 to)
{
    constexpr float ONE_MINUS_EPS = 1.0f - 2.0f * 1.19209290e-7f;
    const float d = dot(from, to);
    if (d > ONE_MINUS_EPS)
    {
        return QUAT_IDENTITY;
    }
    if (d < -ONE_MINUS_EPS)
    {
        return from_axis_angle(any_orthonormal_vector(from), SIM_PI);
    }
    const Vec3 c = cross(from, to);
    return quat_normalize({c.x, c.y, c.z, 1.0f + d});
}

struct Mat3
{
    Vec3 x_axis{1.0f, 0.0f, 0.0f};
    Vec3 y_axis{0.0f, 1.0f, 0.0f};
    Vec3 z_axis{0.0f, 0.0f, 1.0f};
};

inline constexpr Mat3 MAT3_IDENTITY{};
inline constexpr Mat3 MAT3_ZERO{VEC3_ZERO, VEC3_ZERO, VEC3_ZERO};

inline Mat3 from_cols(Vec3 x, Vec3 y, Vec3 z) { return {x, y, z}; }

inline Mat3 mat3_from_quat(Quat r)
{
    const float x2 = r.x + r.x;
    const float y2 = r.y + r.y;
    const float z2 = r.z + r.z;
    const float xx = r.x * x2;
    const float xy = r.x * y2;
    const float xz = r.x * z2;
    const float yy = r.y * y2;
    const float yz = r.y * z2;
    const float zz = r.z * z2;
    const float wx = r.w * x2;
    const float wy = r.w * y2;
    const float wz = r.w * z2;
    return {
        {1.0f - (yy + zz), xy + wz, xz - wy},
        {xy - wz, 1.0f - (xx + zz), yz + wx},
        {xz + wy, yz - wx, 1.0f - (xx + yy)},
    };
}

inline Mat3 from_diagonal(Vec3 v)
{
    return {{v.x, 0.0f, 0.0f}, {0.0f, v.y, 0.0f}, {0.0f, 0.0f, v.z}};
}

inline Mat3 transpose(Mat3 m)
{
    return {{m.x_axis.x, m.y_axis.x, m.z_axis.x},
            {m.x_axis.y, m.y_axis.y, m.z_axis.y},
            {m.x_axis.z, m.y_axis.z, m.z_axis.z}};
}

inline Vec3 mat3_mul(Mat3 m, Vec3 v)
{
    Vec3 res = m.x_axis * v.x;
    res = res + m.y_axis * v.y;
    res = res + m.z_axis * v.z;
    return res;
}

inline Vec3 operator*(Mat3 m, Vec3 v) { return mat3_mul(m, v); }

inline Mat3 mat3_mul(Mat3 a, Mat3 b)
{
    return {a * b.x_axis, a * b.y_axis, a * b.z_axis};
}

inline Mat3 operator*(Mat3 a, Mat3 b) { return mat3_mul(a, b); }

inline Vec3 col(Mat3 m, int i) { return i == 0 ? m.x_axis : (i == 1 ? m.y_axis : m.z_axis); }
inline Vec3 row(Mat3 m, int i)
{
    if (i == 0)
    {
        return {m.x_axis.x, m.y_axis.x, m.z_axis.x};
    }
    if (i == 1)
    {
        return {m.x_axis.y, m.y_axis.y, m.z_axis.y};
    }
    return {m.x_axis.z, m.y_axis.z, m.z_axis.z};
}

inline bool is_finite(Mat3 m) { return is_finite(m.x_axis) && is_finite(m.y_axis) && is_finite(m.z_axis); }
inline bool is_finite(Quat q)
{
    return std::isfinite(q.x) && std::isfinite(q.y) && std::isfinite(q.z) && std::isfinite(q.w);
}

// Unit factors used by the data layer.
inline constexpr float INCH_TO_M = 0.0254f;
inline constexpr float FT_LB_TO_NM = 1.3558f;
inline constexpr float MPH_TO_MS = 0.44703f;
inline constexpr float MS_TO_MPH = 2.2369f;
inline constexpr float LB_IN_TO_N_M = 175.1268f;
inline constexpr float RPM_PER_RAD_S = 9.549296f;
inline constexpr float HP_RPM_CONSTANT = 5252.0f;

inline float rpm_to_rad(float rpm) { return rpm / RPM_PER_RAD_S; }
inline float rad_to_rpm(float rad) { return rad * RPM_PER_RAD_S; }
inline float mph_to_ms(float mph) { return mph * MPH_TO_MS; }
inline float ms_to_mph(float ms) { return ms * MS_TO_MPH; }
inline float inch_to_m(float inch) { return inch * INCH_TO_M; }

} // namespace atelier::driving
