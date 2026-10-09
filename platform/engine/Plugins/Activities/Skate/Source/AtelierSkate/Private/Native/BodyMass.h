#pragma once
#include "NativeMath.h"
#include <optional>
namespace atelier::skate
{
enum class MassShapeKind { Sphere,Capsule,RoundedBox,Cylinder,Unsupported };
struct MassShape
{
    MassShapeKind kind=MassShapeKind::Unsupported;
    float radius=0,half_length=0,padding=0;
    Vec3 half_extents{};
};
struct PrimitiveMass { Vec3 moments_per_unit_mass;float volume; };
// Primitive moments precede aggregate mass scaling and inverse inertia.
std::optional<PrimitiveMass> ComputePrimitiveMass(MassShape shape);
}
