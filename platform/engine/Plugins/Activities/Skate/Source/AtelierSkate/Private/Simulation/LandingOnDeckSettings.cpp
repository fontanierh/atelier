#include "LandingOnDeckSettings.h"
#include "StockSettingsReader.h"
namespace atelier::skate
{
bool LandingOnDeckConfiguration::Load(const SettingsDatabase& data,std::string& error)
{
    LandingOnDeckConfiguration next;const StockSettingsReader reader(data);
    if(!reader.Float("physics_landingondeck","default","MinAngleToAutoTurn",next.state.minimum_auto_angle,error)||
       !reader.Float("physics_landingondeck","default","BodySpinSpeedAuto",next.state.automatic_speed,error)||
       !reader.Float("physics_landingondeck","default","BodySpinSpeed",next.state.input_speed,error)||
       !reader.Float("physics_landingondeck","default","BodySpinDeltaInput",next.state.input_delta,error)||
       !reader.Float("physics_landingondeck","default","BodySpinDeltaAuto",next.state.automatic_delta,error)||
       !reader.Float("physics_wipeout","default","MaxSpeedLandingOnBoard",next.state.maximum_landing_speed,error)||
       !reader.Float("physics_skeleton","default","SkateRootYOffset",next.root.root_y_offset,error)||
       !reader.Float("physics_skeleton","default","SkateRootCapsuleRadius",next.root.capsule_radius,error)||
       !reader.Float("physics_skeleton","default","SkateRootCapsuleLength",next.root.capsule_length,error))return false;
    *this=next;error.clear();return true;
}
}
