#pragma once
#include "BoardTypes.h"
#include "HookDrive.h"
#include "RigidBody.h"

namespace atelier::skate
{
struct BodySnapshot
{
    std::uint32_t state_flags=0;
    BodyRates rates{};
    InertiaDynamics inertia{};
};
// The animated hook target is registered after the seven physical board parts.
struct BoardHook { BodySnapshot body{};HookDriveState drive{}; };
constexpr std::size_t HookReaction=BoardBodyCount;
struct BoardConstraints
{
    std::vector<JointConstraint> joints;
    std::vector<DriveRows> drives;
    static BoardConstraints Build(const std::array<BodySnapshot,BoardBodyCount>& bodies,
        const BoardHook& hook,std::array<DriveFrames,3> frames,
        DriveDynamics truck_dynamics,float time_step);
};
// Hook quaternion normalization writes the live drive state on every call.
std::array<DriveFrames,3> PrepareDriveFrames(std::array<AffineTransform,2> base,
    std::array<float,2> targets,BoardHook& hook);
}
