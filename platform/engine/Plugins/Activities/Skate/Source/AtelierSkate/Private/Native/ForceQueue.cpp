#include "ForceQueue.h"

namespace atelier::skate
{
bool BoardForceQueue::Append(QueuedPointForce entry)
{
    if(count_==ForceCapacity)return false;
    entries_[count_++]=entry;return true;
}
ForceAccumulator BoardForceQueue::ApplyToDeck(ForceAccumulator accumulator,Basis3 deck_basis,float inverse_mass,
    Basis3 world_inverse_inertia,float force_point_y_offset) const
{
    for(std::size_t i=0;i<count_;++i)
    {
        const auto& entry=entries_[i];
        const Vec3 point{entry.point_body.x+0.0f,entry.point_body.y+force_point_y_offset,entry.point_body.z+0.0f};
        accumulator=AccumulatePointForce(accumulator,entry.force_world,point,deck_basis,inverse_mass,world_inverse_inertia);
    }
    return accumulator;
}
float TotalBodyMass(const std::vector<float>& inverse_masses)
{
    float even=0.0f,odd=0.0f;std::size_t i=0;
    for(;i+1<inverse_masses.size();i+=2)
    {
        even=1.0f/inverse_masses[i]+even;
        odd=1.0f/inverse_masses[i+1]+odd;
    }
    const float paired=odd+even;
    return paired+(i<inverse_masses.size()?1.0f/inverse_masses[i]:0.0f);
}
}
