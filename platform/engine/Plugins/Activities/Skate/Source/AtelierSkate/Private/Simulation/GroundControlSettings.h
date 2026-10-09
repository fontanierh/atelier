#pragma once
#include "GroundPropulsion.h"
#include "GroundContactResponse.h"
#include "SpeedModel.h"
#include "Settings.h"
namespace atelier::skate
{
// Immutable stock bindings, before the Ground owner applies trainer tuning.
// Failure leaves the caller's settings object unchanged, as with Rust Result.
bool LoadGroundManualSettings(const SettingsDatabase&,ManualSettings&,std::string& error);
bool LoadGroundManualMode(const SettingsDatabase&,std::string_view mode,ManualMode&,std::string& error);
bool LoadGroundPropulsionSettings(const SettingsDatabase&,std::string_view mode,GroundPropulsionSettings&,std::string& error);
bool LoadGroundLinearDragSettings(const SettingsDatabase&,LinearDragSettings&,std::string& error);
bool LoadGroundSpeedModelSettings(const SettingsDatabase&,std::string_view mode,std::string_view surface,SpeedModelSettings&,std::string& error);
bool LoadGroundWallRideSettings(const SettingsDatabase&,WallRideSettings&,std::string& error);
bool GroundSurfaceKey(std::uint32_t mode,std::string_view& output,std::string& error);
}
