#pragma once
#include "NativeMath.h"
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

namespace atelier::skate
{
struct OffboardGrabDescriptor {std::uint32_t kind,id;};
struct OffboardGrabGeometry
{
    std::uint32_t id;
    std::vector<Vec4> points,approach_vectors;
    std::uint32_t word_60;
};
// Geometry identity and every native word belong to the record, independently
// of the owner's completion/publication readiness.
struct OffboardGrabRecord
{
    std::array<std::uint32_t,72> words;
    std::shared_ptr<const OffboardGrabGeometry> geometry;
};
struct OffboardGrabQuery
{
    Vec4 position,sort_position;
    Mat4 bounds_frame;
    Vec4 bounds_extents;
    float margin,angle_a,angle_b;
    std::uint32_t mode;
    std::size_t capacity;
    std::uint32_t selection_flags_2948;
    std::int32_t matching_id_2952;
};
struct OffboardGrabLine
{
    Vec4 start,end;
    float radius;
    std::int32_t group;
    std::uint32_t reject_flags;
    std::uint8_t source_pool_mask;
    std::uint32_t selection_flags;
};
struct OffboardGrabHit {float fraction;std::optional<std::uint32_t> assembly;};

// Lossless retained PlayerGrabSpline storage. Scene execution, request binding,
// validation and candidate selection are separate producers still to be ported.
// Ground operates on this same cache; invalidation is not a query completion.
struct OffboardGrabCache
{
    std::vector<OffboardGrabQuery> queries;
    std::optional<std::vector<OffboardGrabRecord>> query_result;
    std::vector<OffboardGrabRecord> pending,validated;
    std::optional<std::vector<std::optional<OffboardGrabHit>>> validation;
    std::array<std::optional<OffboardGrabDescriptor>,2> requests;
    std::array<std::optional<OffboardGrabRecord>,2> data;
    std::array<bool,2> data_ready{};
    std::optional<std::array<OffboardGrabLine,5>> interactable_request;
    std::optional<std::optional<std::uint32_t>> interactable_result;
    bool interactable_latched=false;
    std::uint8_t flags_12836=0;
    Vec4 query_position{},validation_position{};
    void Invalidate();
    void EnterReset();
};
}
