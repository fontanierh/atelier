// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationTrees.h"
#include <filesystem>
#include <shared_mutex>

namespace atelier::skate
{
struct AnimationLoopTransform {Quat rotation{0,0,0,1};std::array<float,3> translation{};};
Sqt AnimationTrajectoryDelta(Sqt current,Sqt previous,std::optional<AnimationLoopTransform> loop);
Sqt AddAnimationPose(Sqt a,Sqt b,bool motion_is_a);
bool MirrorAnimationPose(std::vector<Sqt>& pose,const std::vector<std::int32_t>& parents,const std::vector<std::int32_t>& partners,std::uint32_t trajectory_mode,std::string& error);
// Registration preserves stock bank/name replacement and ambiguity semantics.
// Clips own verified native tracks; no original compressed-bank reader is used.
struct AnimationPoseFrames
{
    AnimationRig rig;
    std::map<std::string,std::shared_ptr<const AnimationClipSamples>> clips;
    bool RegisterClip(std::shared_ptr<const AnimationClipSamples> clip,std::string& error);
    const AnimationClipSamples* Clip(std::string_view name,std::string& error) const;
    const AnimationReferencePose* NamedPose(std::string_view name,std::string& error) const;
};
struct AuthoredAnimationClip {float fps=0;std::vector<std::vector<Mat4>> frames;};
struct AuthoredAnimationDocument
{
    std::uint32_t version=0;
    std::vector<std::string> bone_names;
    std::map<std::string,AuthoredAnimationClip> clips;
};
bool ParseAuthoredAnimationDocument(std::string_view text,AuthoredAnimationDocument& output,std::string& error);
struct AnimationClipReplacement
{
    std::shared_ptr<const AnimationClipSamples> stock;
    std::vector<std::vector<SampleWords>> frames;
};
using AnimationClipReplacements=std::map<std::string,AnimationClipReplacement>;
bool BakeAuthoredAnimationClips(const AuthoredAnimationDocument& document,const AnimationPoseFrames& frames,AnimationClipReplacements& output,std::string& error);
// Executes production PoseCommand stacks and initial-bank reference poses.
// Mod replacement ownership is ordered by owner string, as in the stock host.
class AnimationPoseEvaluator
{
public:
    explicit AnimationPoseEvaluator(AnimationPoseFrames frames):frames(std::move(frames)) {}
    AnimationPoseFrames frames;
    bool LoadAuthoredClips(const std::filesystem::path& asset_root,std::string& error);
    bool SetAuthoredClips(std::string_view text,std::string& error);
    bool InstallModClips(std::string_view owner,std::string_view text,std::string& error);
    void RemoveModClips(std::string_view owner);
    void ClearModClips();
    bool Evaluate(const std::vector<PoseCommand>& commands,std::vector<Sqt>& output,std::string& error) const;
    bool Hierarchy(const std::vector<Sqt>& pose,std::vector<Mat4>& output,std::string& error) const;
private:
    AnimationClipReplacements authored_;
    mutable std::shared_mutex mods_mutex_;
    std::map<std::string,AnimationClipReplacements> mod_clips_;
};
}
