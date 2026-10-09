#pragma once
#include "NativeMath.h"
#include <optional>
#include <vector>
namespace atelier::skate
{
void NormalizeDriveFrames(std::array<std::uint32_t,16>& frames);
// Null registrations skip; duplicate registrations normalize repeatedly in order.
void NormalizeActiveDriveFrames(std::vector<std::array<std::uint32_t,16>>& frames,
                                const std::vector<std::optional<std::size_t>>& active_frame_indices);
}
