// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GeometryTriangleFixup.h"
#include <optional>

namespace atelier::skate
{
struct WorldContactSettings
{
    float volume_padding=0,maximum_separating_distance=0;
    float edge_cos_bend_normal_threshold=0,convexity_epsilon=0;
    bool is_object=false;
};
struct PrimitiveContactManifold
{
    Vec3 normal{};
    std::array<ContactPair,16> points{};
    std::size_t count=0;
};
float WorldSeparationLimit(Vec3 velocity,Vec3 triangle_normal,float padding,float maximum);
Triangle TransformTriangleVolume(const std::array<Vec3,3>& vertices,float fatness,
    const std::array<float,3>& edge_cosines,std::uint32_t volume_flags,const AffineTransform& transform);
// Normal faces from the static world triangle toward the moving primitive.
std::optional<PrimitiveContactManifold> PrimitiveTriangleWorldContacts(const ContactPrimitive& primitive,
    const Triangle& triangle,Vec3 velocity,WorldContactSettings settings);
}
