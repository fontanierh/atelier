#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
class PhysicsAirMath
{
public:
    virtual ~PhysicsAirMath() = default;
    virtual float Minimum(float left,float right)=0;
    virtual float LengthSquared(Vec4 value)=0;
    virtual float Length(Vec4 value)=0;
    virtual Vec4 ClampLength(Vec4 value,float maximum)=0;
};
class AirMath final : public PhysicsAirMath
{
public:
    float Minimum(float left,float right) override;
    float LengthSquared(Vec4 value) override;
    float Length(Vec4 value) override;
    Vec4 ClampLength(Vec4 value,float maximum) override;
};
float AirAngleBetweenVectors(Vec4 left,Vec4 right);
Vec4 ClampAirJumpVelocity(Vec4 reference,Vec4 current);
}
