#pragma once
#include "AirTrajectorySelectorTypes.h"
namespace atelier::skate
{
// Output is assigned only after every source-ordered lookup succeeds.
bool LoadAirTrajectorySelectorSettings(const SettingsDatabase&,AirTrajectorySelectorSettings&,std::string& error);
}
