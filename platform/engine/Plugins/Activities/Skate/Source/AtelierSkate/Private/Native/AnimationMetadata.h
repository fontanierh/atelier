// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace atelier::skate
{
struct AnimationBankSource
{
    std::string source_bank, source_sha256;
    std::uint64_t source_bytes = 0;
};
struct ClipAttributeMetadata
{
    std::string name;
    std::uint8_t type_id = 0;
    std::uint32_t begin_bits = 0, end_bits = 0;
    std::vector<std::uint32_t> payload_words;
    std::uint64_t source_offset = 0;
};
struct ClipMetadata
{
    std::string name;
    std::uint64_t source_offset = 0;
    std::uint32_t fps_bits = 0, frames_bits = 0, base_speed_bits = 0, flags_word = 0;
    std::vector<ClipAttributeMetadata> attributes;
};
struct PhaseBlendMetadata
{
    std::string name;
    std::uint64_t source_offset = 0;
    std::string parameter;
    std::vector<std::string> children;
};
struct BlendSimplexMetadata
{
    std::vector<std::uint32_t> children;
    std::vector<std::vector<std::uint32_t>> vertex_bits, normal_bits;
    std::vector<std::uint32_t> scale_bits;
};
struct BlendSpaceMetadata
{
    std::string name;
    std::uint64_t source_offset = 0;
    std::vector<std::string> parameters, children;
    std::vector<BlendSimplexMetadata> simplexes;
};
struct SelectorMetadata
{
    std::string name;
    std::uint64_t source_offset = 0;
    std::string parameter, default_child;
    std::vector<std::string> children, values;
};
struct SelectionParameterMetadata
{
    std::string name;
    std::uint32_t mode = 0, weight_bits = 0, minimum_bits = 0, maximum_bits = 0;
};
struct SelectionCandidateMetadata
{
    std::string child;
    std::vector<std::uint32_t> value_bits;
};
struct SelectionSpaceMetadata
{
    std::string name;
    std::uint64_t source_offset = 0;
    std::vector<SelectionParameterMetadata> parameters;
    std::vector<SelectionCandidateMetadata> candidates;
};
struct UnsupportedAnimationTree
{
    std::string name;
    std::uint64_t source_offset = 0;
    std::uint32_t type_id = 0;
};
enum class AnimationTreeKind : std::uint32_t { Clip=2, BlendSpace=6, PhaseBlend=7, Selector=8, SelectionSpace=11 };
struct AnimationTreeMetadata
{
    AnimationTreeKind kind = AnimationTreeKind::Clip;
    const ClipMetadata* clip = nullptr;
    const BlendSpaceMetadata* blend_space = nullptr;
    const PhaseBlendMetadata* phase_blend = nullptr;
    const SelectorMetadata* selector = nullptr;
    const SelectionSpaceMetadata* selection_space = nullptr;
};
class AnimationMetadata
{
public:
    // These arenas retain every record in authored order, including duplicates.
    std::vector<ClipMetadata> clips;
    std::vector<PhaseBlendMetadata> phase_blends;
    std::vector<BlendSpaceMetadata> blend_spaces;
    std::vector<SelectorMetadata> selectors;
    std::vector<SelectionSpaceMetadata> selection_spaces;
    std::vector<UnsupportedAnimationTree> unsupported_trees;
    std::string source_bank, source_sha256;

    bool Load(const std::vector<std::uint8_t>& bytes, std::string& error);
    // Validate typed records and reconstruct bank/name provenance without serializing a byte payload.
    bool InitializeBank(AnimationBankSource source, std::string& error);
    // Reject namespace collisions before mutation, preserving primary identity.
    bool Merge(const AnimationMetadata& other, std::string& error);
    const std::vector<AnimationBankSource>& Sources() const { return sources_; }
    const AnimationBankSource* SourceFor(std::string_view name) const;
    const ClipMetadata* Clip(std::string_view name, std::string& error) const;
    bool Tree(std::string_view name, AnimationTreeMetadata& output, std::string& error) const;
    std::size_t ClipCount() const { return clips.size(); }
private:
    std::vector<AnimationBankSource> sources_;
    std::map<std::string,std::size_t> origins_;
};
}
