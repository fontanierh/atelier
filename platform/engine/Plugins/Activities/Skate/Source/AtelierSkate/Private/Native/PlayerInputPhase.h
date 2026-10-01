// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerInputTypes.h"
#include "Settings.h"
#include <string>
namespace atelier::skate
{
// Required original subsystem calls, with no synthetic physical producers.
class InputPhaseServices
{
public:
    virtual ~InputPhaseServices()=default;
    virtual bool UpdatePreInputManager(PlayerInputState&,PhysicalPlayerInput&,std::string&)=0;
    virtual bool ResetProcessedInput(ProcessedPhysicsInput&,std::string&)=0;
    virtual bool ActorQuery56(std::uint32_t&,std::string&)=0;
    virtual bool ActorQuery44(std::uint32_t&,std::string&)=0;
    virtual bool ResetPlayerProbe(PlayerInputState&,PhysicalPlayerInput&,std::string&)=0;
    virtual bool CheckTeleport(PlayerInputState&,PhysicalPlayerInput&,ProcessedPhysicsInput&,std::string&)=0;
    virtual bool ActorInputAvailable(bool&,std::string&)=0;
    virtual bool TransitionAction(float&,std::string&)=0;
    virtual bool CalculateGroundPosition(const PhysicalPlayerInput&,RawVector&,std::string&)=0;
    virtual bool PrepareBoardToolkit(PlayerInputState&,PhysicalPlayerInput&,ProcessedPhysicsInput&,std::string&)=0;
    virtual bool ProcessSkeleton(const AnimationInputPacket&,PhysicalPlayerInput&,ProcessedPhysicsInput&,std::string&)=0;
    virtual bool UpdateGrindManager(PlayerInputState&,PhysicalPlayerInput&,ProcessedPhysicsInput&,std::string&)=0;
};
struct InputPhaseError
{
    enum class Kind {None,Service,InvalidStateVariant} kind=Kind::None;
    std::uint32_t state_variant=0;
    std::string service;
};
struct InputContinuation {std::uint32_t captured_state{},captured_category{};};
bool StartPlayerInputPhase(PlayerInputState&,PhysicalPlayerInput&,const AnimationInputPacket&,
    ProcessedPhysicsInput&,InputPhaseServices&,InputContinuation&,InputPhaseError&);
bool FinishPlayerInputPhase(InputContinuation,PlayerInputState&,PhysicalPlayerInput&,const AnimationInputPacket&,
    ProcessedPhysicsInput&,InputPhaseServices&,InputPhaseError&);
bool ProcessPlayerInputPhase(PlayerInputState&,PhysicalPlayerInput&,const AnimationInputPacket&,
    ProcessedPhysicsInput&,InputPhaseServices&,InputPhaseError&);
GroundHistoryResult PlayerGroundHistory(GroundHistoryRequest);
RawVector PlayerPreparedJumpVelocity(PrepareJumpRequest);
bool LoadPlayerInputState(const SettingsDatabase&,PlayerInputState&,std::string&);
void ResetProcessedPhysicsInput(ProcessedPhysicsInput&);
void ResetPhysicalPlayerOutputs(PhysicalPlayerInput&);
}
