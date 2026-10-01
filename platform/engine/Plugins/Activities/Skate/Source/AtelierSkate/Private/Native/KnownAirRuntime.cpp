// SPDX-License-Identifier: Apache-2.0
#include "KnownAirPrivate.h"
namespace atelier::skate
{
namespace
{
const KnownAirModeSettings* KnownMode(const KnownAirConfiguration& c,const ProcessedPhysicsInput& p,std::string& error)
{
    if (p.state_variant_index_2528>=c.modes.size()) {error="Undefined KnownAir physics mode "+std::to_string(p.state_variant_index_2528);return nullptr;}
    return &c.modes[p.state_variant_index_2528];
}
}
bool KnownAirRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    KnownAirConfiguration next{};if (!LoadKnownAirConfiguration(data,next,error)) return false;
    configuration=std::move(next);state={};state.landing_normal_64={0,1,0,0};error.clear();return true;
}
bool KnownAirRuntime::Enter(AirPhaseOwners owners,std::string& error)
{
    KnownAirFrame frame;if (!known_air::Frame(owners,201,frame,error)) return false;auto next=state;
    const auto mode=KnownMode(configuration,owners.processed,error);if (!mode) return false;
    auto live=known_air::Live::Create(owners,configuration,error);if (!live) return false;
    known_air::Enter(next,frame,configuration.settings,*mode,*live);if (!live->Finish(error)) return false;state=next;return true;
}
bool KnownAirRuntime::Update(AirPhaseOwners owners,std::string& error)
{
    KnownAirFrame frame;if (!known_air::Frame(owners,201,frame,error)) return false;auto next=state;
    const auto mode=KnownMode(configuration,owners.processed,error);if (!mode) return false;const auto reckoning=known_air::ReckoningFields(owners);
    auto live=known_air::Live::Create(owners,configuration,error);if (!live) return false;
    known_air::Update(next,frame,configuration.settings,*mode,reckoning,*live);if (!live->Finish(error)) return false;state=next;return true;
}
bool KnownAirRuntime::Exit(AirPhaseOwners owners,std::uint32_t next_state,std::string& error)
{
    KnownAirFrame frame;if (!known_air::Frame(owners,next_state,frame,error)) return false;auto next=state;auto reckoning=known_air::ReckoningFields(owners);
    auto live=known_air::Live::Create(owners,configuration,error);if (!live) return false;
    known_air::Exit(next,frame,configuration.settings,reckoning,*live);if (!live->Finish(error)) return false;
    owners.processed.scalar_2612=frame.forward_speed_2612;owners.air_reckoning.state.spin_angle=reckoning.body_spin_angle_1568;
    owners.air_reckoning.state.spin_speed=reckoning.body_spin_speed_1572;state=next;return true;
}
bool KnownAirRuntime::PostPhysics(AirPhaseOwners owners,std::string& error)
{
    KnownAirFrame frame;if (!known_air::Frame(owners,201,frame,error)) return false;auto next=state;
    const auto mode=KnownMode(configuration,owners.processed,error);if (!mode) return false;KnownAirWipeoutRequest request{};
    auto live=known_air::Live::Create(owners,configuration,error);if (!live) return false;
    known_air::Post(next,frame,*mode,configuration.wipeout,request,*live);if (!live->Finish(error)) return false;
    if (request.counter_200!=0) owners.wipeout.state.Request(15,request.scalar_116);state=next;return true;
}
bool KnownAirRuntime::Fill(AirPhaseOwners owners,AirOutputFields& physical,KnownAirOutput& output,std::string& error)
{
    KnownAirFrame frame;if (!known_air::Frame(owners,201,frame,error)) return false;auto out=known_air::Storage(physical);
    auto live=known_air::Live::Create(owners,configuration,error);if (!live) return false;
    known_air::Fill(state,frame,out,*live);if (!live->Finish(error)) return false;known_air::Publish(out,physical);output=out;return true;
}
}
