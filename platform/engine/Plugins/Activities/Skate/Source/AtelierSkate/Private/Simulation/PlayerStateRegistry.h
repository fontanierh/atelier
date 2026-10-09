#pragma once
#include "PhysicalPhase.h"
namespace atelier::skate
{
struct PlayerStateCapability
{
    PhysicalStateId id;
    bool supported,has_enter,has_exit;
};
// The original host support table is distinct from the complete core enum.
// Lifecycle callers must check this before publishing a new state.
class PlayerStateRegistry
{
public:
    PlayerStateCapability Capability(PhysicalStateId) const;
    bool CanTransition(PhysicalStateId current,PhysicalStateId requested) const;
};
}
