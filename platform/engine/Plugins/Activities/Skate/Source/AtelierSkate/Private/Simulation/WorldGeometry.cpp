#include "WorldGeometry.h"
#include <algorithm>
#include <cstring>
#include <limits>
#include <numeric>
#include <type_traits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
bool Finite(Vec3 p) { return std::isfinite(p.x) && std::isfinite(p.y) && std::isfinite(p.z); }
bool Identity(const AffineTransform& transform)
{
    const std::array<std::array<float,3>,3> identity={{{1,0,0},{0,1,0},{0,0,1}}};
    return transform.basis.columns==identity && transform.translation.x==0.0f
        && transform.translation.y==0.0f && transform.translation.z==0.0f;
}
float ThinMargin()
{
    const std::uint32_t word=0x3727c5ac;
    float value; std::memcpy(&value,&word,sizeof(value)); return value;
}
float BoundsScale(Bounds bounds)
{
    float scale=1.0f;
    for (float value:{bounds.min.x,bounds.min.y,bounds.min.z,bounds.max.x,bounds.max.y,bounds.max.z})
        scale=VectorMax(scale,std::fabs(value));
    return scale;
}
std::uint32_t FloatOrder(float value)
{
    std::uint32_t word; std::memcpy(&word,&value,sizeof(word));
    return word&0x80000000u ? ~word : word^0x80000000u;
}
float Axis(Vec3 value,unsigned axis) { return axis==0 ? value.x : axis==1 ? value.y : value.z; }
}

Bounds Bounds::Expanded(float padding) const
{
    return {{min.x-padding,min.y-padding,min.z-padding},{max.x+padding,max.y+padding,max.z+padding}};
}
bool Bounds::Overlaps(Bounds other) const
{
    return !(max.x<other.min.x || min.x>other.max.x || max.y<other.min.y
        || min.y>other.max.y || max.z<other.min.z || min.z>other.max.z);
}
bool Bounds::Contains(Vec3 point) const
{
    return Finite(point) && point.x>=min.x && point.x<=max.x && point.y>=min.y
        && point.y<=max.y && point.z>=min.z && point.z<=max.z;
}
bool Bounds::Valid() const
{
    return Finite(min) && Finite(max) && min.x<=max.x && min.y<=max.y && min.z<=max.z;
}
std::optional<Bounds> Bounds::FromPoints(const Vec3* points,std::size_t count)
{
    if (!count || !Finite(points[0])) return std::nullopt;
    Bounds bounds{points[0],points[0]};
    for (std::size_t i=1;i<count;++i)
    {
        const Vec3 point=points[i];
        if (!Finite(point)) return std::nullopt;
        bounds.min={VectorMin(bounds.min.x,point.x),VectorMin(bounds.min.y,point.y),VectorMin(bounds.min.z,point.z)};
        bounds.max={VectorMax(bounds.max.x,point.x),VectorMax(bounds.max.y,point.y),VectorMax(bounds.max.z,point.z)};
    }
    return bounds;
}

Triangle TriangleFromVolume(const std::array<Vec3,3>& vertices,float fatness,
                            const std::array<float,3>& edge_cosines,std::uint32_t volume_flags)
{
    const Vec3 raw_normal=Cross3(Subtract(vertices[1],vertices[0]),Subtract(vertices[2],vertices[0]));
    const float squared=Dot3(raw_normal,raw_normal);
    const Vec3 normal=squared>std::ldexp(1.0f,-23) ? Scale(raw_normal,InverseLengthSquared(squared,1)) : raw_normal;
    const std::array<Vec3,3> raw_edges={Subtract(vertices[2],vertices[0]),Subtract(vertices[1],vertices[2]),
                                     Subtract(vertices[0],vertices[1])};
    Triangle result{vertices,{normal,{},volume_flags&~2u,edge_cosines},{},fatness};
    for (std::size_t i=0;i<3;++i)
    {
        const float inverse=InverseLengthSquared(Dot3(raw_edges[i],raw_edges[i]),1);
        result.feature.edges[i]=Scale(raw_edges[i],inverse);
        result.edge_lengths[i]=RefinedReciprocal(inverse,2);
    }
    return result;
}
std::optional<WorldTriangle> WorldTriangle::FromVertices(const std::array<Vec3,3>& vertices,
    ContactMaterial material,std::uint32_t tag,std::uint32_t flags,
    const std::array<float,3>& edge_cosines,float fatness)
{
    for (Vec3 point:vertices) if (!Finite(point)) return std::nullopt;
    const Triangle triangle=TriangleFromVolume(vertices,fatness,edge_cosines,flags);
    for (float length:triangle.edge_lengths) if (!std::isfinite(length) || length<=0.0f) return std::nullopt;
    const Vec3 normal=triangle.feature.normal;
    if (!Finite(normal) || (normal.x==0.0f && normal.y==0.0f && normal.z==0.0f)) return std::nullopt;
    return WorldTriangle{triangle,material,tag};
}
const char* QueryMetadata::Validate(const std::vector<WorldTriangle>& triangles) const
{
    if (packed_surfaces.size()!=triangles.size()) return "Query surface count must equal canonical triangle count";
    std::size_t next=0;
    for (const QueryMesh& mesh:meshes)
    {
        const IndexRange range=mesh.triangle_range;
        if (range.start!=next || range.end<=next || range.end>triangles.size())
            return "Query meshes must partition canonical triangles in supplied order";
        if (!Identity(mesh.local_to_world) || !Identity(mesh.world_to_local))
            return "BoardWorld static query meshes require identity transforms";
        if (!mesh.local_bounds.Valid()) return "Invalid query mesh bounds";
        for (std::size_t i=range.start;i<range.end;++i)
            for (Vec3 point:triangles[i].triangle.vertices)
                if (!mesh.local_bounds.Contains(point)) return "Query mesh bounds exclude canonical triangle geometry";
        next=range.end;
    }
    if (next!=triangles.size()) return "Query metadata leaves canonical triangles unassigned";
    for (const EdgeSegment& edge:static_edges)
        if (!edge.local_bounds.Valid() || !edge.local_bounds.Contains(edge.start) || !edge.local_bounds.Contains(edge.end))
            return "Invalid authored query edge";
    return nullptr;
}

std::optional<Bounds> PrimitiveBounds(const ContactPrimitive& primitive)
{
    return std::visit([](const auto& shape)->std::optional<Bounds>
    {
        using Shape=std::decay_t<decltype(shape)>;
        if constexpr (std::is_same_v<Shape,Triangle>)
        {
            if (!std::isfinite(shape.fatness)) return std::nullopt;
            const auto bounds=Bounds::FromPoints(shape.vertices);
            return bounds ? std::optional<Bounds>(bounds->Expanded(std::fabs(shape.fatness))) : std::nullopt;
        }
        else
        {
            if (!std::isfinite(shape.radius)) return std::nullopt;
            if constexpr (std::is_same_v<Shape,Sphere>)
            {
                const auto bounds=Bounds::FromPoints(&shape.center,1);
                return bounds ? std::optional<Bounds>(bounds->Expanded(std::fabs(shape.radius))) : std::nullopt;
            }
            else if constexpr (std::is_same_v<Shape,Capsule>)
            {
                const Vec3 offset=Scale(shape.axis,shape.half_length);
                const std::array<Vec3,2> points={Subtract(shape.center,offset),
                    Vec3{shape.center.x+offset.x,shape.center.y+offset.y,shape.center.z+offset.z}};
                const auto bounds=Bounds::FromPoints(points);
                return bounds ? std::optional<Bounds>(bounds->Expanded(std::fabs(shape.radius))) : std::nullopt;
            }
            else
            {
                const std::array<float,3> half={shape.half_extents.x,shape.half_extents.y,shape.half_extents.z};
                std::array<float,3> extent{};
                for (unsigned axis=0;axis<3;++axis)
                {
                    float sum=0.0f;
                    for (unsigned i=0;i<3;++i) sum+=std::fabs(half[i])*std::fabs(shape.basis.columns[i][axis]);
                    extent[axis]=std::fabs(shape.radius)+sum;
                }
                const std::array<Vec3,2> points={Vec3{shape.center.x-extent[0],shape.center.y-extent[1],shape.center.z-extent[2]},
                    Vec3{shape.center.x+extent[0],shape.center.y+extent[1],shape.center.z+extent[2]}};
                return Bounds::FromPoints(points);
            }
        }
    },primitive);
}
Bounds ConservativeBounds(Bounds bounds,float padding)
{
    return bounds.Expanded(padding+BoundsScale(bounds)*(8.0f*std::numeric_limits<float>::epsilon()));
}

WorldGeometry::WorldGeometry(std::vector<WorldTriangle> triangles):triangles_(std::move(triangles))
{
    triangle_bounds_.reserve(triangles_.size());
    const float infinity=std::numeric_limits<float>::infinity();
    for (const WorldTriangle& entry:triangles_)
    {
        const auto bounds=Bounds::FromPoints(entry.triangle.vertices);
        triangle_bounds_.push_back(bounds.value_or(Bounds{{-infinity,-infinity,-infinity},{infinity,infinity,infinity}}));
        const float fatness=entry.triangle.fatness;
        maximum_fatness_=VectorMax(maximum_fatness_,std::isfinite(fatness) && fatness>=0.0f ? fatness : infinity);
    }
    for (Bounds bounds:triangle_bounds_)
    {
        const float span=VectorMax(VectorMax(bounds.max.x-bounds.min.x,bounds.max.y-bounds.min.y),bounds.max.z-bounds.min.z);
        maximum_triangle_margin_=VectorMax(maximum_triangle_margin_,span*(2.0f*ThinMargin()));
    }
}
std::optional<WorldGeometry> WorldGeometry::WithQueryMetadata(std::vector<WorldTriangle> triangles,
                                                            QueryMetadata metadata,const char*& error)
{
    error=metadata.Validate(triangles);
    if (error) return std::nullopt;
    WorldGeometry world(std::move(triangles));
    world.metadata_=std::move(metadata);
    world.order_.resize(world.metadata_->meshes.size());
    std::iota(world.order_.begin(),world.order_.end(),std::size_t{0});
    if (!world.order_.empty()) world.BuildIndex({0,world.order_.size()});
    return world;
}
const QueryMetadata* WorldGeometry::Metadata(const char*& error) const
{
    error=metadata_ ? nullptr : "Canonical world has no authored query metadata";
    return metadata_ ? &*metadata_ : nullptr;
}
std::size_t WorldGeometry::BuildIndex(IndexRange range)
{
    const auto& meshes=metadata_->meshes;
    std::vector<Vec3> points;
    points.reserve((range.end-range.start)*2);
    for (std::size_t i=range.start;i<range.end;++i)
    {
        const Bounds bounds=meshes[order_[i]].local_bounds;
        points.push_back(bounds.min); points.push_back(bounds.max);
    }
    const Bounds bounds=*Bounds::FromPoints(points);
    const std::size_t id=nodes_.size();
    nodes_.push_back({bounds,std::nullopt,range});
    if (range.end-range.start>8)
    {
        const std::array<float,3> extent={bounds.max.x-bounds.min.x,bounds.max.y-bounds.min.y,bounds.max.z-bounds.min.z};
        unsigned axis=0;
        for (unsigned i=1;i<3;++i) if (FloatOrder(extent[i])>=FloatOrder(extent[axis])) axis=i;
        auto center=[&](std::size_t i)
        {
            const Bounds b=meshes[i].local_bounds;
            return Axis(b.min,axis)*0.5f+Axis(b.max,axis)*0.5f;
        };
        const std::size_t middle=range.start+(range.end-range.start)/2;
        std::nth_element(order_.begin()+range.start,order_.begin()+middle,order_.begin()+range.end,
            [&](std::size_t a,std::size_t b)
            {
                const auto left=FloatOrder(center(a)),right=FloatOrder(center(b));
                return left==right ? a<b : left<right;
            });
        const std::size_t left=BuildIndex({range.start,middle}),right=BuildIndex({middle,range.end});
        nodes_[id].children=std::array<std::size_t,2>{left,right};
    }
    return id;
}
std::vector<std::size_t> WorldGeometry::QueryIndex(Bounds bounds) const
{
    std::vector<std::size_t> result;
    if (nodes_.empty()) return result;
    std::vector<std::size_t> stack={0};
    while (!stack.empty())
    {
        const std::size_t id=stack.back(); stack.pop_back();
        const Node& node=nodes_[id];
        if (!node.bounds.Overlaps(bounds)) continue;
        if (node.children)
        {
            stack.push_back((*node.children)[1]); stack.push_back((*node.children)[0]);
        }
        else
            for (std::size_t i=node.range.start;i<node.range.end;++i)
                if (metadata_->meshes[order_[i]].local_bounds.Overlaps(bounds)) result.push_back(order_[i]);
    }
    std::sort(result.begin(),result.end());
    return result;
}
std::vector<IndexRange> WorldGeometry::CandidateRanges(std::optional<Bounds> bounds) const
{
    if (!metadata_ || !bounds || !bounds->Valid()) return {{0,triangles_.size()}};
    const Bounds expanded=bounds->Expanded((maximum_fatness_+maximum_triangle_margin_)
        +BoundsScale(*bounds)*(8.0f*std::numeric_limits<float>::epsilon()));
    std::vector<IndexRange> ranges;
    for (std::size_t mesh:QueryIndex(expanded)) ranges.push_back(metadata_->meshes[mesh].triangle_range);
    return ranges;
}
std::optional<Bounds> WorldGeometry::LineCandidateBounds(Vec3 start,Vec3 end,float radius) const
{
    if (!std::isfinite(radius) || radius<0.0f) return std::nullopt;
    const Vec3 direction=Subtract(end,start);
    const float span=VectorMax(VectorMax(std::fabs(direction.x),std::fabs(direction.y)),std::fabs(direction.z));
    const auto bounds=Bounds::FromPoints(std::array<Vec3,2>{start,end});
    if (!bounds) return std::nullopt;
    return ConservativeBounds(*bounds,((radius+maximum_fatness_)+maximum_triangle_margin_)+span*ThinMargin());
}
std::vector<std::size_t> WorldGeometry::LineCandidates(Vec3 start,Vec3 end,float radius) const
{
    const auto bounds=LineCandidateBounds(start,end,radius);
    std::vector<std::size_t> candidates;
    for (IndexRange range:CandidateRanges(bounds))
        for (std::size_t i=range.start;i<range.end;++i)
            if (!metadata_ || !bounds || triangle_bounds_[i].Overlaps(*bounds)) candidates.push_back(i);
    return candidates;
}
MeshIndicesResult WorldGeometry::CandidateMeshIndices(std::optional<Bounds> bounds) const
{
    const char* error;
    const QueryMetadata* metadata=Metadata(error);
    if (!metadata) return {{},error};
    if (!bounds || !bounds->Valid())
    {
        std::vector<std::size_t> indices(metadata->meshes.size());
        std::iota(indices.begin(),indices.end(),std::size_t{0}); return {std::move(indices),nullptr};
    }
    return {QueryIndex(ConservativeBounds(*bounds,maximum_fatness_+maximum_triangle_margin_)),nullptr};
}
WorldLineQueryResult WorldGeometry::QueryThinLine(Vec3 start,Vec3 end) const { return QuerySweptLine(start,end,0.0f); }
WorldLineQueryResult WorldGeometry::QuerySweptLine(Vec3 start,Vec3 end,float radius) const
{
    if (!std::isfinite(radius) || radius<0.0f) return {std::nullopt,"line query radius must be finite and nonnegative"};
    const Vec3 direction=Subtract(end,start);
    std::optional<WorldLineHit> nearest;
    for (std::size_t index:LineCandidates(start,end,radius))
    {
        TriangleLineHit geometry{};
        const WorldTriangle& entry=triangles_[index];
        if (TriangleSegment(geometry,start,direction,entry.triangle.vertices,radius,entry.triangle.fatness)
            && (!nearest || geometry.fraction<nearest->geometry.fraction)) nearest=WorldLineHit{geometry,entry.tag};
    }
    return {nearest,nullptr};
}
}
