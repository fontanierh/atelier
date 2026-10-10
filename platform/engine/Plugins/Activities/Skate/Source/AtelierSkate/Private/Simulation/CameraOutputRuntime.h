#pragma once
#include "CameraPublication.h"
namespace atelier::skate::camera {
// This producer consumes the same completed exchange as the frame coordinator.
// The ordered simulation-rate requests remain owned by the one CameraRuntime;
// the global coordinator consumes them at its original next-tick boundary.
struct CameraOutputResult {
  CameraFrame frame;
  const std::vector<SimulationRateRequest> *simulation_rate_requests;
};
CameraPublicationInputs
PublishCameraOutput(const CameraPublicationFrame &,
                    const PhysicalOutputSnapshot &, CameraPreferences,
                    std::uint8_t skater_animation_stance, std::uint32_t context,
                    std::uint64_t tick);
bool AdvanceCameraOutput(const CameraPublicationFrame &,
                         const SimulationExchange &, CameraRuntime &,
                         CameraOutputResult &output, std::string &error);
} // namespace atelier::skate::camera
