#include "GroundCorrections.h"
#include "GroundContactResponse.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> out;
std::uint32_t Word()
{
    char bytes[4]; if (!std::cin.read(bytes, 4)) std::exit(2);
    return std::uint32_t(static_cast<unsigned char>(bytes[0]))
        | (std::uint32_t(static_cast<unsigned char>(bytes[1])) << 8)
        | (std::uint32_t(static_cast<unsigned char>(bytes[2])) << 16)
        | (std::uint32_t(static_cast<unsigned char>(bytes[3])) << 24);
}
float Float() { const auto word = Word(); float value; std::memcpy(&value, &word, 4); return value; }
Vec3 Three() { return {Float(), Float(), Float()}; }
Vec4 Four() { return {Float(), Float(), Float(), Float()}; }
Basis3 Basis() { Basis3 b; for (auto& c : b.columns) for (auto& v : c) v = Float(); return b; }
PointGraph<8> Curve() { PointGraph<8> c; for (auto& v : c.x) v = Float(); for (auto& v : c.y) v = Float(); return c; }
BodySnapshot Body()
{
    BodySnapshot b; b.state_flags = Word(); auto& r = b.rates;
    r.orientation = Four(); r.basis = Basis(); r.world_inverse_inertia = Basis();
    r.position = Three(); r.linear_velocity = Three(); r.angular_velocity = Three();
    r.force_acceleration = Three(); r.torque_acceleration = Three(); r.kinetic_energy = Float(); r.cool_down = Word();
    b.inertia = {Three(), Float(), Float(), Float(), Float(), Float(), Float()}; return b;
}
void Out(std::uint32_t word) { out.push_back(word); }
void Out(float value) { std::uint32_t word; std::memcpy(&word, &value, 4); Out(word); }
void Out(Vec3 v) { Out(v.x); Out(v.y); Out(v.z); }
void Out(Vec4 v) { for (auto lane : v) Out(lane); }
void Out(Basis3 b) { for (auto c : b.columns) for (auto v : c) Out(v); }
void Out(BodySnapshot b)
{
    Out(b.state_flags); const auto& r = b.rates;
    Out(r.orientation); Out(r.basis); Out(r.world_inverse_inertia); Out(r.position); Out(r.linear_velocity);
    Out(r.angular_velocity); Out(r.force_acceleration); Out(r.torque_acceleration); Out(r.kinetic_energy); Out(r.cool_down);
    Out(b.inertia.inverse_tensor);
    for (float v : {b.inertia.inverse_mass, b.inertia.spherical, b.inertia.maximum_linear_velocity,
        b.inertia.maximum_angular_velocity, b.inertia.linear_drag, b.inertia.angular_drag}) Out(v);
}
}
int main()
{
    const auto cases = Word();
    for (std::uint32_t c = 0; c < cases; ++c)
    {
        const auto op = Word(); Out(c); Out(op); const auto mark = out.size(); Out(0u);
        switch (op)
        {
        case 0: Out(GroundCentreOfMassHeight(Four())); break;
        case 1: { const auto a = Four(), b = Four(); Out(GroundCollisionForceProjection(a, b)); break; }
        case 2: { const auto a = Four(), b = Four(); Out(GroundEdgeDirection(a, b)); break; }
        case 3: Out(GroundEdgeUp(Four())); break;
        case 4: { const auto a = Four(), b = Four(), d = Four(); Out(GroundHangForce(a, b, d)); break; }
        case 5: { const auto y = Four(), z = Four(); Out(GroundWheelCatchDisplacement(y, z)); break; }
        case 6: { const auto p = Four(); const float x = Float(), z = Float(), dt = Float(); Out(GroundPinningVelocity(p, x, z, dt)); break; }
        case 7: { const auto v = Four(); const float squared = Float(), magnitude = Float(); Out(GroundScaleToMagnitude(v, squared, magnitude)); break; }
        case 8:
        {
            auto body = Body(); const auto deck = Three(); Out(body); const auto count = Word(); Out(count);
            for (std::uint32_t n = 0; n < count; ++n) { const auto force = Three(), point = Three(); GroundApplyWorldForce(body, deck, force, point); Out(body); }
            break;
        }
        case 9:
        {
            const WallRideSettings settings{Curve(), Float(), Float(), Float(), Float(), Float(), Float(), Float()};
            const WallRidePhysical physical{Four(), Four(), Four(), Float(), Float(), Float(), std::int32_t(Word())};
            const GroundContactFrame frame{Four(), Four(), Four(), Word(), Word() != 0, Float(), Float()};
            const auto r = CalculateWallRideResponse(settings, physical, frame, Four());
            Out(std::uint32_t(r.active_2731)); Out(r.tag_16_force.tag); Out(r.tag_16_force.force_world); Out(r.tag_16_force.point_body);
            Out(r.vector_2688); Out(r.scalar_2704); Out(std::uint32_t(r.animated_board_2708)); break;
        }
        default: return 2;
        }
        out[mark] = std::uint32_t(out.size() - mark - 1);
    }
    if (std::cin.peek() != std::char_traits<char>::eof()) return 2;
    for (auto word : out) for (unsigned i = 0; i < 4; ++i) std::cout.put(char(word >> (8 * i)));
}
