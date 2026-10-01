// SPDX-License-Identifier: Apache-2.0
// C++ port of the recovered gesture recognizer; see ThirdParty/skate-core-LICENSE.
#pragma once
#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace atelier::skate
{
using StickPoint = std::array<float, 2>;

struct GesturePattern
{
    std::string name;
    std::vector<StickPoint> points;
    float tolerance_squared = 0;
};

struct GestureSet
{
    std::string name;
    std::uint32_t stick = 0;
    std::vector<GesturePattern> patterns;
};

struct GestureSettings
{
    std::uint8_t maximum_misses = 0;
    std::uint32_t difficulty = 0;
};

struct GestureRecognition
{
    std::size_t pattern = 0;
    float strength = 0;
    float distance = 0;
    float elapsed = 0;
};

// This is the project-native format. Runtime code has no PAT parser.
bool LoadGestureData(const std::vector<std::uint8_t>& bytes, std::vector<GestureSet>& result, std::string& error);
bool ValidGesturePatterns(const std::vector<GesturePattern>& patterns);

class GestureRecognizer
{
public:
    explicit GestureRecognizer(std::vector<GesturePattern> patterns);
    const std::vector<GesturePattern>& Patterns() const { return patterns_; }
    std::optional<std::size_t> Held(StickPoint sample);
    std::optional<GestureRecognition> Sample(StickPoint sample, GestureSettings settings);

private:
    struct Node
    {
        bool active = false;
        bool complete = false;
        std::size_t next = 0;
        std::uint16_t elapsed = 0;
        std::uint8_t misses = 0;
        float distance = 0;
        void Tick(const GesturePattern& pattern, StickPoint sample, std::uint8_t maximum_misses);
        float Score(std::size_t count) const;
    };
    std::vector<GesturePattern> patterns_;
    std::vector<Node> nodes_;
    bool has_previous_sample_ = false;
    bool refractory_ = false;
    std::optional<std::size_t> held_;
};
}
