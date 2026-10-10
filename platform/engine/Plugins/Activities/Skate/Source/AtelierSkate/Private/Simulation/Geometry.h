#pragma once
#include "SimulationMath.h"
#include <optional>

namespace atelier::skate
{
struct ClosestTrianglePoint
{
    Vec3 point;
    std::uint32_t region = 0;
    float u = 0.0f, v = 0.0f;
};
struct TriangleLineHit
{
    Vec3 position, normal;
    float fraction = 0.0f;
    std::array<float,3> volume_parameter{};
};
ClosestTrianglePoint ClosestPointOnTriangle(Vec3 point, const std::array<Vec3,3>& vertices);
std::optional<TriangleLineHit> ThinTriangleSegment(Vec3 start, Vec3 direction, const std::array<Vec3,3>& vertices);
float SampleShakeBezier(const Mat4& points, float input);
}
