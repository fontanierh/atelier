#pragma once
#include "GeometryTypes.h"

namespace atelier::skate
{
enum class TriangleRegion : std::uint32_t { Face,Edge0,Edge1,Vertex1,Edge2,Vertex0,Vertex2 };
struct ContactPair { Vec3 a{},b{}; };
struct TriangleFixup
{
    bool reverse=false;
    float edge_cos_bend_normal_threshold=0,convexity_epsilon=0;
    bool is_object=false;
};
TriangleRegion ClassifyTriangleFeature(const TriangleFeature& triangle,Vec3 direction);
// Acceptance may bend the normal and reproject one side of each pair. Capacity is 16.
bool FixUpTriangle(const TriangleFeature& triangle,Vec3& normal,ContactPair* contacts,
                   std::size_t count,TriangleFixup settings);
}
