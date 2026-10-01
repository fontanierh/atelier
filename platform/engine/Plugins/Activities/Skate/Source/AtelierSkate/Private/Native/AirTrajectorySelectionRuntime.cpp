// SPDX-License-Identifier: Apache-2.0
#include "AirTrajectoryRuntime.h"
#include "AirTrajectorySelectorSettings.h"
#include <algorithm>
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
class SelectionServices final : public AirTrajectorySelectionServices {
public:
  SelectionServices(const AirTrajectoryGrindRuntime &settings,
                    const WorldGeometry &world,
                    const PlayerGrindStaticProvider &provider,
                    std::vector<std::size_t> &nearby, float lock_distance,
                    AirTrajectoryGrindContext context)
      : settings_(settings), world_(world), provider_(provider), nearby_(nearby),
        lock_distance_(lock_distance), context_(context) {}
  bool EvaluateGrind(AirTrajectoryPrediction &prediction, bool acquire,
                     AirTrajectoryGrindEvaluation &result,
                     std::string &error) override {
    return settings_.Evaluate(prediction, acquire, world_, provider_, nearby_,
                              lock_distance_, context_, result, error);
  }
  bool Line(Vec4 start, Vec4 end, float radius,
            std::optional<AirTrajectorySurfaceHit> &result,
            std::string &error) override {
    return AirTrajectoryWorldLine(world_, start, end, radius, result, error);
  }
private:
  const AirTrajectoryGrindRuntime &settings_;
  const WorldGeometry &world_;
  const PlayerGrindStaticProvider &provider_;
  std::vector<std::size_t> &nearby_;
  float lock_distance_;
  AirTrajectoryGrindContext context_;
};
} // namespace
std::pair<Vec4,Vec4> AirTrajectoryVertDeparture(Vec4 n, Vec4 v,
                                              float direction, float assist) {
  const float speed = std::sqrt((v[0] * v[0] + v[1] * v[1]) + v[2] * v[2]);
  const float horizontal = std::sqrt(n[0] * n[0] + n[2] * n[2]);
  if (direction >= 0.5f || horizontal < 1.0e-6f) return {n,v};
  const Vec4 wall{n[0]/horizontal,0.0f,n[2]/horizontal,0.0f};
  if (std::abs(n[1]) < 0.25f && v[1] > 0.8f * speed && horizontal > 0.9f)
    return {wall,v};
  const float reach=0.25f+0.4f*std::clamp(assist,0.0f,1.0f);
  const float into=v[0]*wall[0]+v[2]*wall[2];
  const float climb=v[1]/VectorMax(std::sqrt(v[1]*v[1]+into*into),1.0e-6f);
  if (assist <= 0.0f || n[1] <= 0.0f || n[1] >= reach || v[1] <= 0.0f
      || climb < std::sqrt(1.0f-reach*reach)-0.1f) return {n,v};
  const float out=VectorMin(into,0.0f);
  return {wall,Vec4{v[0]-wall[0]*out,v[1],v[2]-wall[2]*out,v[3]}};
}
Vec4 AirTrajectoryVertDepartureNormal(Vec4 n, Vec4 v, float direction) {
  return AirTrajectoryVertDeparture(n,v,direction,0.0f).first;
}
bool AirTrajectoryRuntime::Load(const SettingsDatabase &data,
                                std::string &error) {
  AirTrajectoryRuntime value;
  if (!LoadAirTrajectorySelectorSettings(data, value.settings, error) ||
      !value.grind_settings_.Load(data, error))
    return false;
  *this = std::move(value);
  error.clear();
  return true;
}
bool AirTrajectoryRuntime::Launch(AirLaunchInfo info, AirSelectorInput input,
                                  const WorldGeometry &world, bool &launched,
                                  std::string &error) {
  const auto departure=AirTrajectoryVertDeparture(
      input.ground_normal,info.start_velocity,input.directional_input,vert_assist);
  input.ground_normal=departure.first;info.start_velocity=departure.second;
  bool did_launch;
  if (!selector.Launch(info, input, settings, did_launch, error))
    return false;
  if (did_launch && !Submit(world, error))
    return false;
  launched = did_launch;
  error.clear();
  return true;
}
void AirTrajectoryRuntime::BindGrindWorld(
    std::shared_ptr<const PlayerGrindStaticProvider> provider) {
  grind_world_ = std::move(provider);
  nearby_grinds_.clear();
}
bool AirTrajectoryRuntime::Update(AirSelectorInput input,
                                  const WorldGeometry &world,
                                  AirTrajectoryGrindContext context,
                                  bool &valid, std::string &error) {
  if (!pending_results_) {
    valid = selector.UpdateWithoutCompletion();
    error.clear();
    return true;
  }
  // Source takes the batch before checking provider registration. On failure
  // the selector remains pending, but the completed results are consumed.
  auto results = std::move(*pending_results_);
  pending_results_.reset();
  if (!grind_world_) {
    error = "Trajectory static grind provider was not registered";
    return false;
  }
  SelectionServices services(grind_settings_, world, *grind_world_,
                             nearby_grinds_, input.grind_lock_distance, context);
  bool did_validate;
  if (!selector.CompleteBatch(results, input, settings, services, did_validate,
                               error))
    return false;
  if (selector.Pending() && !Submit(world, error))
    return false;
  valid = did_validate;
  error.clear();
  return true;
}
bool AirTrajectoryRuntime::Submit(const WorldGeometry &world,
                                  std::string &error) {
  std::vector<AirTrajectoryQueryResult> results;
  results.reserve(selector.Requests().size());
  for (const auto &request : selector.Requests()) {
    AirTrajectoryQueryResult result;
    if (!Query(world, request, result, error))
      return false;
    results.push_back(std::move(result));
  }
  pending_results_ = std::move(results);
  error.clear();
  return true;
}
} // namespace atelier::skate
