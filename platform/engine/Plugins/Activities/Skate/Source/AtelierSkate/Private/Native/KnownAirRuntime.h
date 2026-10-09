#pragma once
#include "AirPhaseRuntime.h"
#include "KnownAirSettings.h"
namespace atelier::skate
{
// Every call borrows the same AirPhaseOwners. The core state copy publishes
// only after the live adapter has completed without an error; physical owner
// mutations already performed remain visible when it returns an error.
class KnownAirRuntime
{
public:
    KnownAirState state;
    KnownAirConfiguration configuration{};
    KnownAirRuntime(){state.landing_normal_64={0,1,0,0};}
    bool Load(const SettingsDatabase&,std::string& error);
    void SetSpinSpeed(float speed){configuration.settings.max_spin_speed_428=speed;}
    bool Enter(AirPhaseOwners,std::string& error);
    bool Update(AirPhaseOwners,std::string& error);
    bool Exit(AirPhaseOwners,std::uint32_t next,std::string& error);
    bool PostPhysics(AirPhaseOwners,std::string& error);
    bool Fill(AirPhaseOwners,AirOutputFields&,KnownAirOutput&,std::string& error);
};
}
