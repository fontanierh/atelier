// SPDX-License-Identifier: Apache-2.0
#include "GroundDrag.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
float GroundDragInput::Calculate(LinearDragSettings settings) const
{
    return CalculateLinearDrag({flags_2468,absolute_body_speed_2616,balance_2720,scalar_2724,ground_normal_y},settings);
}
bool BodyInertias::SetLinearDrag(float drag,std::optional<std::size_t> part,DragBindingError& error)
{
    if(part&&*part>=part_count){error=DragBindingError::PartOutsideAssembly;return false;}
    const auto* selected=part?part_inertia_indices+*part:part_inertia_indices;
    const auto count=part?std::size_t(1):part_count;
    for(std::size_t i=0;i<count;++i)
        if(selected[i]>=inertia_count){error=DragBindingError::InertiaOutsideStorage;return false;}
    const std::uint32_t word=0x426fffff;float frequency;std::memcpy(&frequency,&word,4);
    std::size_t i=0;
    for(;i+4<=count;i+=4)
    {
        const auto first=selected[i],second=selected[i+1],third=selected[i+2],fourth=selected[i+3];
        const float coefficient=drag*frequency;
        inertias[first].linear_drag=coefficient;inertias[second].linear_drag=coefficient;
        inertias[third].linear_drag=coefficient;inertias[fourth].linear_drag=coefficient;
    }
    for(;i<count;++i)inertias[selected[i]].linear_drag=drag*frequency;
    return true;
}
}
