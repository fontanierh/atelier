#include "GraphMotionSliding.h"
#include <cmath>
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
std::optional<float> Value(const IntentMap& values,std::string_view name)
{
    const auto found = values.Get(name); return found ? std::optional<float>(*found) : std::nullopt;
}
}
bool GraphMotionSlidingSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const auto scalar = [&](std::string_view name,float& target)
    {
        const auto field = data.Field("anim_motion","power_slide",name);
        if (!field || !field->Float()) { error = "Missing anim_motion/power_slide scalar "+std::string(name); return false; }
        target = *field->Float(); return true;
    };
    const auto curve = [&](std::string_view name,auto& target)
    {
        constexpr auto count = std::tuple_size<decltype(target.x)>::value;
        const auto field = data.Field("anim_motion","power_slide",name); const std::uint32_t* words = nullptr;
        if (!field || !field->Words(4+count*2,words)) { error = "Missing anim_motion/power_slide curve "+std::string(name); return false; }
        for (std::size_t i = 0; i < count; ++i) { target.x[i] = Float(words[4+i]); target.y[i] = Float(words[4+count+i]); }
        return true;
    };
    return scalar("slide_speed_threshold",speed_threshold) && scalar("well_into_slide_time",well_into_slide) &&
        curve("slide_speed_factor",speed_factor) && curve("not_sliding_time_thresh",time_threshold) &&
        curve("not_sliding_threshold",threshold) && curve("slide_speed_to_lean",speed_to_lean) &&
        curve("slide_phys_to_anim_spin",phys_to_anim_spin) && scalar("slide_smooth",smooth) &&
        scalar("slide_min_entry",minimum_entry) && scalar("slide_turn_value",turn);
}
void GraphMotionSlidingState::Update(const IntentMap& motion,std::uint32_t category,float speed,float direction,float dt,
    const GraphMotionSlidingSettings& s,SlideLatch& output)
{
    const auto right = Value(motion,"RightSlide"), left = Value(motion,"LeftSlide");
    const auto right_value = right.value_or(0), left_value = left.value_or(0); const auto ground = category == 1;
    if (ground && !was_ground)
    {
        not_sliding_time = 0; previous_right = right_value; previous_left = left_value;
        was_right_start = false; was_left_start = false;
    }
    was_ground = ground; if (!ground) return;
    const auto fast = speed > s.speed_threshold, right_start = motion.Contains("RightSlideStart");
    output.SetStart(true,fast && right_start && !was_right_start && previous_right < right_value);
    previous_right = right_value; was_right_start = right_start;
    const auto left_start = motion.Contains("LeftSlideStart");
    output.SetStart(false,fast && left_start && !was_left_start && previous_left > left_value);
    previous_left = left_value; was_left_start = left_start;
    const auto limit = s.time_threshold.Evaluate(direction), sliding = s.speed_factor.Evaluate(speed)*(1.0f-std::abs(direction));
    not_sliding_time = sliding >= s.threshold.Evaluate(direction) ? 0.0f : not_sliding_time+dt;
    const auto stop = not_sliding_time > limit;
    output.AdvanceElapsed(true,dt); output.AdvanceElapsed(false,dt);
    output.SetEnd(true,output.Elapsed(true) > s.well_into_slide && (!right || !fast || stop));
    output.SetEnd(false,output.Elapsed(false) > s.well_into_slide && (!left || !fast || stop));
}
float GraphMotionSlideDirection(Vec4 velocity,Vec4 z,bool flipped)
{
    const auto squared = Dot3(velocity,velocity); if (!(squared > Float(0x3a83126f))) return 1;
    if (flipped) for (auto& value : z) value = -value;
    auto root = 1.0f/std::sqrt(squared);
    for (unsigned i = 0; i < 2; ++i) root = std::fma(root*0.5f,std::fma(-squared,root*root,1.0f),root);
    const auto length = squared*root; auto inverse = 1.0f/length;
    for (unsigned i = 0; i < 2; ++i) inverse = std::fma(inverse,std::fma(-inverse,length,1.0f),inverse);
    for (auto& value : velocity) value *= inverse;
    return Dot3(velocity,z);
}
std::array<float,2> CreateGraphMotionSlide(const SlideLatch& latch,bool authored_right,std::optional<float> right_intent,
    std::optional<float> left_intent,const GraphMotionSlidingSettings& s)
{
    const auto right = authored_right != latch.CapturedFakie(); auto slide = (right ? right_intent : left_intent).value_or(0);
    if (!(latch.Elapsed(right) > s.well_into_slide))
    {
        if (right) slide = s.minimum_entry-slide >= 0 ? s.minimum_entry : slide;
        else { const auto minimum = -s.minimum_entry; slide = minimum-slide >= 0 ? slide : minimum; }
    }
    auto turn = right ? s.turn : -s.turn;
    if (latch.CapturedFakie())
    {
        turn = -turn; const auto negative = -slide, absolute = std::abs(negative), wrapped = absolute > 0.5f ? 1.0f-absolute : absolute;
        slide = negative >= 0 ? wrapped : -wrapped;
    }
    return {slide,turn};
}
float GraphMotionSlideDeceleration(float& previous,Vec4 velocity,const Mat4& ground,const GraphMotionSlidingSettings& s)
{
    Vec4 local{};
    for (unsigned lane = 0; lane < 4; ++lane)
    {
        const auto x = ground[lane][0]*velocity[0], y = std::fma(ground[lane][1],velocity[1],x);
        local[lane] = std::fma(ground[lane][2],velocity[2],y);
    }
    local[1] = 0; const auto squared = Dot3(local,local); float length = 0;
    if (squared != 0)
    {
        auto inverse = 1.0f/std::sqrt(squared);
        for (unsigned i = 0; i < 2; ++i) inverse = std::fma(inverse*0.5f,std::fma(-squared,inverse*inverse,1.0f),inverse);
        length = squared*inverse;
    }
    const auto target = s.speed_to_lean.Evaluate(length), retained = (1.0f-s.smooth)*previous;
    previous = std::fma(target,s.smooth,retained); return previous;
}
float GraphMotionSlideSpin(float direction,const GraphMotionSlidingSettings& s) { return -s.phys_to_anim_spin.Evaluate(direction); }
}
