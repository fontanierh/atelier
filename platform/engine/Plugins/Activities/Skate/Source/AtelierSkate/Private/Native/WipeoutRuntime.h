// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "WipeoutObservations.h"
namespace atelier::skate
{
void CheckWipeoutAirCollision(WipeoutRequests&,const WipeoutSettings&,const WipeoutMode&,const WipeoutFrame&);
void CheckWipeoutAir(WipeoutRequests&,const WipeoutSettings&,const WipeoutMode&,const WipeoutFrame&,bool use_com);
void CheckWipeoutGround(WipeoutRequests&,const WipeoutSettings&,const WipeoutMode&,const WipeoutFrame&);
void CheckWipeoutGroundAnimation(WipeoutRequests&,const WipeoutSettings&,const WipeoutMode&,const WipeoutFrame&,float scale);
void CheckWipeoutPlant(WipeoutRequests&,const WipeoutSettings&,const WipeoutFrame&);
class WipeoutRuntime
{
public:
    // Ground, Air, plant states and teleport borrow this sole request history.
    WipeoutRequests state;
    WipeoutSettings settings{};
    std::array<WipeoutMode,5> modes{};
    bool Load(const SettingsDatabase&,std::string& error);
    bool CheckAirCollision(const ProcessedPhysicsInput&,const WipeoutFrame&,std::string& error);
    bool CheckGround(const WipeoutObservations&,std::string& error);
    bool CheckGroundAnimation(const WipeoutObservations&,float scale,std::string& error);
    bool CheckAir(const WipeoutObservations&,bool use_com,std::string& error);
    bool CheckPlant(const WipeoutObservations&,std::string& error);
    bool RequestsRunout(const ProcessedPhysicsInput& p) const
    {return state.RequestsRunout(WipeoutRequestsFromProcessed(p));}
    bool RequestsWipeout(const ProcessedPhysicsInput& p) const
    {return state.RequestsWipeout(WipeoutRequestsFromProcessed(p));}
private:
    const WipeoutMode* Mode(const ProcessedPhysicsInput&,std::string& error) const;
};
}
