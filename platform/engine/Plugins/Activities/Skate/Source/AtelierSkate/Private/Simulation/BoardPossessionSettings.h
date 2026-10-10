#pragma once
#include "BoardPossessionRuntime.h"
namespace atelier::skate
{
std::optional<BoardPossessionSettings> LoadBoardPossessionSettings(const SettingsDatabase&,std::string& error);
std::optional<float> BoardPossessionStandardAngularDrag(const SettingsDatabase&,std::string& error);
std::optional<BoardPossessionLiveState> LoadBoardPossessionLiveState(const SettingsDatabase&,const BoardPhysicsSettings&,std::string& error);
}
