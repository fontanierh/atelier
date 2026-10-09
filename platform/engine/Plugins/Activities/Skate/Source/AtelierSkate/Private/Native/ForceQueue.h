#pragma once
#include "RigidBody.h"
#include <vector>

namespace atelier::skate
{
constexpr std::size_t ForceCapacity=21;
struct QueuedPointForce
{
    std::uint32_t tag=0;
    Vec3 force_world{},point_body{};
};
class BoardForceQueue
{
public:
    bool Append(QueuedPointForce entry);
    const QueuedPointForce* Entries() const {return entries_.data();}
    std::size_t Count() const {return count_;}
    ForceAccumulator ApplyToDeck(ForceAccumulator accumulator,Basis3 deck_basis,float inverse_mass,
        Basis3 world_inverse_inertia,float force_point_y_offset) const;
    // Consumption preserves records; clearing belongs to the gameplay phase.
    void Clear(){count_=0;}
private:
    std::array<QueuedPointForce,ForceCapacity> entries_{};
    std::size_t count_=0;
};
float TotalBodyMass(const std::vector<float>& inverse_masses);
}
