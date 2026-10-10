#include "CameraSettings.h"
#include "DataReader.h"
#include "StockSettingsReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
namespace {
bool Words(const SettingsDatabase &data, std::string_view category,
           std::string_view key, std::string_view field, std::size_t count,
           std::vector<std::uint32_t> &result, std::string &error) {
  return StockSettingsReader(data).Words(category, key, field, count, result,
                                         error);
}
bool Curve(const SettingsDatabase &data, std::string_view category,
           std::string_view key, std::string_view name, PointGraph<8> &result,
           std::string &error) {
  std::vector<std::uint32_t> words;
  if (!Words(data, category, key, name, 16, words, error))
    return false;
  for (std::size_t i = 0; i < 8; ++i) {
    result.x[i] = Bits(words[i]);
    result.y[i] = Bits(words[i + 8]);
    if (!std::isfinite(result.x[i]) || !std::isfinite(result.y[i])) {
      error = "Non-finite camera curve " + std::string(category) + "/" +
              std::string(key) + "/" + std::string(name);
      return false;
    }
  }
  return true;
}
Vec4 Vector(detail::DataReader &input) {
  return {input.Float(), input.Float(), input.Float(), input.Float()};
}
} // namespace
bool LoadManagerSettings(const SettingsDatabase &data, ManagerSettings &output,
                         std::string &error) {
  CameraSettings next;
  StockSettingsReader read(data);
  const auto f = [&](std::string_view c, std::string_view k, std::string_view n,
                     float &v) { return read.Float(c, k, n, v, error); };
  const auto angle = [&](std::string_view key, AngleTrackingSettings &s) {
    return f("camera_tracker", key, "SpeedClamp", s.speed_clamp_degrees) &&
           f("camera_tracker", key, "AccelerationClampMin",
             s.acceleration_min_degrees) &&
           f("camera_tracker", key, "AccelerationClampMax",
             s.acceleration_max_degrees) &&
           f("camera_tracker", key, "DeltaUmbra", s.delta_umbra_degrees) &&
           f("camera_tracker", key, "DeltaPenumbra", s.delta_penumbra_degrees);
  };
  auto &rig = next.manager.rig;
  auto &anchor = rig.anchor;
  auto &avoid = rig.avoidance;
  auto &position = rig.positioning;
  if (!angle("heading", rig.heading) || !angle("elevation", rig.elevation) ||
      !Curve(data, "camera_lag_profile", "push", "Curve", anchor.latch_curve,
             error) ||
      !Curve(data, "camera_lag_profile", "pump", "Curve", anchor.input_curve,
             error) ||
      !f("camera", "subject_tracker", "SubjectTrackerMaxSpeed",
         anchor.speed_clamp) ||
      !f("camera", "subject_tracker", "SubjectTrackerMaxAcceleration",
         anchor.acceleration_clamp) ||
      !f("camera_lag_profile", "push", "MaxSmoothing", anchor.latch_scale) ||
      !f("camera", "dynamics", "PumpingMinAcceleration",
         anchor.input_threshold) ||
      !f("camera_lag_profile", "pump", "MaxSmoothing", anchor.input_scale))
    return false;
  if (!f("camera", "dynamics", "AvoidanceLookahead", avoid.horizon) ||
      !f("camera", "dynamics", "AvoidanceHeadingSmoothing",
         avoid.heading_smoothing) ||
      !f("camera", "dynamics", "AvoidanceElevationSmoothing",
         avoid.elevation_smoothing) ||
      !f("camera", "dynamics", "AvoidanceEaseOut", avoid.ease_out_time) ||
      !f("camera_positioner", "default", "AvoidanceCollisionOffset",
         avoid.radius_padding))
    return false;
  if (!f("camera_tracker", "distance", "SpeedClamp",
         position.normal.speed_clamp) ||
      !f("camera_tracker", "distance", "SmoothingConstant",
         position.normal.smoothing) ||
      !f("camera_tracker", "distance", "AccelerationClampMax",
         position.normal.acceleration_clamp) ||
      !f("camera_tracker", "distance", "FastSpeedClamp",
         position.alternate.speed_clamp) ||
      !f("camera_tracker", "distance", "Hash_E2D9D0FAAB8CB7F3",
         position.alternate.smoothing) ||
      !f("camera_tracker", "distance", "FastAccelerationClampMax",
         position.alternate.acceleration_clamp) ||
      !f("camera_positioner", "default", "MinDistance",
         position.minimum_distance) ||
      !f("camera_positioner", "default", "MinDistanceDuringWipeout",
         position.alternate_minimum_distance) ||
      !f("camera", "dynamics", "CollisionInterpolationDuration",
         rig.collision_hold_duration))
    return false;
  rig.normalization_threshold = {Bits(0x358637bd), Bits(0x358637bd),
                                 Bits(0x358637bd), Bits(0x358637bd)};
  auto &orientation = next.manager.orientation;
  const auto tracker = [&](std::string_view key,
                           OrientationTrackerSettings &s) {
    return f("camera_tracker", key, "AccelerationClampMin",
             s.acceleration_min_degrees) &&
           f("camera_tracker", key, "AccelerationClampMax",
             s.acceleration_max_degrees) &&
           f("camera_tracker", key, "SmoothingMin", s.smoothing_min) &&
           f("camera_tracker", key, "DeltaUmbra", s.delta_umbra_degrees) &&
           f("camera_tracker", key, "DeltaPenumbra", s.delta_penumbra_degrees);
  };
  if (!f("camera", "rotation", "PanUmbra", orientation.pan_umbra_degrees) ||
      !f("camera", "rotation", "PanPenumbra",
         orientation.pan_penumbra_degrees) ||
      !Curve(data, "camera", "rotation", "PanSmoothingCurve",
             orientation.pan_smoothing_curve, error) ||
      !f("camera", "rotation", "PanMinSmoothing",
         orientation.pan_minimum_smoothing) ||
      !tracker("pan", orientation.pan) || !tracker("tilt", orientation.tilt))
    return false;
  if (!f("camera", "dynamics", "MaxPitch",
         next.manager.framing.maximum_pitch_degrees) ||
      !f("camera", "dynamics", "DutchInterpolationSpeed",
         next.manager.framing.roll_response))
    return false;
  auto &drop = next.manager.drop;
  if (!f("camera_droppredictor", "default", "MinTestDistance",
         drop.minimum_test_distance) ||
      !f("camera_droppredictor", "default", "TotalTestTime",
         drop.total_test_time) ||
      !f("camera_droppredictor", "default", "Hash_FB5A1024D47298A1",
         drop.maximum_test_distance) ||
      !f("camera_droppredictor", "default", "MaxDropDistance",
         drop.maximum_drop_distance))
    return false;
  auto &look = next.manager.look;
  if (!f("camera", "freecam", "FreeCamHeadingOffset",
         look.heading_offset_degrees) ||
      !f("camera", "freecam", "FreeCamHeadingSpeed", look.heading_speed) ||
      !f("camera", "freecam", "FreeCamElevationOffset",
         look.elevation_offset_degrees) ||
      !f("camera", "freecam", "FreeCamElevationSpeed", look.elevation_speed))
    return false;
  auto &shake = next.manager.shake;
  const auto matrix = [&](std::string_view name, Mat4 &result) {
    std::vector<std::uint32_t> words;
    if (!Words(data, "camera_shake", "default", name, 16, words, error))
      return false;
    for (std::size_t r = 0; r < 4; ++r)
      for (std::size_t c = 0; c < 4; ++c)
        result[r][c] = Bits(words[r * 4 + c]);
    return true;
  };
  if (!matrix("AmplitudeCurve", shake.amplitude_curve) ||
      !matrix("FrequencyCurve", shake.frequency_curve))
    return false;
  const std::array<std::pair<const char *, float *>, 15> shake_fields{
      {{"OneShotMagnitude", &shake.impulse_magnitude},
       {"OneShotMinVelocity", &shake.impulse_minimum_velocity},
       {"OneShotMaxVelocity", &shake.impulse_maximum_velocity},
       {"OneShotFrequency", &shake.impulse_frequency},
       {"OneShotDecay", &shake.impulse_decay},
       {"AmplitudeMin", &shake.amplitude_minimum},
       {"AmplitudeMax", &shake.amplitude_maximum},
       {"AmplitudeTopSkaterSpeed", &shake.amplitude_top_speed},
       {"FrequencyMin", &shake.frequency_minimum},
       {"FrequencyMax", &shake.frequency_maximum},
       {"FrequencyTopSkaterSpeed", &shake.frequency_top_speed},
       {"DataFPS", &shake.data_frames_per_second},
       {"TranslationMultiplier", &shake.translation_multiplier},
       {"RotationMultiplier", &shake.rotation_multiplier},
       {"DutchMultiplier", &shake.dutch_multiplier}}};
  for (const auto &[name, value] : shake_fields)
    if (!f("camera_shake", "default", name, *value))
      return false;
  if (!f("camera", "dynamics", "TurningCentredDeadzone",
         next.manager.steering_threshold))
    return false;
  output = std::move(next.manager);
  error.clear();
  return true;
}
bool LoadCompassSettings(const SettingsDatabase &data, CompassSettings &output,
                         std::string &error) {
  CameraSettings next;
  StockSettingsReader read(data);
  const auto f = [&](std::string_view c, std::string_view k, std::string_view n,
                     float &v) { return read.Float(c, k, n, v, error); };
  auto &compass = next.compass;
  if (!f("camera", "dynamics", "HeadingChangeResponseSpeed",
         compass.heading_response) ||
      !f("camera_compass", "default", "TimeBeforeAutoLineup",
         compass.time_before_lineup) ||
      !f("camera_compass", "default", "AutoLineupSpeed",
         compass.lineup_speed) ||
      !f("camera_compass", "default", "MinDeadzoneSpeed",
         compass.minimum_deadzone_speed) ||
      !f("camera_compass", "default", "MaxDeadzoneSpeed",
         compass.maximum_deadzone_speed) ||
      !f("camera_compass", "default", "MaxDeadzoneSize",
         compass.maximum_deadzone_size) ||
      !f("camera_compass", "default", "DeadzoneSizeSmoothing",
         compass.deadzone_smoothing))
    return false;
  output = next.compass;
  error.clear();
  return true;
}
bool LoadSlowMotionSettings(const SettingsDatabase &data,
                            SlowMotionSettings &output, std::string &error) {
  CameraSettings next;
  StockSettingsReader read(data);
  const auto f = [&](std::string_view c, std::string_view k, std::string_view n,
                     float &v) { return read.Float(c, k, n, v, error); };
  std::vector<std::uint32_t> values;
  if (!Words(data, "slowmotion_controller", "default", "timescale", 32, values,
             error))
    return false;
  for (std::size_t i = 0; i < 16; ++i) {
    next.slow_motion.timescale.x[i] = Bits(values[i]);
    next.slow_motion.timescale.y[i] = Bits(values[i + 16]);
  }
  if (!f("slowmotion_controller", "default", "fps_at_scale_one",
         next.slow_motion.fps_at_scale_one))
    return false;
  output = next.slow_motion;
  error.clear();
  return true;
}
bool CameraSettings::Load(const SettingsDatabase &data, std::string &error) {
  CameraSettings next;
  if (!LoadSlowMotionSettings(data, next.slow_motion, error) ||
      !LoadManagerSettings(data, next.manager, error) ||
      !LoadCompassSettings(data, next.compass, error))
    return false;
  *this = std::move(next);
  error.clear();
  return true;
}
bool CameraData::Load(const std::vector<std::uint8_t> &bytes,
                      std::string &error) {
  if (bytes.size() < 8 || std::memcmp(bytes.data(), "ATCAM001", 8) != 0) {
    error = "Invalid native camera signature";
    return false;
  }
  detail::DataReader input{bytes};
  CameraData next;
  next.source_identity = input.String();
  const auto count = input.Word();
  if (count > input.Remaining() / 8) {
    error = "Invalid native camera shot count";
    return false;
  }
  for (std::uint32_t index = 0; index < count; ++index) {
    ShotDefinition d;
    d.name = input.String();
    d.shot_type = input.Word();
    auto &shot = d.shot;
    shot.distance = input.Float();
    shot.lens_length = input.Float();
    shot.smoothing = Vector(input);
    for (auto &v : shot.reference_weights)
      v = input.Float();
    shot.board_offset = input.Float();
    shot.position_heading = input.Float();
    shot.position_elevation = input.Float();
    for (auto &v : shot.framing)
      v = input.Float();
    std::array<std::uint8_t *, 7> flags{
        &shot.follow_subject_in_air,   &shot.mirror_for_stance,
        &shot.snap_to_reference_point, &shot.use_previous_shot,
        &shot.use_drop_predictor,      &shot.use_free_camera_stick,
        &shot.avoidance_override};
    for (auto *flag : flags) {
      const auto word = input.Word();
      if (word > 255)
        input.ok = false;
      *flag = std::uint8_t(word);
    }
    shot.blur = input.Float();
    shot.transition_blur = input.Float();
    shot.subject_opacity = input.Float();
    shot.collision_hint = input.Word();
    shot.anchor = input.Word();
    shot.compass_north = input.Word();
    shot.world_heading = input.Float();
    shot.arm_orientation = Vector(input);
    shot.camera_orientation = Vector(input);
    d.transition_time = input.Float();
    d.transition_units = input.Word();
    for (auto &child : d.children) {
      const auto present = input.Word();
      if (present > 1)
        input.ok = false;
      if (present != 0)
        child = input.String();
    }
    for (auto &v : d.blend_points)
      v = input.Float();
    d.blend_value = input.Float();
    d.blend_type = input.Word();
    d.blend_smoothing = input.Float();
    if (!input.ok) {
      error = "Truncated native camera definition";
      return false;
    }
    if (!next.shots.definitions.emplace(d.name, d).second) {
      error = "Duplicate native camera shot " + d.name;
      return false;
    }
  }
  for (const auto &[name, definition] : next.shots.definitions)
    for (const auto &child : definition.children)
      if (child && !next.shots.definitions.count(*child)) {
        error =
            "Camera shot " + name + " references missing named shot " + *child;
        return false;
      }
  for (auto &samples : next.shakes) {
    const auto size = input.Word();
    if (size == 0 || size > input.Remaining() / 32) {
      error = "Invalid native camera sample count";
      return false;
    }
    samples.rotations.reserve(size);
    samples.translations.reserve(size);
    for (std::uint32_t index = 0; index < size; ++index) {
      samples.rotations.push_back(Vector(input));
      samples.translations.push_back(Vector(input));
    }
  }
  if (!input.ok || input.at != bytes.size()) {
    error = "Invalid native camera payload length";
    return false;
  }
  *this = std::move(next);
  error.clear();
  return true;
}
} // namespace atelier::skate::camera
