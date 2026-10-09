#include "Braking.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
QueuedPointForce CalculateBraking(BrakeInput input, BrakeSettings settings)
{
    float amount = input.flags_2468 & 0x40000000u ? input.input_2728 * settings.input_force : 0.0f;
    if (input.flags_2468 & 0x20000000u) amount = settings.override_force;
    const float scaled = input.surface_factor * amount;
    amount = (input.signed_speed < 0.0f ? 1.0f : -1.0f) * scaled;
    if (input.absolute_body_speed < settings.minimum_speed) amount = 0.0f;
    return {2, Scale(input.direction, amount), {}};
}
float CalculateLinearDrag(LinearDragInput input, LinearDragSettings settings)
{
    const bool brake = input.absolute_body_speed < settings.brake_speed * 2.0f
        && (input.flags_2468 & 0x60000000u) && !(input.scalar_2724 > 0.0f) && input.balance_2720 == 0.0f;
    const bool balance = input.balance_2720 != 0.0f && input.absolute_body_speed < settings.balance_speed
        && input.comparison_scalar > settings.comparison_threshold;
    return brake ? 1.0f : balance ? settings.balance_drag : 0.0f;
}
}
