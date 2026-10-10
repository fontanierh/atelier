#pragma once
#include "SimulationMath.h"
#include <variant>

namespace atelier::skate
{
struct AffineTransform
{
    Basis3 basis{std::array<std::array<float,3>,3>{{{1,0,0},{0,1,0},{0,0,1}}}};
    Vec3 translation{};
};
struct ContactMaterial
{
    float static_friction=0, dynamic_friction=0, restitution=0;
};
struct TriangleFeature
{
    Vec3 normal{};
    std::array<Vec3,3> edges{};
    std::uint32_t flags=0;
    std::array<float,3> edge_cosines{};
};
struct Triangle
{
    std::array<Vec3,3> vertices{};
    TriangleFeature feature{};
    std::array<float,3> edge_lengths{};
    float fatness=0;
};
struct Sphere { Vec3 center{}; float radius=0; };
struct Capsule { Vec3 center{}, axis{}; float half_length=0, radius=0; };
struct RoundedBox { Vec3 center{}; Basis3 basis{}; Vec3 half_extents{}; float radius=0; };
using ContactPrimitive = std::variant<Sphere,Capsule,Triangle,RoundedBox>;
}
