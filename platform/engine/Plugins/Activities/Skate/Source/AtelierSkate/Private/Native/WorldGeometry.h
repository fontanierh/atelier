// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GeometrySweep.h"
#include "GeometryTypes.h"
#include <vector>

namespace atelier::skate
{
struct Bounds
{
    Vec3 min{}, max{};
    Bounds Expanded(float padding) const;
    bool Overlaps(Bounds other) const;
    bool Contains(Vec3 point) const;
    bool Valid() const;
    static std::optional<Bounds> FromPoints(const Vec3* points,std::size_t count);
    template<std::size_t N> static std::optional<Bounds> FromPoints(const std::array<Vec3,N>& points)
    { return FromPoints(points.data(),points.size()); }
    static std::optional<Bounds> FromPoints(const std::vector<Vec3>& points)
    { return FromPoints(points.data(),points.size()); }
};
enum class QueryPool { Ground, Island, Conditional };
struct IndexRange { std::size_t start=0,end=0; };
struct EdgeSegment { Vec3 start{},end{}; Bounds local_bounds{}; };
struct QueryMesh
{
    IndexRange triangle_range{};
    AffineTransform local_to_world{},world_to_local{};
    Bounds local_bounds{};
    std::int32_t matching_group=0;
    std::uint32_t rejection_flags=0,geometry=0;
    QueryPool pool=QueryPool::Ground;
};
struct WorldTriangle
{
    Triangle triangle{};
    ContactMaterial material{};
    std::uint32_t tag=0;
    static std::optional<WorldTriangle> FromVertices(const std::array<Vec3,3>& vertices,
        ContactMaterial material,std::uint32_t tag,std::uint32_t flags,
        const std::array<float,3>& edge_cosines,float fatness);
};
struct QueryMetadata
{
    std::vector<std::uint16_t> packed_surfaces;
    std::vector<QueryMesh> meshes;
    std::vector<EdgeSegment> static_edges;
    std::uint32_t island_flags=0;
    // Null means success; errors use the reference's exact diagnostic strings.
    const char* Validate(const std::vector<WorldTriangle>& triangles) const;
};
struct WorldLineHit { TriangleLineHit geometry{}; std::uint32_t tag=0; };
struct WorldLineQueryResult { std::optional<WorldLineHit> hit; const char* error=nullptr; };
struct MeshIndicesResult { std::vector<std::size_t> indices; const char* error=nullptr; };

Triangle TriangleFromVolume(const std::array<Vec3,3>& vertices,float fatness,
                            const std::array<float,3>& edge_cosines,std::uint32_t volume_flags);
std::optional<Bounds> PrimitiveBounds(const ContactPrimitive& primitive);
Bounds ConservativeBounds(Bounds bounds,float padding);

// Static world storage and traversal only. Candidate and equal-hit order is
// authored triangle order, independent of the hierarchy's partition order.
class WorldGeometry
{
public:
    explicit WorldGeometry(std::vector<WorldTriangle> triangles);
    static std::optional<WorldGeometry> WithQueryMetadata(std::vector<WorldTriangle> triangles,
                                                         QueryMetadata metadata,const char*& error);
    const std::vector<WorldTriangle>& Triangles() const { return triangles_; }
    const std::vector<Bounds>& TriangleBounds() const { return triangle_bounds_; }
    float MaximumFatness() const { return maximum_fatness_; }
    const QueryMetadata* Metadata(const char*& error) const;
    std::vector<IndexRange> CandidateRanges(std::optional<Bounds> bounds) const;
    std::optional<Bounds> LineCandidateBounds(Vec3 start,Vec3 end,float radius) const;
    std::vector<std::size_t> LineCandidates(Vec3 start,Vec3 end,float radius) const;
    MeshIndicesResult CandidateMeshIndices(std::optional<Bounds> bounds) const;
    WorldLineQueryResult QueryThinLine(Vec3 start,Vec3 end) const;
    WorldLineQueryResult QuerySweptLine(Vec3 start,Vec3 end,float radius) const;
private:
    struct Node
    {
        Bounds bounds{};
        std::optional<std::array<std::size_t,2>> children;
        IndexRange range{};
    };
    std::size_t BuildIndex(IndexRange range);
    std::vector<std::size_t> QueryIndex(Bounds bounds) const;
    std::vector<WorldTriangle> triangles_;
    std::vector<Bounds> triangle_bounds_;
    std::optional<QueryMetadata> metadata_;
    std::vector<Node> nodes_;
    std::vector<std::size_t> order_;
    float maximum_fatness_=0, maximum_triangle_margin_=0;
};
}
