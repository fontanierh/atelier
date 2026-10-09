#pragma once
#include "BoardContactFeedback.h"
#include "ContactGeneration.h"
#include "ForceQueue.h"
#include <optional>

namespace atelier::skate
{
struct AttachedStep
{
    // Unique live owners, separate from board/hook; mirrors Rust's exclusive borrows.
    std::vector<BodySnapshot*> bodies;
    std::vector<ContactConstraint>& contacts;
    std::vector<JointConstraint>& joints;
    std::vector<DriveRows>& drives;
    std::size_t WorldReaction() const {return AttachedReactionBase+bodies.size();}
};
struct BoardCollision
{
    CollisionBody body_a,body_b;
    ContactInput contact;
};
struct BoardStepSettings
{
    SimulationStep simulation;
    std::uint32_t iterations;
    std::array<AffineTransform,2> base_truck_transforms;
    DriveDynamics truck_dynamics;
    float force_point_y_offset;
};
// Optional observations retain the simulation typed data instead of a formatted string.
// Capturing never changes the solver's inputs or scheduling.
struct BoardSolverDiagnostics
{
    std::uint64_t tick;
    BodySnapshot deck;
    BoardHook hook;
    ReactionCorrections reaction;
    struct Joint {std::size_t index;JointConstraint row;};
    struct Drive {std::size_t index;DriveRows row;};
    std::vector<Joint> joints;
    std::vector<Drive> drives;
};
class BoardStep
{
public:
    bool diagnostic_capture=false;
    std::optional<BoardSolverDiagnostics> diagnostic_snapshot;
    const std::vector<BoardContactReport>& ContactReports() const {return reports_;}
    const std::vector<ContactConstraint>& SolvedContacts() const {return contacts_;}
    void Advance(std::array<BodySnapshot,BoardBodyCount>& bodies,BoardHook& hook,const BoardForceQueue& forces,
        const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,BoardStepSettings settings);
    void AdvanceAttached(std::array<BodySnapshot,BoardBodyCount>& bodies,BoardHook& hook,const BoardForceQueue& forces,
        const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,BoardStepSettings settings,
        AttachedStep attached);
private:
    std::vector<ContactConstraint> contacts_;
    std::vector<BoardContactReport> reports_;
    std::vector<PackedReaction> reactions_;
    std::uint64_t diagnostic_tick_=0;
};
}
