#pragma once
#include "AggregateMass.h"
#include "GeometryTypes.h"
#include <vector>

namespace atelier::skate
{
struct DeckGeometrySettings
{
    float width,mid_length,thickness,back_end_size;
    float front_end_angle_degrees,back_end_angle_degrees;
    std::int32_t end_capsule_count;
    bool enable_deck_volume_collisions,enable_end_volume_collisions;
    static DeckGeometrySettings Stock();
};
struct DeckRoundedBox { Vec3 half_extents{};float radius=0; };
struct DeckCapsule { float radius=0,half_length=0; };
struct DeckSphere { float radius=0; };
struct DeckTriangle
{
    std::array<Vec3,3> vertices{};
    float fatness=0;
    std::array<float,3> edge_cosines{};
    // Volume flags; collision_enabled is separate from these authored bits.
    std::uint32_t volume_flags=0;
};
using DeckShape=std::variant<DeckRoundedBox,DeckCapsule,DeckSphere,DeckTriangle>;
struct DeckChild
{
    DeckShape shape;
    AffineTransform transform{};
    bool collision_enabled=false;
    MassMoments ComputeMassMoments() const;
};
struct DeckGeometry
{
    std::vector<DeckChild> children;
    explicit DeckGeometry(DeckGeometrySettings settings);
    MassMoments ComputeMassMoments() const;
};
BodyMassProperties DeckMassProperties(const DeckGeometry& geometry,float mass,float angular_drag);
BodyMassProperties StockDeckMassProperties();
// Four wheels, two trucks, then the deck, matching simulation body indices.
std::array<BodyMassProperties,7> DefaultSkateboardMassProperties();
}
