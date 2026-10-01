// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerGrindSurface.h"
#include "WorldGeometry.h"
namespace atelier::skate
{
struct PlayerGrindPrimitive {Vec4 start,end;std::uint64_t owner;};
struct PlayerGrindPrimitiveMetadata {std::array<std::uint64_t,2> spline_guids;std::uint32_t segment_index,flags;};
struct PlayerGrindSourceIdentity
{
    std::string stream_file,asset_id;
    std::uint64_t section_index,section_offset;
};
struct PlayerGrindBounds
{
    std::array<float,3> min,max;
    PlayerGrindBounds IdentityTransformed() const;
    bool Overlaps(PlayerGrindBounds) const;
    PlayerGrindBounds Union(PlayerGrindBounds) const;
    PlayerGrindBounds Padded() const;
    PlayerGrindBounds Cube() const;
    PlayerGrindBounds Inner() const;
    PlayerGrindBounds Child(std::size_t) const;
    std::optional<std::pair<std::size_t,PlayerGrindBounds>> ContainingChild(PlayerGrindBounds) const;
    bool Movable(PlayerGrindBounds) const;
};
// The converter supplies all authored bounds and package section occurrences.
// Stock bounds are never reconstructed from primitive endpoints. The authored
// policy preserves the original explicit host-polyline branch independently.
struct PlayerGrindConvertedAsset
{
    PlayerGrindSourceIdentity source;
    std::vector<std::size_t> indices;
    bool identity_transform_bounds;
};
struct PlayerGrindConvertedData
{
    std::vector<PlayerGrindPrimitive> primitives;
    std::vector<PlayerGrindPrimitiveMetadata> metadata;
    std::vector<std::array<std::uint64_t,2>> rail_guids;
    std::vector<PlayerGrindBounds> authored_bounds;
    std::vector<std::uint64_t> source_rail_indices;
    std::vector<PlayerGrindConvertedAsset> assets;
};
class PlayerGrindOctree
{
public:
    static std::optional<PlayerGrindOctree> New(PlayerGrindBounds,std::vector<PlayerGrindBounds>,std::string& error);
    std::vector<std::size_t> Query(PlayerGrindBounds,std::size_t limit) const;
private:
    struct Bucket {std::vector<std::pair<std::size_t,bool>> entries;std::optional<std::size_t> child;};
    struct Node {PlayerGrindBounds bounds;std::vector<std::size_t> resident;std::array<Bucket,8> buckets;};
    std::vector<Node> nodes_;
    std::vector<PlayerGrindBounds> bounds_;
    std::size_t node_capacity_;
    void Insert(std::size_t);
    void Split(std::size_t parent,std::size_t slot,PlayerGrindBounds);
};
class PlayerGrindStaticProvider
{
public:
    static std::optional<PlayerGrindStaticProvider> FromConverted(PlayerGrindConvertedData,std::string& error);
    const std::vector<PlayerGrindPrimitive>& Primitives() const {return data_.primitives;}
    const PlayerGrindPrimitiveMetadata* Metadata(std::size_t) const;
    std::optional<std::array<std::uint64_t,2>> SplineGuids(std::uint64_t owner) const;
    const PlayerGrindSourceIdentity* Source(std::size_t primitive) const;
    std::optional<std::uint64_t> SourceRailIndex(std::size_t primitive) const;
    const PlayerGrindBounds* AuthoredBounds(std::size_t primitive) const;
    bool Query(std::array<float,3> min,std::array<float,3> max,std::vector<std::size_t>& result,std::string& error) const;
private:
    struct Asset {PlayerGrindBounds bounds;PlayerGrindOctree tree;};
    PlayerGrindConvertedData data_;
    std::vector<Asset> assets_;
    std::vector<std::size_t> source_for_primitive_;
};
struct PlayerGrindForceExitProbe {Vec4 start,end;};
struct PlayerGrindForceExitHit {Vec4 normal;};
bool PlayerGrindSurfaceProbe(const WorldGeometry&,std::array<std::uint32_t,2> actor,std::size_t index,
    PlayerGrindProbe,std::optional<PlayerGrindProbeHit>& result,std::string& error);
bool PlayerGrindForceExitLine(const WorldGeometry&,std::array<std::uint32_t,2> actor,
    PlayerGrindForceExitProbe,std::optional<PlayerGrindForceExitHit>& result,std::string& error);
}
