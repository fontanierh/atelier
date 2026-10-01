// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BipedGroundRuntime.h"
#include "BipedAirState.h"
namespace atelier::skate
{
class BipedAirRuntime
{
public:
    BipedAirState state;BipedAirChecks checks;
    bool Load(const SettingsDatabase&,std::string& error);
    // Called at the original early fixed-step phase, with retained input,
    // before current ProcessInput and state selection.
    bool ConsumeSelector(BipedRuntimeOwners,std::string& error);
    bool Enter(BipedRuntimeOwners,BipedGroundRuntime&,std::string& error);
    bool Update(BipedRuntimeOwners,BipedGroundRuntime&,std::string& error);
    bool PostPhysics(BipedRuntimeOwners,const WipeoutFrame& actual_frame,std::string& error);
    void Fill(BipedRuntimeOwners) const;void Exit(OffboardAirSelector&);
private:
    BipedAirEnterInput EnterInput(BipedRuntimeOwners) const;
    BipedAirHeightInput HeightInput(BipedRuntimeOwners) const;
    bool LaunchPacket(BipedRuntimeOwners,const BipedGroundRuntime&,OffboardAirLaunchPacket&,std::string& error) const;
};
}
