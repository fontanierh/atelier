#pragma once
#include "SimulationMath.h"
#include <optional>
namespace atelier::skate
{
using PoseMatrix=std::array<std::uint32_t,16>;
struct PartPose
{
    PoseMatrix transform{};
    std::optional<PoseMatrix> local_mass_frame;
    std::optional<std::array<std::uint32_t,44>> body;
    std::optional<std::array<std::uint32_t,10>> inertia;
};
PoseMatrix OrthonormalizeRotation(PoseMatrix input);
PoseMatrix OrthonormalizePartBasis(PoseMatrix input);
PoseMatrix PartTransform(const PartPose& part);
void SetPartTransform(PartPose& part,PoseMatrix requested);
void SetBoardTransform(std::array<PartPose,7>& parts,PartPose& hook,PoseMatrix requested);
}
