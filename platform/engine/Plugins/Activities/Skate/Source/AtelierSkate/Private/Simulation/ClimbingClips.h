#pragma once
#include "ClimbingMath.h"
#include <string>
#include <string_view>
#include <vector>
namespace atelier::skate {
struct ClimbingClip {
  std::string name;
  float fps=0;
  std::vector<std::string> names;
  std::vector<std::int32_t> parents;
  std::vector<std::vector<std::array<float,10>>> frames;
  bool Validate(std::string& error) const;
  float Duration() const;
  std::vector<climbing_math::Transform> Sample(float time) const;
  std::vector<Mat4> Globals(const std::vector<climbing_math::Transform>&) const;
  std::size_t Index(std::string_view) const;
  Vec3 Hands(const std::vector<Mat4>&) const;
  Vec3 Feet(const std::vector<Mat4>&) const;
};
struct ClimbingClipFile {std::uint32_t version;std::vector<ClimbingClip> clips;};
struct ClimbingClips {
  ClimbingClip reach,mantle;
  static bool FromConverted(ClimbingClipFile,ClimbingClips&,std::string& error);
};
// The simulation schema v1: eight magic bytes "SKCLIP1\0", u32 source version, u32
// clip count; per clip string(name), f32 fps, names count+strings, parents
// count+i32, frames count, then each frame count+SQT10 floats. Strings carry
// u32 byte length and UTF-8 bytes; words/floats are little endian. The source
// file's absence is transported separately as std::nullopt, not an empty file.
bool ReadClimbingClipFile(const std::vector<std::uint8_t>&,ClimbingClipFile&,
                          std::string& error);
} // namespace atelier::skate
