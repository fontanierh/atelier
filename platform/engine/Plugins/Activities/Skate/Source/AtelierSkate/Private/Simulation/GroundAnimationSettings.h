#pragma once
#include "GroundJump.h"
#include "Settings.h"
namespace atelier::skate {
struct GroundAnimationSettings {
  GroundJumpSettings jump;
  std::array<GroundJumpMode, 5> modes;
  bool Load(const SettingsDatabase &, std::string &error);
};
} // namespace atelier::skate
