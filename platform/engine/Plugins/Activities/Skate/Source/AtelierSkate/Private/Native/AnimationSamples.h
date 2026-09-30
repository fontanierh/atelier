// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace atelier::skate
{
// Exact scale XYZ, quaternion XYZW and translation XYZ words.
using SampleWords = std::array<std::uint32_t,10>;
struct AnimationBone { std::string name; std::int32_t parent = -1, mirror = -1; };
struct AnimationReferencePose
{
    std::uint32_t bank = 0;
    std::string name;
    std::uint64_t record = 0;
    std::vector<SampleWords> samples;
};
class AnimationRig
{
public:
    std::vector<AnimationBone> bones;
    bool has_trajectory = false;
    std::vector<AnimationReferencePose> poses;
    bool Load(const std::vector<std::uint8_t>& bytes, std::string& error);
    const AnimationReferencePose* NamedPose(std::uint32_t bank, std::string_view name) const;
    const AnimationReferencePose* Pose(std::uint32_t bank, std::uint64_t record) const;
private:
    std::map<std::pair<std::uint32_t,std::string>,std::size_t> names_;
    std::map<std::pair<std::uint32_t,std::uint64_t>,std::size_t> records_;
};

class AnimationClipSamples
{
public:
    std::string name;
    std::uint32_t bank = 0;
    std::uint64_t record = 0;
    std::uint32_t fps_bits = 0;
    std::array<std::uint32_t,3> loop_translation{};
    std::array<std::uint32_t,4> loop_rotation{};
    bool channel_animation = false;
    std::vector<std::uint32_t> channel_weights;
    std::uint32_t frame_count = 0, bone_count = 0;

    bool Load(const std::vector<std::uint8_t>& bytes, std::string& error);
    SampleWords Sample(std::uint32_t frame, std::uint32_t bone) const;
private:
    // One word for a constant track; otherwise one original word per frame.
    std::vector<std::vector<std::uint32_t>> tracks_;
};
}
