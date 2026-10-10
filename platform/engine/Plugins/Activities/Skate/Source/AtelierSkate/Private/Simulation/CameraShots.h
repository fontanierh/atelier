#pragma once
#include "CameraTracking.h"
#include <map>
#include <vector>
namespace atelier::skate::camera {
struct Shot {
  float distance = 2, lens_length = 12;
  Vec4 smoothing;
  std::array<float, 10> reference_weights{0, 0, 0, 0, 1, 0, 0, 0, 0, 0};
  float board_offset = 0, position_heading, position_elevation = 0;
  std::array<float, 3> framing{};
  std::uint8_t follow_subject_in_air = 1, mirror_for_stance = 1,
               snap_to_reference_point = 0, use_previous_shot = 0,
               use_drop_predictor = 0, use_free_camera_stick = 0,
               avoidance_override = 0;
  float blur = 1, transition_blur = 1, subject_opacity = 1;
  std::uint32_t collision_hint = 0, anchor = 0, compass_north = 0;
  float world_heading = 0;
  Quat arm_orientation{0, 0, 0, 1}, camera_orientation{0, 0, 0, 1};
  Shot();
  void UpdateNormal(float north, float heading_mirror);
  Vec4 ReferencePoint(const std::array<Vec4, 10> &positions,
                      Vec4 board_offset_direction, Vec4 fallback) const;
  void InterpolateFrom(Shot from, Shot to, float fraction);
};
float InterpolateFloat(float from, float to, std::uint32_t style,
                       float fraction);
float FilterBlendValue(float previous, float raw, float smoothing,
                       float minimum, float maximum);
struct BlendIntervalResult {
  std::size_t left, right;
  float fraction;
};
std::optional<BlendIntervalResult> BlendInterval(std::array<float, 3> points,
                                                 std::array<bool, 3> present,
                                                 float value);
struct ShotDefinition {
  std::string name;
  std::uint32_t shot_type = 0;
  Shot shot;
  float transition_time = 0.5f;
  std::uint32_t transition_units = 0;
  std::array<std::optional<std::string>, 3> children;
  std::array<float, 3> blend_points{};
  float blend_value = 0;
  std::uint32_t blend_type = 0;
  float blend_smoothing = 0;
};
class ShotDatabase {
public:
  virtual ~ShotDatabase() = default;
  virtual bool Load(std::string_view name, ShotDefinition &result,
                    std::string &error) const = 0;
};
class StockShots final : public ShotDatabase {
public:
  std::map<std::string, ShotDefinition> definitions;
  bool Load(std::string_view name, ShotDefinition &result,
            std::string &error) const override;
};
class ShotEnvironment {
public:
  virtual ~ShotEnvironment() = default;
  virtual float HeadingMirror() const = 0;
  virtual bool CompassNorth(std::uint32_t entry, float &result,
                            std::string &error) const = 0;
  virtual bool SpecialCameraFlag() const = 0;
  virtual float RawBlendValue(std::uint32_t kind, float authored, float dt) = 0;
};
struct ShotPlacement {
  Vec4 anchor{}, camera_position{};
  std::uint8_t clamp_height = 0;
  float floor_height = 0;
};
struct ShotNode {
  ShotDefinition definition;
  std::vector<ShotNode> children;
  bool Setup(const ShotDatabase &database, ShotEnvironment &env,
             std::vector<std::string> &ancestry, std::size_t &count,
             std::string &error);
  bool Update(float dt, ShotEnvironment &env, std::string &error);
};
struct ShotManager {
  ShotNode current;
  Shot previous, interpolated;
  float elapsed = 0, transition_distance = 0, transition_duration = 0,
        transition_override = -1;
  bool instant_changes = false;
  void ApplyGraphTransition(float incoming, float outgoing);
  Shot FirstLeaf() const;
  bool SetShot(std::string_view name, bool force, const ShotDatabase &database,
               ShotEnvironment &env, ShotPlacement placement, bool &changed,
               std::string &error);
  bool Update(float dt, ShotEnvironment &env, float &fraction,
              std::string &error);
  void MakeInstant();
  bool IsTransitioning() const;
  float FramingFraction() const;
  float Duration(bool camera_man) const;
};
std::string AsciiLower(std::string_view name);
} // namespace atelier::skate::camera
