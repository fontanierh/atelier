// SPDX-License-Identifier: Apache-2.0
#include "AnimationSamples.h"
#include "DataReader.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <set>
#include <utility>

namespace atelier::skate
{
namespace
{
std::uint64_t Wide(detail::DataReader& input)
{
    const auto low = input.Word(), high = input.Word();
    return std::uint64_t(low) | (std::uint64_t(high)<<32);
}
bool Finite(std::uint32_t bits)
{
    float value; std::memcpy(&value,&bits,4); return std::isfinite(value);
}
std::string AnimationName(std::string_view name)
{
    std::string result(name);
    for (auto& c : result) if (c >= 'a' && c <= 'z') c = char(c-'a'+'A');
    return result;
}
}
bool AnimationRig::Load(const std::vector<std::uint8_t>& bytes, std::string& error)
{
    auto fail = [&]() { error = "Invalid native animation rig"; return false; };
    if (bytes.size() < 20 || std::memcmp(bytes.data(),"ATSKEL01",8) != 0) return fail();
    detail::DataReader input{bytes}; AnimationRig result;
    const auto count = input.Word(), trajectory = input.Word();
    if (count == 0 || count > 255 || trajectory > 1 || count > input.Remaining()/12) return fail();
    result.has_trajectory = trajectory != 0;
    std::set<std::string> names;
    for (std::uint32_t i = 0; i < count; ++i)
    {
        AnimationBone bone; bone.name = input.String();
        bone.parent = std::int32_t(input.Word()); bone.mirror = std::int32_t(input.Word());
        if (!input.ok || bone.parent < -1 || bone.parent >= std::int32_t(i) || bone.mirror < -1 ||
            bone.mirror >= std::int32_t(count) || bone.name.empty() || !names.insert(bone.name).second) return fail();
        result.bones.push_back(std::move(bone));
    }
    for (std::uint32_t i = 0; i < count; ++i)
        if (result.bones[i].mirror >= 0 && result.bones[result.bones[i].mirror].mirror != std::int32_t(i)) return fail();
    const auto poses = input.Word();
    if (!input.ok || poses > input.Remaining()/20) return fail();
    for (std::uint32_t i = 0; i < poses; ++i)
    {
        AnimationReferencePose pose;
        pose.bank = input.Word(); pose.name = input.String(); pose.record = Wide(input);
        const auto samples = input.Word();
        if (!input.ok || pose.name.empty() || samples != count || samples > input.Remaining()/40) return fail();
        for (std::uint32_t b = 0; b < samples; ++b)
        {
            SampleWords sample{};
            for (auto& word : sample) { word = input.Word(); if (!Finite(word)) return fail(); }
            pose.samples.push_back(sample);
        }
        if (!result.records_.emplace(std::make_pair(pose.bank,pose.record),result.poses.size()).second) return fail();
        // Original banks replace earlier same-name records in file order.
        result.names_[{pose.bank,AnimationName(pose.name)}] = result.poses.size();
        result.poses.push_back(std::move(pose));
    }
    if (!input.ok || input.Remaining() != 0) return fail();
    *this = std::move(result); error.clear(); return true;
}
const AnimationReferencePose* AnimationRig::NamedPose(std::uint32_t bank, std::string_view name) const
{
    const auto found = names_.find({bank,AnimationName(name)});
    return found == names_.end() ? nullptr : &poses[found->second];
}
const AnimationReferencePose* AnimationRig::Pose(std::uint32_t bank, std::uint64_t record) const
{
    const auto found = records_.find({bank,record});
    return found == records_.end() ? nullptr : &poses[found->second];
}

bool AnimationClipSamples::Load(const std::vector<std::uint8_t>& bytes, std::string& error)
{
    auto fail = [&]() { error = "Invalid native animation samples"; return false; };
    if (bytes.size() < 8 || std::memcmp(bytes.data(),"ATCLIP01",8) != 0) return fail();
    detail::DataReader input{bytes}; AnimationClipSamples result;
    result.name = input.String(); result.bank = input.Word(); result.record = Wide(input); result.fps_bits = input.Word();
    for (auto& value : result.loop_translation) { value = input.Word(); if (!Finite(value)) return fail(); }
    for (auto& value : result.loop_rotation) { value = input.Word(); if (!Finite(value)) return fail(); }
    const auto channel = input.Word(), weights = input.Word();
    float fps; std::memcpy(&fps,&result.fps_bits,4);
    if (!input.ok || result.name.empty() || !std::isfinite(fps) || fps <= 0 || channel > 1 ||
        weights == 0 || weights > 255 || weights > input.Remaining()/4) return fail();
    result.channel_animation = channel != 0;
    for (std::uint32_t i = 0; i < weights; ++i)
    {
        const auto weight = input.Word(); if (!Finite(weight)) return fail();
        result.channel_weights.push_back(weight);
    }
    result.frame_count = input.Word(); result.bone_count = input.Word();
    if (!input.ok || result.frame_count == 0 || result.bone_count != weights || weights*10 > input.Remaining()/8) return fail();
    for (std::uint32_t i = 0; i < weights*10; ++i)
    {
        const auto count = input.Word();
        if (!input.ok || (count != 1 && count != result.frame_count) || count > input.Remaining()/4) return fail();
        std::vector<std::uint32_t> track;
        for (std::uint32_t f = 0; f < count; ++f)
        {
            const auto value = input.Word(); if (!Finite(value)) return fail();
            track.push_back(value);
        }
        result.tracks_.push_back(std::move(track));
    }
    if (!input.ok || input.Remaining() != 0) return fail();
    *this = std::move(result); error.clear(); return true;
}
SampleWords AnimationClipSamples::Sample(std::uint32_t frame, std::uint32_t bone) const
{
    assert(frame < frame_count && bone < bone_count);
    SampleWords result{};
    for (std::size_t i = 0; i < result.size(); ++i)
    {
        const auto& track = tracks_[bone*10+i];
        result[i] = track[track.size() == 1 ? 0 : frame];
    }
    return result;
}
}
