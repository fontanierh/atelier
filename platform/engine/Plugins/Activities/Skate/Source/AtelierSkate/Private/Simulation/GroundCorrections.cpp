#include "GroundCorrections.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) { float value; std::memcpy(&value, &word, 4); return value; }
Vec4 Scale4(Vec4 value, float factor) { for (auto& lane : value) lane *= factor; return value; }
Vec4 Subtract4(Vec4 a, Vec4 b) { for (std::size_t i = 0; i < 4; ++i) a[i] -= b[i]; return a; }
float FlipSign(float value)
{
    std::uint32_t word; std::memcpy(&word, &value, 4); word ^= 0x80000000u;
    std::memcpy(&value, &word, 4); return value;
}
}
float GroundCentreOfMassHeight(Vec4 value) { return Length3(value); }
float GroundCollisionForceProjection(Vec4 force, Vec4 velocity)
{
    const float squared = Dot3(force, force);
    const float inverse = InverseLengthSquared(squared, 2);
    const float length = squared == 0.0f ? 0.0f : squared * inverse;
    const auto direction = length > Float(0x358637bd) ? Scale4(force, inverse) : Vec4{};
    return Dot3(direction, velocity);
}
Vec4 GroundEdgeDirection(Vec4 start, Vec4 end)
{
    const auto delta = Subtract4(end, start);
    return Scale4(delta, RefinedReciprocal(Length3(delta), 2));
}
Vec4 GroundEdgeUp(Vec4 direction)
{
    const auto first = Cross3(Vec4{0, 1, 0, 0}, direction);
    const auto perpendicular = Cross3(first, direction);
    const float magnitude = Length3(perpendicular);
    if (magnitude <= 0.0f) return {1, 0, 0, 0};
    const float signed_length = perpendicular[1] < 0.0f ? -magnitude : magnitude;
    return Scale4(perpendicular, RefinedReciprocal(signed_length, 2));
}
Vec4 GroundHangForce(Vec4 start, Vec4 end, Vec4 deck)
{
    const auto direction = GroundEdgeDirection(start, end);
    auto side = Cross3(GroundEdgeUp(direction), direction);
    if (Dot3(Subtract4(deck, start), side) < 0.0f) side = Scale4(side, -1.0f);
    constexpr Vec4 lift{0, 160, 0, 0};
    for (std::size_t i = 0; i < 4; ++i) side[i] = std::fma(side[i], 50.0f, lift[i]);
    return side;
}
Vec4 GroundWheelCatchDisplacement(Vec4 deck_y, Vec4 deck_z)
{
    if (!(deck_z[1] > 0.0f)) for (auto& lane : deck_z) lane = FlipSign(lane);
    return Scale4(Cross3(deck_z, deck_y), Float(0x3be56042));
}
Vec4 GroundPinningVelocity(Vec4 position, float x, float z, float dt)
{
    return Scale4(Subtract4(Vec4{x, position[1], z, 0}, position), RefinedReciprocal(dt, 2));
}
Vec4 GroundScaleToMagnitude(Vec4 vector, float squared, float magnitude)
{
    const float inverse = InverseLengthSquared(squared, 2);
    const float length = squared == 0.0f ? 0.0f : squared * inverse;
    // The scalar division is distinct from inverse-length scaling.
    return Scale4(vector, magnitude / length);
}
void GroundApplyWorldForce(BodySnapshot& body, Vec3 deck_part_position, Vec3 force, Vec3 point)
{
    const auto arm = Subtract(point, deck_part_position);
    const auto torque = Cross3(arm, force);
    const float inverse = body.inertia.inverse_mass;
    body.rates.force_acceleration.x += force.x * inverse;
    body.rates.force_acceleration.y += force.y * inverse;
    body.rates.force_acceleration.z += force.z * inverse;
    const auto columns = body.rates.world_inverse_inertia.columns;
    const auto angular = [&](std::size_t i) {
        return std::fma(columns[2][i], torque.z,
            std::fma(columns[1][i], torque.y, columns[0][i] * torque.x));
    };
    body.rates.torque_acceleration.x += angular(0);
    body.rates.torque_acceleration.y += angular(1);
    body.rates.torque_acceleration.z += angular(2);
    body.rates.cool_down = 0;
}
}
