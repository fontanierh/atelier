// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PhysicalPhase.h"
#include "BoardPossession.h"
namespace atelier::skate
{
// Complete core player/lifecycle.rs (TU3 SetPhysicsState 0x82DB8540).
// StateBinding selects an already owned state; it never creates another owner.
struct StateBinding
{
    PhysicalStateId state;
    std::uint32_t owner_offset;
    static StateBinding New(PhysicalStateId id) {return {id,PhysicalStateOwnerOffset(id)};}
};
struct PlayerStateChangeFields {std::uint32_t word_1312,previous_category_latch_1336;float scalar_1344;};
struct ProcessedStateChangeFields
{
    std::uint32_t flags_2480,requested_state_2500,previous_state_2504,current_state_2508,current_category_2512,previous_category_2516,previous_category_latch_2520,word_2564;
    float scalar_2664;
};
struct StateChangeData {PlayerStateChangeFields player;ProcessedStateChangeFields processed;SkateboardControllerFields skateboard_controller;};
class SkateboardControllerActions
{
public:
    virtual ~SkateboardControllerActions()=default;
    virtual void HoldSkateboard()=0;
    virtual void LetGoOfSkateboard()=0;
};
struct StateCall {StateBinding state,active;};
class PhysicalStateCalls
{
public:
    virtual ~PhysicalStateCalls()=default;
    virtual PhysicalStateId GetType(StateBinding)=0;
    virtual void Exit(StateCall)=0;
    virtual void Enter(StateCall)=0;
};
class PhysicalPlayerStateLifecycle
{
public:
    explicit PhysicalPlayerStateLifecycle(PhysicalStateId initial):active_(StateBinding::New(initial)){}
    StateBinding Active() const {return active_;}
    // Unknown numeric requests fail before callbacks or writes, as pinned Rust.
    bool SetPhysicsState(std::uint32_t requested,StateChangeData&,PhysicalStateCalls&,
        SkateboardControllerActions&,StateBinding& result,std::uint32_t& unknown_state);
private:
    StateBinding active_;
};
}
