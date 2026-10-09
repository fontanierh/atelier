#pragma once
#include "CameraManager.h"
#include "Settings.h"
namespace atelier::skate::camera {
bool LoadManagerSettings(const SettingsDatabase &data, ManagerSettings &result,
                         std::string &error);
bool LoadCompassSettings(const SettingsDatabase &data, CompassSettings &result,
                         std::string &error);
bool LoadSlowMotionSettings(const SettingsDatabase &data,
                            SlowMotionSettings &result, std::string &error);
struct CameraSettings {
  ManagerSettings manager;
  CompassSettings compass;
  SlowMotionSettings slow_motion;
  bool Load(const SettingsDatabase &data, std::string &error);
};
// ATCAM001 contains decoded named shots and centered sample vectors. Original
// collections/RefSpecs/.shk are consumed only by the conversion tool and
// oracle.
struct CameraData {
  StockShots shots;
  std::array<ShakeSamples, 2> shakes;
  std::string source_identity;
  bool Load(const std::vector<std::uint8_t> &bytes, std::string &error);
};
} // namespace atelier::skate::camera
