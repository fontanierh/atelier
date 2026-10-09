// The Flick-It gesture recognizer.
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
    // The player's flick pace (FeelTuning::flick_pace): the flick speed a full pop needs. The ticks per point that
    // still pop at full strength, and those past which a flick pops weakest, are divided by it, so below 1 a gentler
    // flick pops fully.
    float pace = 1.f;
    // Stick samples per simulation tick: 1 is the authored 60 Hz reading; 2 reads the stick at 120 Hz
    // (FeelTuning::flick_120hz). Every count in samples (maximum_misses here, the elapsed time, the pause after a
    // recognition) stands for the same time at either rate: maximum_misses is already given in samples, and elapsed is
    // reported and scored in ticks.
    std::uint8_t samples_per_tick = 1;
};

struct GestureRecognition
{
    std::size_t pattern = 0;
    float strength = 0;
    float distance = 0;
    float elapsed = 0;   // in ticks at either sampling rate
};

// This is the project format. Runtime code has no PAT parser.
bool LoadGestureData(const std::vector<std::uint8_t>& bytes, std::vector<GestureSet>& result, std::string& error);
bool ValidGesturePatterns(const std::vector<GesturePattern>& patterns);

class GestureRecognizer
{
public:
    explicit GestureRecognizer(std::vector<GesturePattern> patterns);
    const std::vector<GesturePattern>& Patterns() const { return patterns_; }
    std::optional<std::size_t> Held(StickPoint sample);
    std::optional<GestureRecognition> Sample(StickPoint sample, GestureSettings settings);
    // One tick read at 120 Hz (settings.samples_per_tick 2): the stick half a tick before its end, then at its end.
    // Patterns completed within the tick compete on score as they do on one 60 Hz sample: one whose last circle the
    // half sample reaches first does not pre-empt a better one that the tick's end completes. Without `half` (no
    // reading between frames) the tick's end counts as both samples, and the flick reads exactly as at 60 Hz.
    std::optional<GestureRecognition> SampleTick(std::optional<StickPoint> half, StickPoint now, GestureSettings settings);
    // Every pattern's radius as authored times this (FeelTuning::flick_radius); 1 restores them.
    void ScaleRadius(float scale);
    // Patterns recognised beside the authored ones, appended after them so an authored pattern wins a tied score.
    // Replaces any earlier extras; an empty list restores the authored set.
    void SetExtraPatterns(std::vector<GesturePattern> extra);

private:
    struct Node
    {
        bool active = false;
        bool complete = false;
        std::size_t next = 0;
        std::uint16_t elapsed = 0;
        std::uint8_t misses = 0;
        float distance = 0;
        // miss_mask is the miss counter's wrap: the authored 6 bits at 60 Hz, 7 at 120 Hz (twice the samples). A
        // sample of weight 2 stands for two at 120 Hz (a whole tick read once).
        void Tick(const GesturePattern& pattern, StickPoint sample, std::uint8_t maximum_misses, std::uint8_t miss_mask,
            std::uint8_t weight);
        float Score(std::size_t count, float elapsed_ticks) const;
    };
    // Sample's steps: tick every node with a sample of `weight` samples (false when it is skipped: the first sample, or
    // the pause after a recognition),
    // the best complete node, its score, and its recognition (which starts the pause).
    bool Advance(StickPoint sample, GestureSettings settings, std::uint8_t weight = 1);
    std::optional<std::size_t> Best(GestureSettings settings) const;
    float Score(std::size_t node, GestureSettings settings) const;
    GestureRecognition Recognize(std::size_t node, GestureSettings settings);
    std::vector<GesturePattern> patterns_;
    std::vector<float> authored_tolerance_;
    std::size_t authored_count_ = 0;
    float radius_scale_ = 1.f;
    std::vector<Node> nodes_;
    bool has_previous_sample_ = false;
    // Samples still skipped after a recognition: one tick's worth (the authored one sample at 60 Hz, two at 120 Hz).
    std::uint8_t refractory_ = 0;
    std::optional<std::size_t> held_;
};
}
