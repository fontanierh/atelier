#pragma once
#include "Braking.h"
#include "RigidBody.h"
#include <optional>
namespace atelier::skate
{
struct GroundDragInput
{
    std::uint32_t flags_2468;
    float absolute_body_speed_2616,balance_2720,scalar_2724,ground_normal_y;
    float Calculate(LinearDragSettings) const;
};
enum class DragBindingError { PartOutsideAssembly,InertiaOutsideStorage };
struct BodyInertias
{
    const std::size_t* part_inertia_indices;
    std::size_t part_count;
    InertiaDynamics* inertias;
    std::size_t inertia_count;
    // Empty selection means all parts. Validation precedes every inertia write.
    bool SetLinearDrag(float,std::optional<std::size_t> part,DragBindingError&);
    bool ApplyGroundDrag(float drag,DragBindingError& error) {return SetLinearDrag(drag,std::nullopt,error);}
};
}
