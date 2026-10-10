#include "AirTrajectoryGrindRuntime.h"
#include "StockSettingsReader.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
float Float(std::uint32_t word) {
  float result;
  std::memcpy(&result, &word, sizeof(result));
  return result;
}
Vec4 Sub(Vec4 a, Vec4 b) {
  for (std::size_t i = 0; i < 4; ++i)
    a[i] -= b[i];
  return a;
}
Vec4 Scale(Vec4 a, float scalar) {
  for (auto &lane : a)
    lane *= scalar;
  return a;
}
float LengthSquaredValue(float square) {
  return square == 0 ? 0.0f : square * InverseLengthSquared(square, 2);
}
Vec4 Unit(Vec4 a) {
  const float square = Dot3(a, a);
  return LengthSquaredValue(square) > Float(0x358637bd)
             ? Scale(a, InverseLengthSquared(square, 2))
             : Vec4{};
}
Vec4 Cross(Vec4 a, Vec4 b) {
  return {std::fma(-a[2], b[1], a[1] * b[2]),
          std::fma(-a[0], b[2], a[2] * b[0]),
          std::fma(-a[1], b[0], a[0] * b[1]), 0};
}
bool HeightGraph(const SettingsDatabase &data, const StockSettingsReader &reader,
                 PointGraph<8> &result, std::string &error) {
  constexpr std::string_view category = "physics_trajectory";
  constexpr std::string_view name = "RequiredAngleVsHeight";
  const auto *field = data.Field(category, "default", name);
  std::vector<std::uint32_t> words;
  if (!field) {
    // Use the shared original lookup diagnostics, including inheritance
    // failures. There is no completed replacement for a missing graph.
    reader.Words(category, "default", name, 20, words, error);
    return false;
  }
  if (field->type != "Sk8::PointNegGraphData8") {
    error = "Wrong stock graph type physics_trajectory/RequiredAngleVsHeight";
    return false;
  }
  if (!reader.Words(category, "default", name, 20, words, error))
    return false;
  for (std::size_t i = 0; i < 8; ++i) {
    result.x[i] = Float(words[4 + i]);
    result.y[i] = Float(words[12 + i]);
  }
  return true;
}
class SurfaceQueries final : public PlayerGrindSurfaceQueries {
public:
  SurfaceQueries(const WorldGeometry &world,
                 std::array<std::uint32_t, 2> actor)
      : world_(world), actor_(actor) {}
  bool Query(std::size_t index, PlayerGrindProbe probe,
             std::optional<PlayerGrindProbeHit> &result,
             std::string &error) override {
    return PlayerGrindSurfaceProbe(world_, actor_, index, probe, result, error);
  }
private:
  const WorldGeometry &world_;
  std::array<std::uint32_t, 2> actor_;
};
} // namespace
AirTrajectoryGrindContext AirTrajectoryGrindContext::FromProcessed(
    const ProcessedPhysicsInput &p, Vec4 board_position) {
  Vec4 body_position;
  for (std::size_t i = 0; i < 4; ++i)
    body_position[i] = Float(p.vectors_544_560_592_608[2][i]);
  return {board_position, body_position,
          {p.actor_query_2948, p.actor_query_2952}};
}
bool AirTrajectoryGrindRuntime::Load(const SettingsDatabase &data,
                                     std::string &error) {
  AirTrajectoryGrindRuntime value;
  const StockSettingsReader reader(data);
  const auto t = [&](std::string_view name, float &output) {
    return reader.Float("physics_trajectory", "default", name, output, error);
  };
  auto &l = value.limits;
  l.lock_distance = 0;
  if (!t("GrindMaxSpeedSqrIntoLedge", l.max_speed_squared_ledge) ||
      !t("GrindMaxSpeedSqrIntoGrind", l.max_speed_squared_rail) ||
      !t("GrindMaxSpeedDownOntoGrind", l.max_downward_speed) ||
      !t("GrindLockLedgeScalar2", l.ledge_scalars[0]) ||
      !t("GrindLockLedgeScalar", l.ledge_scalars[1]) ||
      !t("GrindLockLedgeLowSideScalar2", l.ledge_scalars[2]) ||
      !t("GrindLockLedgeLowSideScalar", l.ledge_scalars[3]) ||
      !t("GrindTipScalar", l.tip_scalar) ||
      !t("GrindAdjustMaxAngle", l.maximum_adjust_angle) ||
      !reader.Float("physicsdeck", "default", "DeckMidLength",
                    l.deck_dimensions[0], error) ||
      !reader.Float("physicsdeck", "default", "DeckFrontEndSize",
                    l.deck_dimensions[1], error) ||
      !HeightGraph(data, reader, value.height, error) ||
      !t("GrindOffset", value.padding) ||
      !t("MaxTrajectoryAdjust", value.maximum_adjust) ||
      !t("GrindLandingVelScalar", value.velocity_scalar) ||
      !t("GrindLandingMaxAngle", value.max_angle) ||
      !t("ScoreGrind", value.score) ||
      !reader.Float("physics_grinds", "default", "DeckCenterToTruck",
                    value.truck_distance, error))
    return false;
  std::vector<std::uint32_t> words;
  if (!reader.Words("physics_trajectory", "default",
                    "GrindPenaltyVsDistToGrind", 20, words, error))
    return false;
  value.penalty_domain = Float(words[2]);
  *this = std::move(value);
  error.clear();
  return true;
}
bool AirTrajectoryGrindRuntime::Evaluate(
    AirTrajectoryPrediction &prediction, bool acquire,
    const WorldGeometry &world, const PlayerGrindStaticProvider &provider,
    std::vector<std::size_t> &nearby, float lock_distance,
    AirTrajectoryGrindContext context, AirTrajectoryGrindEvaluation &output,
    std::string &error) const {
  const auto collision_position = prediction.CollisionPosition();
  const auto collision_velocity = prediction.CollisionVelocity();
  if (acquire) {
    std::array<float, 3> min, max;
    for (std::size_t i = 0; i < 3; ++i) {
      min[i] = collision_position[i] - (i == 1 ? 0.5f : 2.0f);
      max[i] = collision_position[i] + (i == 1 ? 4.0f : 2.0f);
    }
    std::vector<std::size_t> indices;
    if (!provider.Query(min, max, indices, error))
      return false;
    nearby = AirTrajectoryBoxFilter(indices, provider.Primitives(),
                                    context.board_position);
  }
  AirTrajectoryGrindEvaluation result{
      std::nullopt, 0, 1000, std::nullopt, penalty_domain};
  float square = 1000000;
  for (const auto index : nearby) {
    const auto edge = provider.Primitives()[index];
    const auto axis = Unit(Sub(edge.end, edge.start));
    const auto from = Sub(collision_position, edge.start);
    const auto end = Sub(collision_position, edge.end);
    const auto perpendicular = Sub(from, Scale(axis, Dot3(axis, from)));
    square = VectorMin(
        VectorMin(VectorMin(Dot3(perpendicular, perpendicular), Dot3(from, from)),
                  Dot3(end, end)), square);
  }
  if (!nearby.empty())
    result.distance = LengthSquaredValue(square);
  if (!acquire || nearby.empty()) {
    output = std::move(result);
    error.clear();
    return true;
  }
  std::vector<AirTrajectoryGrindCandidate> candidates;
  for (const auto index : nearby) {
    const auto candidate = ConsiderAirTrajectoryGrindPrimitive(
        prediction, provider.Primitives()[index], index, padding);
    if (candidate)
      candidates.push_back(*candidate);
  }
  auto current_limits = limits;
  current_limits.lock_distance = lock_distance;
  while (const auto candidate =
             TakeBestAirTrajectoryGrind(candidates, lock_distance, height)) {
    const auto c = *candidate;
    const auto edge = provider.Primitives()[c.primitive];
    const PlayerGrindSurfaceInput query{edge.start, edge.end, c.point,
                                       std::nullopt, truck_distance};
    if (!PreparePlayerGrindSurface(query))
      continue;
    SurfaceQueries queries(world, context.actor);
    PlayerGrindSurface surface;
    if (!InvestigatePlayerGrindSurface(query, queries, surface, error))
      return false;
    GrindAirLandingOrientation orientation;
    orientation.kind = std::uint32_t(PlayerGrindGeometryKind::Impossible);
    Vec4 support{};
    UpdatePlayerGrindLandingOrientation(
        &surface, context.board_position, c.point, support, orientation);
    const auto delta = AdmitAirTrajectoryGrindDisplacement(
        prediction, c, edge, collision_velocity, context.body_position,
        {orientation.kind, orientation.high_side}, current_limits,
        result.effective_lock_distance);
    if (!delta)
      continue;
    const auto original_velocity = prediction.request.trajectory.velocity;
    ApplyAirTrajectoryGrindTarget(prediction, c, *delta, support,
                                  original_velocity, maximum_adjust,
                                  velocity_scalar, max_angle);
    auto vertical = Cross(Cross(c.direction, {0, 1, 0, 0}), c.direction);
    if (vertical[1] < 0)
      vertical = Scale(vertical, -1);
    vertical = LengthSquaredValue(Dot3(vertical, vertical)) > Float(0x358637bd)
                   ? Unit(vertical) : Vec4{0, 1, 0, 0};
    const auto *metadata = provider.Metadata(c.primitive);
    if (!metadata) {
      error = "Accepted grind primitive lacks native metadata";
      return false;
    }
    result.target = AirTrajectoryGrindTarget{
        edge, c.primitive, metadata->flags, orientation, c.point, vertical};
    result.score = score;
    output = std::move(result);
    error.clear();
    return true;
  }
  output = std::move(result);
  error.clear();
  return true;
}
} // namespace atelier::skate
