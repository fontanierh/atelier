#pragma once
#include "PhysicalPhase.h"
namespace atelier::skate
{
// Core player/pre_state.rs, state_phase.rs and post_state.rs wrapper order.
// Callbacks are mandatory and infallible because that is the original contract.
struct PreStatePacket
{
    std::array<std::uint32_t,18> words;
    std::array<std::uint32_t,4> Vector48() const;
};
struct PreStatePlayerFields {std::uint32_t frame_counter_1312;bool component_1840_present;};
struct PreStateSkeletonFields
{
    std::array<std::uint32_t,4> predicted_position_16112;
    bool predicted_position_set_16416,nested_flag_3184;
};
class PreStateServices
{
public:
    virtual ~PreStateServices()=default;
    virtual void FillPacketVtable24(PreStatePacket&)=0;
    virtual void UpdateComponent1840()=0;
    virtual void UpdateBeforeStateVtable4()=0;
};
struct StatePhaseFields
{
    float elapsed_1344,timestep_2604;
    std::uint32_t controller_state_448;
    bool controller_system_on_452;
};
class StatePhaseServices
{
public:
    virtual ~StatePhaseServices()=default;
    virtual void UpdateCurrentStateVtable8()=0;
    virtual void UpdateController()=0;
    virtual void UpdateControllerMode1()=0;
    virtual void UpdateControllerMode2()=0;
    virtual void UpdateControllerMode3()=0;
    virtual void UpdateControllerMode4()=0;
    virtual void TouchSkateboardVtable116()=0;
    virtual void ApplySkateboardForceQueue()=0;
    virtual void UpdateSkateboardFixedStepCache()=0;
};
class PostStateServices
{
public:
    virtual ~PostStateServices()=default;
    virtual void UpdateCurrentStateVtable12()=0;
};
void RunPlayerPreState(PreStatePlayerFields&,PreStateSkeletonFields&,PreStateServices&);
void RunPlayerStatePhase(StatePhaseFields&,StatePhaseServices&);
void RunPlayerPostState(PostStateServices&);
}
