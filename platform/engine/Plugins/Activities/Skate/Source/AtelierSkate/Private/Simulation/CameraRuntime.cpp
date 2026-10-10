#include "CameraRuntime.h"
#include <charconv>
#include <cmath>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate::camera {
namespace {
// Rust's Debug presentation is retained for the source runtime's nonfinite
// frame diagnostic. Arithmetic and comparisons use the original float bits.
std::string DebugFloat(float value) {
  if (std::isnan(value))
    return "NaN";
  if (std::isinf(value))
    return std::signbit(value) ? "-inf" : "inf";
  char buffer[64];
  const auto converted = std::to_chars(buffer, buffer + sizeof(buffer), value);
  std::string text(buffer, converted.ptr);
  const auto exponent = text.find('e');
  if (exponent != std::string::npos) {
    auto first = exponent + 1;
    if (first < text.size() && text[first] == '+')
      text.erase(first, 1);
    if (first < text.size() && text[first] == '-')
      ++first;
    while (first + 1 < text.size() && text[first] == '0')
      text.erase(first, 1);
  } else if (text.find('.') == std::string::npos)
    text += ".0";
  return text;
}
template <class Values> std::string DebugArray(const Values &values) {
  std::string text = "[";
  for (std::size_t index = 0; index < values.size(); ++index) {
    if (index != 0)
      text += ", ";
    text += DebugFloat(values[index]);
  }
  return text + "]";
}
std::string DebugMatrix(Mat4 value) {
  std::string text = "[";
  for (std::size_t index = 0; index < value.size(); ++index) {
    if (index != 0)
      text += ", ";
    text += DebugArray(value[index]);
  }
  return text + "]";
}
std::string DebugBasis(Basis3 value) {
  return "Basis3 { columns: [" + DebugArray(value.columns[0]) + ", " +
         DebugArray(value.columns[1]) + ", " + DebugArray(value.columns[2]) +
         "] }";
}
std::string DebugFrame(CameraFrame value) {
  return "CameraFrame { basis: " + DebugBasis(value.basis) +
         ", position: " + DebugArray(value.position) +
         ", previous_basis: " + DebugBasis(value.previous_basis) +
         ", previous_position: " + DebugArray(value.previous_position) +
         ", linear_velocity: " + DebugArray(value.linear_velocity) +
         ", angular_velocity: " + DebugArray(value.angular_velocity) +
         ", shake_translation: " + DebugArray(value.shake_translation) +
         ", discontinuity: " + (value.discontinuity ? "true" : "false") +
         ", field_of_view_degrees: " + DebugFloat(value.field_of_view_degrees) +
         ", opacity: " + DebugFloat(value.opacity) +
         ", blur: " + DebugFloat(value.blur) + " }";
}
bool Finite(const CameraFrame &value) {
  for (float lane : value.position)
    if (!std::isfinite(lane))
      return false;
  for (const auto &column : value.basis.columns)
    for (float lane : column)
      if (!std::isfinite(lane))
        return false;
  return std::isfinite(value.field_of_view_degrees);
}
} // namespace

bool SubjectPublisher::Publish(CameraSubjectSnapshot input,
                               const CameraMan &manager,
                               CompassSettings settings, ManagerSubject &result,
                               std::string &error) {
  if (last_tick && input.tick <= *last_tick) {
    error = "Camera subject publication is not monotonic: previous=" +
            std::to_string(*last_tick) +
            ", current=" + std::to_string(input.tick);
    return false;
  }
  last_tick = input.tick;
  const auto publication = pose.Publish(input.pose);
  input.subject.rig.transform = publication.transform;
  input.subject.rig.skeleton_root = input.pose.skeleton_root;
  input.anchors.damped_center_of_mass = publication.damped_center_of_mass;
  anchors.Update(input.anchors);
  input.subject.anchors = anchors.entries;
  input.reference_points.damped_centre_of_mass =
      publication.damped_center_of_mass;
  input.reference_points.tracked_anchor = manager.rig.anchor.position;
  input.reference_points.incline_normal = manager.state.incline_normal;
  input.subject.rig.reference_positions = input.reference_points.Positions();
  const auto selected =
      manager.shots.current.definition.name.empty()
          ? 5u
          : manager.shots.current.definition.shot.compass_north;
  const auto compass_input =
      input.compass.Bind(input.subject, manager.frame.position, selected);
  input.subject.compass =
      compass.Update(input.subject.reset != 0 ? 0.0f : Bits(0x3c888889),
                     compass_input, settings);
  result = input.subject;
  error.clear();
  return true;
}

bool CameraRuntime::Load(const SettingsDatabase &stock, const Graph &source,
                         const std::vector<std::uint8_t> &camera_data,
                         std::string &error) {
  CameraRuntime next;
  if (!LoadSlowMotionSettings(stock, next.settings.slow_motion, error) ||
      !next.graph.FromGraph(source, next.settings.slow_motion, error) ||
      !next.data.Load(camera_data, error) ||
      !LoadManagerSettings(stock, next.settings.manager, error) ||
      !LoadCompassSettings(stock, next.settings.compass, error))
    return false;
  *this = std::move(next);
  error.clear();
  return true;
}

bool CameraRuntime::Advance(float dt, CameraSubjectSnapshot snapshot,
                            const WorldGeometry &world, Vec4 query_gravity,
                            const CameraGraphEnvironment &environment,
                            MovingObstacleProvider &moving, CameraFrame &result,
                            std::string &error) {
  if (latest_subject && snapshot.tick <= latest_subject->tick) {
    error = "Camera received non-monotonic subject tick: previous=" +
            std::to_string(latest_subject->tick) +
            ", current=" + std::to_string(snapshot.tick);
    return false;
  }
  latest_subject = snapshot;
  ManagerSubject published;
  if (!subject.Publish(snapshot, manager, settings.compass, published, error) ||
      !manager.Prepare(published, settings.manager, error))
    return false;
  std::vector<SimulationRateRequest> requests;
  if (!graph.Update(dt, manager, published, snapshot.graph, environment,
                    data.shots, requests, error))
    return false;
  simulation_rate_requests.insert(simulation_rate_requests.end(),
                                  requests.begin(), requests.end());
  CameraTrajectory a(world, query_gravity, trajectories[0]);
  CameraTrajectory b(world, query_gravity, trajectories[1]);
  CameraTrajectory c(world, query_gravity, trajectories[2]);
  CameraCollision collision(world);
  CameraFrame output;
  if (!manager.Update(dt, published, settings.manager,
                      {&data.shakes[0], &data.shakes[1]}, {&a, &b, &c}, moving,
                      collision, collision, output, error))
    return false;
  if (collision.error) {
    error = *collision.error;
    return false;
  }
  for (const auto &trajectory : trajectories)
    if (trajectory.error) {
      error = *trajectory.error;
      return false;
    }
  if (!Finite(output)) {
    error = "Normal gameplay camera produced a non-finite frame: frame=" +
            DebugFrame(output) + "; lens_length=" +
            DebugFloat(manager.shots.interpolated.lens_length) +
            "; aspect_ratio=" + DebugFloat(manager.state.aspect_ratio) +
            "; subject_transform=" + DebugMatrix(published.rig.transform) +
            "; skeleton_root=" + DebugMatrix(published.rig.skeleton_root) +
            "; ground_normal=" + DebugArray(published.ground_normal) +
            "; launch_position=" + DebugArray(published.launch_position) +
            "; landing_position=" + DebugArray(published.landing_position);
    return false;
  }
  frame = output;
  result = output;
  error.clear();
  return true;
}
} // namespace atelier::skate::camera
