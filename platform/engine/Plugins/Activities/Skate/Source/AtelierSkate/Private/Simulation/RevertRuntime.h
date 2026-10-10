#pragma once
#include "GroundPhaseRuntime.h"
namespace atelier::skate
{
struct RevertOwners
{
    GroundPhaseOwners ground;
    SkeletonInputRuntime& skeleton_input;
    SkeletonAir& skeleton_air;
    const std::vector<Mat4>& hierarchy;
};
// RevertGround102 retains its own captured heading/timer, while borrowing the
// same physical bodies, ground manual/pump and skeleton owners as Ground.
class RevertRuntime
{
public:
    PointGraph<8> speed;
    PointGraph<4> tolerance;
    float gain=0,delay=0,duration=0;
    float direction=0,travel_sign=1;
    Vec4 velocity{};
    float elapsed=0;
    bool captured=false,active=false;
    bool Load(const SettingsDatabase&,std::string& error);
    Vec4 Correction(Vec4 forward,Vec4 normal,Vec4 angular);
    void Enter(GroundPhaseOwners);
    bool Update(RevertOwners,const GroundSettings&,std::string& error);
};
}
