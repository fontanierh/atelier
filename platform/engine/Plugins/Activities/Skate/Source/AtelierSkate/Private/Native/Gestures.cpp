// SPDX-License-Identifier: Apache-2.0
#include "Gestures.h"
#include "DataReader.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <utility>

// The source uses separate multiplies except for the explicit strength mul_add.
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(_MSC_VER)
#pragma fp_contract(off)
#endif

namespace atelier::skate
{
namespace
{
float DistanceSquared(StickPoint a, StickPoint b)
{
    const float x = a[0] - b[0];
    const float y = a[1] - b[1];
    return x * x + y * y;
}

}

bool ValidGesturePatterns(const std::vector<GesturePattern>& patterns)
{
    for (const auto& pattern : patterns)
    {
        if (pattern.points.size() < 2 || pattern.points.size() > 15 ||
            !std::isfinite(pattern.tolerance_squared) || pattern.tolerance_squared < 0) return false;
        for (const auto& point : pattern.points)
            if (!std::isfinite(point[0]) || !std::isfinite(point[1])) return false;
    }
    return true;
}

bool LoadGestureData(const std::vector<std::uint8_t>& bytes, std::vector<GestureSet>& result, std::string& error)
{
    auto fail = [&]() { error = "Invalid native gesture data"; return false; };
    if (bytes.size() < 12 || std::memcmp(bytes.data(), "ATGEST01", 8) != 0) return fail();
    detail::DataReader input{bytes};
    const auto set_count = input.Word();
    if (set_count > (bytes.size()-12)/12) return fail();
    std::vector<GestureSet> sets;
    for (std::uint32_t i = 0; i < set_count; ++i)
    {
        GestureSet set;
        set.name = input.String();
        set.stick = input.Word();
        const auto count = input.Word();
        if (!input.ok || set.stick > 1 || count > (bytes.size()-input.at)/12) return fail();
        for (std::uint32_t p = 0; p < count; ++p)
        {
            GesturePattern pattern;
            pattern.name = input.String();
            pattern.tolerance_squared = input.Float();
            const auto points = input.Word();
            if (!input.ok || points < 2 || points > 15 || points > (bytes.size()-input.at)/8) return fail();
            for (std::uint32_t point = 0; point < points; ++point)
                pattern.points.push_back({input.Float(), input.Float()});
            set.patterns.push_back(std::move(pattern));
        }
        if (!ValidGesturePatterns(set.patterns)) return fail();
        sets.push_back(std::move(set));
    }
    if (!input.ok || input.at != bytes.size()) return fail();
    result = std::move(sets);
    error.clear();
    return true;
}

GestureRecognizer::GestureRecognizer(std::vector<GesturePattern> patterns)
    : patterns_(std::move(patterns)), nodes_(patterns_.size())
{
    assert(ValidGesturePatterns(patterns_));
    for (const auto& pattern : patterns_) authored_tolerance_.push_back(pattern.tolerance_squared);
}

void GestureRecognizer::ScaleRadius(float scale)
{
    for (std::size_t i = 0; i < patterns_.size(); ++i) patterns_[i].tolerance_squared = authored_tolerance_[i] * (scale * scale);
}

void GestureRecognizer::Node::Tick(const GesturePattern& pattern, StickPoint sample, std::uint8_t maximum_misses)
{
    if (!active)
    {
        const float current = DistanceSquared(pattern.points[0], sample);
        if (current <= pattern.tolerance_squared)
        {
            *this = Node{};
            active = true;
            next = 1;
            elapsed = 1;
            distance = current;
        }
    }
    else if (!complete)
    {
        const float current = DistanceSquared(pattern.points[next], sample);
        if (current <= pattern.tolerance_squared)
        {
            distance += current;
            elapsed = (elapsed + 1) & 0x3ff;
            if (next + 1 == pattern.points.size()) complete = true;
            else { ++next; misses = 0; }
        }
        else
        {
            if (next != 1 || DistanceSquared(pattern.points[0], sample) > pattern.tolerance_squared)
            {
                elapsed = (elapsed + 1) & 0x3ff;
                misses = (misses + 1) & 0x3f;
            }
            if (misses > maximum_misses) *this = Node{};
        }
    }
}

float GestureRecognizer::Node::Score(std::size_t points) const
{
    const float count = static_cast<float>(points);
    const float mean = std::fmin(std::fmax(distance, .15f) / count, .15f);
    return (count * count * count * count) / (mean * static_cast<float>(elapsed));
}

std::optional<std::size_t> GestureRecognizer::Held(StickPoint sample)
{
    if (held_)
    {
        const auto& pattern = patterns_[*held_];
        if (DistanceSquared(pattern.points.back(), sample) > pattern.tolerance_squared) held_.reset();
    }
    return held_;
}

std::optional<GestureRecognition> GestureRecognizer::Sample(StickPoint sample, GestureSettings settings)
{
    if (refractory_)
    {
        std::fill(nodes_.begin(), nodes_.end(), Node{});
        refractory_ = false;
        return std::nullopt;
    }
    if (!has_previous_sample_)
    {
        has_previous_sample_ = true;
        return std::nullopt;
    }
    for (std::size_t i = 0; i < nodes_.size(); ++i) nodes_[i].Tick(patterns_[i], sample, settings.maximum_misses);
    std::optional<std::size_t> best;
    for (std::size_t i = 0; i < nodes_.size(); ++i)
    {
        if (nodes_[i].complete && (!best || nodes_[i].Score(patterns_[i].points.size()) >
            nodes_[*best].Score(patterns_[*best].points.size()))) best = i;
    }
    if (!best) return std::nullopt;
    const Node& node = nodes_[*best];
    const float ratio = static_cast<float>(node.elapsed) / static_cast<float>(patterns_[*best].points.size());
    const float low = (settings.difficulty == 2 ? 1.5f : 1.75f) / settings.pace;
    const float high = (settings.difficulty == 2 ? 3.f : 4.4f) / settings.pace;
    float strength;
    if (ratio <= low) strength = 1.f;
    else if (ratio >= high) strength = 0.f;
    else
    {
        const float slope = 1.f / (low - high);
        strength = std::fma(slope, ratio, -(slope * high));
    }
    refractory_ = true;
    held_ = best;
    return GestureRecognition{*best, strength, node.distance, static_cast<float>(node.elapsed)};
}
}
