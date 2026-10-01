// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardPose.h"
#include "BoardStep.h"

namespace atelier::skate
{
enum class BoardMotion { Active,Frozen,Static };
BodySnapshot InitializeBody(const PartPose& part,InertiaDynamics inertia,SimulationStep simulation,BoardMotion mode);
class BoardRuntime
{
public:
    BoardRuntime(std::array<BodyMassProperties,BoardBodyCount> masses,
        std::array<AffineTransform,BoardBodyCount> authored,AffineTransform spawn,SimulationStep simulation,BoardMotion mode);
    std::optional<BoardSolverDiagnostics> TakeSolverDiagnostics(bool enabled);
    std::uint32_t CollisionGroup() const {return collision_group_;}
    void SetCollisionGroup(std::uint32_t group){collision_group_=group;}
    const std::array<BodySnapshot,BoardBodyCount>& Bodies() const {return bodies_;}
    std::array<BodySnapshot,BoardBodyCount>& BodiesMut(){return bodies_;}
    const BoardHook& Hook() const {return hook_;}
    BoardHook& HookMut(){return hook_;}
    const BoardForceQueue& Forces() const {return forces_;}
    BoardForceQueue& ForcesMut(){return forces_;}
    void ClearForces(){forces_.Clear();}
    const std::vector<BoardContactReport>& ContactReports() const {return step_.ContactReports();}
    const std::vector<ContactConstraint>& SolvedContacts() const {return step_.SolvedContacts();}
    void ResetPhysical(std::array<AffineTransform,BoardBodyCount> authored,AffineTransform target,
        std::uint32_t processed_flags,Vec3 gravity);
    void SetTransform(AffineTransform target);
    AffineTransform BodyTransform(BoardBodyId id) const;
    std::array<AffineTransform,BoardBodyCount> PartTransforms() const;
    AffineTransform HookTransform() const;
    void SetHookTransform(AffineTransform requested);
    void Advance(const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,BoardStepSettings settings);
    void AdvanceAttached(const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,
        BoardStepSettings settings,AttachedStep attached);
private:
    std::array<BodySnapshot,BoardBodyCount> bodies_;
    std::array<LocalMassFrame,BoardBodyCount> mass_frames_;
    BoardHook hook_;
    BoardStep step_;
    BoardForceQueue forces_;
    std::uint32_t collision_group_=4;
};
}
