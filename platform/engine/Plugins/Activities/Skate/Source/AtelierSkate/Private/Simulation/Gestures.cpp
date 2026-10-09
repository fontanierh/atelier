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
    authored_count_ = patterns_.size();
}

void GestureRecognizer::ScaleRadius(float scale)
{
    radius_scale_ = scale;
    for (std::size_t i = 0; i < patterns_.size(); ++i) patterns_[i].tolerance_squared = authored_tolerance_[i] * (scale * scale);
}

void GestureRecognizer::SetExtraPatterns(std::vector<GesturePattern> extra)
{
    assert(ValidGesturePatterns(extra));
    patterns_.resize(authored_count_);
    authored_tolerance_.resize(authored_count_);
    for (auto& pattern : extra)
    {
        authored_tolerance_.push_back(pattern.tolerance_squared);
        patterns_.push_back(std::move(pattern));
    }
    ScaleRadius(radius_scale_);
    nodes_.assign(patterns_.size(), Node{});
    if (held_ && *held_ >= patterns_.size()) held_.reset();
}

void GestureRecognizer::Node::Tick(const GesturePattern& pattern, StickPoint sample, std::uint8_t maximum_misses,
    std::uint8_t miss_mask, std::uint8_t weight)
{
    if (!active)
    {
        const float current = DistanceSquared(pattern.points[0], sample);
        if (current <= pattern.tolerance_squared)
        {
            *this = Node{};
            active = true;
            next = 1;
            // A whole tick read once enters at 0, so that Ticks counts its ticks as at 60 Hz.
            elapsed = weight == 2 ? 0 : 1;
            distance = current;
        }
    }
    else if (!complete)
    {
        const float current = DistanceSquared(pattern.points[next], sample);
        if (current <= pattern.tolerance_squared)
        {
            distance += current;
            elapsed = (elapsed + weight) & 0x3ff;
            if (next + 1 == pattern.points.size()) complete = true;
            else { ++next; misses = 0; }
        }
        else
        {
            if (next != 1 || DistanceSquared(pattern.points[0], sample) > pattern.tolerance_squared)
            {
                elapsed = (elapsed + weight) & 0x3ff;
                misses = static_cast<std::uint8_t>((misses + weight) & miss_mask);
            }
            if (misses > maximum_misses) *this = Node{};
        }
    }
}

float GestureRecognizer::Node::Score(std::size_t points, float elapsed_ticks) const
{
    const float count = static_cast<float>(points);
    const float mean = std::fmin(std::fmax(distance, .15f) / count, .15f);
    return (count * count * count * count) / (mean * elapsed_ticks);
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

namespace
{
// A node's elapsed is 1 plus the samples from the last one in the first circle to the one completing the pattern. At
// 60 Hz each end of that span falls on average half a tick past the stick's own moment, a whole tick in all; at 120 Hz
// a quarter tick, half a tick in all. elapsed/2 + 1 is then the 60 Hz count a flick of that duration has on average,
// and, for a whole tick read once (weight 2, entering at 0), exactly the 60 Hz count.
float Ticks(std::uint16_t elapsed, GestureSettings settings)
{
    return settings.samples_per_tick == 2 ? static_cast<float>(elapsed) / 2.f + 1.f : static_cast<float>(elapsed);
}
}

bool GestureRecognizer::Advance(StickPoint sample, GestureSettings settings, std::uint8_t weight)
{
    if (refractory_)
    {
        std::fill(nodes_.begin(), nodes_.end(), Node{});
        refractory_ = static_cast<std::uint8_t>(refractory_ > weight ? refractory_ - weight : 0);
        return false;
    }
    if (!has_previous_sample_)
    {
        has_previous_sample_ = true;
        return false;
    }
    const std::uint8_t miss_mask = settings.samples_per_tick == 2 ? 0x7f : 0x3f;
    for (std::size_t i = 0; i < nodes_.size(); ++i)
        nodes_[i].Tick(patterns_[i], sample, settings.maximum_misses, miss_mask, weight);
    return true;
}

float GestureRecognizer::Score(std::size_t node, GestureSettings settings) const
{
    return nodes_[node].Score(patterns_[node].points.size(), Ticks(nodes_[node].elapsed, settings));
}

std::optional<std::size_t> GestureRecognizer::Best(GestureSettings settings) const
{
    std::optional<std::size_t> best;
    for (std::size_t i = 0; i < nodes_.size(); ++i)
        if (nodes_[i].complete && (!best || Score(i, settings) > Score(*best, settings))) best = i;
    return best;
}

std::optional<GestureRecognition> GestureRecognizer::Sample(StickPoint sample, GestureSettings settings)
{
    if (!Advance(sample, settings)) return std::nullopt;
    const auto best = Best(settings);
    if (!best) return std::nullopt;
    return Recognize(*best, settings);
}

std::optional<GestureRecognition> GestureRecognizer::SampleTick(std::optional<StickPoint> half, StickPoint now,
    GestureSettings settings)
{
    if (!half)
    {
        if (!Advance(now, settings, 2)) return std::nullopt;
        const auto best = Best(settings);
        if (!best) return std::nullopt;
        return Recognize(*best, settings);
    }
    if (!Advance(*half, settings)) return Sample(now, settings);
    const auto first = Best(settings);
    if (!first) return Sample(now, settings);
    // The half sample completed a pattern. Read on to the tick's end as if it had not; a different pattern completed
    // there with a better score wins, as on one sample. Otherwise the half sample's stands and the end is the pause.
    const auto at_half = nodes_;
    Advance(now, settings);
    if (const auto second = Best(settings); second && *second != *first && Score(*second, settings) > Score(*first, settings))
        return Recognize(*second, settings);
    nodes_ = at_half;
    const auto recognition = Recognize(*first, settings);
    Advance(now, settings);
    return recognition;
}

GestureRecognition GestureRecognizer::Recognize(std::size_t best, GestureSettings settings)
{
    const Node& node = nodes_[best];
    const float elapsed = Ticks(node.elapsed, settings);
    const float ratio = elapsed / static_cast<float>(patterns_[best].points.size());
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
    refractory_ = settings.samples_per_tick == 2 ? 2 : 1;
    held_ = best;
    return GestureRecognition{best, strength, node.distance, elapsed};
}
}
