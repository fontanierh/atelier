#include "InputIntentions.h"
#include <algorithm>
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
std::uint32_t Bits(float value) { std::uint32_t bits; std::memcpy(&bits,&value,4); return bits; }
float Clamp(float value, float low, float high)
{
    value = low-value >= 0 ? low : value; return high-value >= 0 ? value : high;
}
void Bit(std::uint32_t& word, std::uint32_t mask, bool value) { word = (word&~mask)|(value ? mask : 0); }
float PlainDot(Vec4 a, Vec4 b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
Vec4 SafeUnit(Vec4 vector)
{
    const auto squared = PlainDot(vector,vector);
    auto inverse = ReciprocalSquareRootEstimate(squared);
    for (unsigned i = 0; i < 2; ++i) inverse = std::fma(inverse*0.5f,std::fma(-squared,inverse*inverse,1.0f),inverse);
    const auto length = squared == 0 ? 0.0f : squared*inverse;
    if (length > Float(0x358637bd)) { for (auto& v : vector) v *= inverse; return vector; }
    return {};
}
float RemapAngle(float x, float y, float magnitude)
{
    if (!(magnitude > Float(0x37800000))) return 0;
    const auto initial = ReciprocalEstimate(x);
    const auto reciprocal = std::fma(initial,std::fma(-initial,x,1.0f),initial);
    const auto basic = Atan(std::fma(y,reciprocal,0.0f));
    const auto sign = Bits(y)&0x80000000;
    const auto result = x < 0 ? Float(0x40490fdb|sign)+basic : basic;
    return x == 0 ? Float(0x3fc90fdb|sign) : result;
}
float Filter(std::array<float,9>& s, std::array<float,4> coefficients, float input)
{
    std::copy(coefficients.begin(),coefficients.end(),s.begin());
    const auto difference = input-s[4], input_difference = input-s[5], complement = 1.0f-s[3];
    s[5] = input;
    s[8] = std::fma(input_difference,s[3],s[8]*complement);
    s[6] = std::fma(difference,s[3],complement*s[6]);
    auto term = std::fma(s[8]-s[7],s[2],s[1]*s[6]);
    term = std::fma(difference,s[0],term);
    const auto result = term+s[4]; s[7] = result-s[4]; s[4] = result; return result;
}
}
SteeringIntentions ProduceSteering(std::array<float,2> left, std::uint32_t flags)
{
    const auto x = left[0], y = left[1], angle = LeftStickAngle(x,y), absolute = std::abs(angle);
    const auto length = x == 0 && y == 0 ? 0.0f : ControllerMagnitude(std::fma(y,y,x*x));
    const auto signed_length = x >= 0 ? length : -length;
    const auto turn = y > 0 ? absolute > Float(0x40433333) ? 0.0f : absolute > Float(0x40166666)
        ? ((Float(0x40433333)-absolute)*Float(0x3fb6db6d))*signed_length : signed_length : x;
    const auto active = length > Float(0x3f666666) && !(absolute > Float(0x3fb1eb85)) && !(absolute < Float(0x3f68f5c3));
    auto hard = (absolute-Float(0x3fb1eb85))*Float(0xc0055556);
    const auto minimum = Float(0x3a83126f);
    hard = hard-minimum >= 0 ? hard : minimum; hard = angle >= 0 ? hard : -hard;
    const bool allowed = (flags&1) == 0;
    return {turn != 0 && allowed ? std::optional<float>(turn) : std::nullopt,
        active && allowed ? std::optional<float>(hard) : std::nullopt,
        active && allowed ? std::optional<float>(std::abs(hard*Float(0x3f59999a))) : std::nullopt};
}
std::vector<ControllerIntent> ProduceRiding(const DerivedControllerInput& controller, std::uint32_t flags, PushPreferences preferences)
{
    const auto& w = controller.Words(); const auto previous = w[6], current = w[13];
    const std::array<float,2> left{Float(w[7]),Float(w[8])};
    const auto allowed = (flags&(1u<<11)) == 0;
    const auto held = [&](unsigned b) { return (current&(1u<<b)) != 0 && allowed; };
    const auto fresh = [&](unsigned b, unsigned t) { return held(b) && ((previous&(1u<<b)) == 0 || Float(w[t]) < 0.3f); };
    auto right = held(21), lp = held(23), nr = fresh(21,20), nl = fresh(23,22);
    const auto angle = LeftStickAngle(left[0],left[1]);
    const auto from_forward = angle >= 0 ? Float(0x40490fdb)-angle : -Float(0x40490fdb)-angle;
    const auto length = ControllerMagnitude(std::fma(left[1],left[1],left[0]*left[0]));
    if (preferences.automatic_push_enabled && allowed && !(right || lp || nr || nl) && std::abs(from_forward) < 0.6f && length > 0.8f)
    { if (preferences.automatic_push_right) { right = true; nr = true; } else { lp = true; nl = true; } }
    if ((flags&(1u<<6)) != 0 && (right || nr) && (lp || nl)) right = lp = nr = nl = false;
    std::vector<ControllerIntent> out;
    const auto emit = [&](std::string_view name, float value) { out.push_back({name,value}); };
    if ((current&(1u<<20)) != 0 && (flags&(1u<<7)) == 0) emit("Brake",1);
    if (nr || nl) emit("NewPush",1);
    if (right) { emit("RightPush",1); emit("Pushing",1); }
    if (lp) { emit("LeftPush",1); emit("Pushing",1); }
    if (left[0] != 0 && (flags&(1u<<1)) == 0) { emit("BodySpin",left[0]); emit("PhysBodySpin",left[0]); }
    if (left[0] != 0 && (flags&1) == 0) emit("KickTurn",left[0]);
    const auto steering = ProduceSteering(left,flags);
    if (steering.hard_turn_crouch) emit("HardTurnCrouch",*steering.hard_turn_crouch);
    if (steering.hard_turn) emit("HardTurn",*steering.hard_turn);
    const auto absolute = std::abs(angle), start = Float(0x3ff5c28f), end = Float(0x40166666);
    const auto stick_crouch = (absolute <= start ? 0.0f : absolute < end ? ((absolute-start)*Float(0x4014d655))*length : length)*0.0f;
    const auto lt = Float(w[11]), rt = Float(w[12]);
    if (absolute > start || lt > 0 || rt != 0)
    {
        const auto trigger = lt-rt >= -0.0f ? lt : rt;
        emit("Crouch",stick_crouch-trigger >= -0.0f ? stick_crouch : trigger);
    }
    if (steering.turn) emit("Turn",*steering.turn);
    if ((flags&(1u<<8)) == 0 && length > 0.89999998f)
    {
        constexpr auto scale = 0.28004956f; const auto half_pi = Float(0x3fc90fdb);
        if (angle > 0 && angle < 0.91000003f) emit("RightSlideStart",1);
        if (angle > -0.91000003f && angle < 0) emit("LeftSlideStart",1);
        if (angle > -2 && angle < half_pi) emit("LeftSlide",-((angle+2.0f)*scale));
        if (angle > -half_pi && angle < 2) emit("RightSlide",(2.0f-angle)*scale);
    }
    if ((current&(1u<<28)) != 0) emit("GrabWorld",1);
    return out;
}
std::vector<ControllerIntent> ProduceAnticipation(const DerivedControllerInput& c)
{
    const auto& w = c.Words(); const auto x = Float(w[9]), y = Float(w[10]);
    if (x == 0 && y == 0) return {};
    return {{"AnticMag",ControllerMagnitude(std::fma(x,x,y*y))},{"AnticAngle",LeftStickAngle(x,y)}};
}
std::vector<ControllerIntent> ProduceManual(const DerivedControllerInput& c, std::uint32_t flags)
{
    std::vector<ControllerIntent> out; if ((flags&(1u<<9)) != 0) return out;
    const auto& w = c.Words(); const auto x = Float(w[9]), y = Float(w[10]);
    const auto length = ControllerMagnitude(std::fma(x,x,y*y));
    if (y != 0) out.push_back({"Manual",y > 0 ? length : -length});
    const auto threshold = Float(0x3f666666);
    if (length > threshold) { const auto brake = (length-threshold)*Float(0x411ffffe); out.push_back({"ManualBrake",y > 0 ? brake : -brake}); }
    return out;
}
std::vector<ControllerIntent> ProduceTrick(const DerivedControllerInput& c)
{
    const auto& w = c.Words(); const auto lt = Float(w[11]), rt = Float(w[12]), x = Float(w[9]), y = Float(w[10]);
    std::vector<ControllerIntent> out; const auto emit = [&](std::string_view name,float value) { out.push_back({name,value}); };
    if (lt == 1) emit("LeftGroundGrab",1); if (lt > 0) emit("LeftAirGrab",1);
    if (rt == 1) emit("RightGroundGrab",1); if (rt > 0) emit("RightAirGrab",1);
    const auto before = w[6], now = w[13];
    if ((now&(1u<<20)) != 0) { emit("Dismount",1); if ((before&(1u<<20)) == 0) emit("NewDismount",1); }
    constexpr auto dark = (1u<<20)|(1u<<28);
    if ((now&dark) != 0) emit("DarkCatch",1);
    if ((now&dark) != 0 && (before&dark) == 0) emit("NewDarkCatch",1);
    const auto length = std::sqrt(std::fma(x,x,y*y));
    if (length > 0) { emit("BoardAdjustAngle",std::atan2(x,-y)); emit("BoardAdjustMag",length); }
    if (x != 0) emit("TweakX",x); if (y != 0) emit("TweakY",y);
    if ((now&(1u<<28)) != 0) emit("GrabWorld",1);
    if (x != 0) emit("HandPlantTweakX",x); if (y != 0) emit("HandPlantTweakY",y);
    for (auto pair : {std::pair<unsigned,std::string_view>{20,"HandPlantDismount"},{21,"HandPlantOneFootRight"},{23,"HandPlantOneFootLeft"}})
        if ((now&(1u<<pair.first)) != 0) emit(pair.second,1);
    return out;
}
std::vector<ControllerIntent> ProduceGrind(const DerivedControllerInput& c)
{
    const auto& w = c.Words(); const auto lx = Float(w[7]), rx = Float(w[9]), ry = Float(w[10]);
    const auto translation = Clamp(lx+rx,-1,1);
    std::vector<ControllerIntent> out;
    for (auto i : {ControllerIntent{"GrindBalanceX",-lx},{"PhysGrindTranslation",translation},{"PhysGrindStabilityNudge",lx},{"PhysGrindUpDown",ry}})
        if (i.value != 0) out.push_back(i);
    return out;
}
std::vector<ControllerIntent> ProduceWipeout(const DerivedControllerInput& c, std::uint32_t actor, std::uint32_t physical)
{
    const auto& w = c.Words(); const auto before = w[6], now = w[13];
    const auto axis = [&](unsigned slot) { return Float(w[slot]); };
    const auto rising = [&](unsigned bit) { return (before&(1u<<bit)) == 0 && (now&(1u<<bit)) != 0; };
    const auto edge = [&](unsigned p,unsigned n) { return axis(p) != 1 && axis(n) == 1; };
    std::vector<ControllerIntent> out; const auto emit = [&](std::string_view name,float value) { out.push_back({name,value}); };
    emit("WipeoutGestureX",(physical&0x80) != 0 ? axis(9) : 0.0f); emit("WipeoutGestureY",(physical&0x80) != 0 ? axis(10) : 0.0f);
    const auto x = (physical&0x100) != 0 ? axis(7) : 0.0f, y = (physical&0x100) != 0 ? axis(8) : 0.0f;
    if (x != 0) emit("WipeoutControlX",x); if (y != 0) emit("WipeoutControlY",y);
    if (rising(21) || rising(23)) emit("WipeOutRecover",1);
    if ((actor&0x40) == 0 && axis(11) == 1 && axis(12) == 1 && (now&0xc0000000) == 0xc0000000 && (edge(4,11) || edge(5,12) || rising(31) || rising(30))) emit("WipeOutRequest",1);
    if ((physical&0x40) != 0 && edge(5,12)) emit("WipeOutPushOff",1);
    return out;
}
std::vector<ControllerIntent> ProduceOffboardDiscrete(const DerivedControllerInput& c,std::uint32_t flags,bool air)
{
    const auto& w = c.Words(); const auto before = w[6], now = w[13];
    const auto axis = [&](unsigned slot) { return Float(w[slot]); };
    const auto held = [&](unsigned bit) { return (now&(1u<<bit)) != 0; };
    const auto rising = [&](unsigned bit) { return held(bit) && (before&(1u<<bit)) == 0; };
    std::vector<ControllerIntent> out; const auto emit = [&](std::string_view name,float value) { out.push_back({name,value}); };
    if (rising(23)) emit("OB_Jump",1);
    const auto x = axis(9), y = axis(10);
    if (x != 0) emit("OB_LookAtX",x); if (y != 0) emit("OB_LookAtY",y);
    const auto drop = axis(4) != 1 && axis(11) == 1, toss = axis(5) != 1 && axis(12) == 1;
    if (drop) emit("OB_DropBoard",1); if (toss) emit("OB_ThrowBoard",1); if (drop || toss) emit("OB_RetrieveBoard",1);
    if (held(28) || held(30)) emit("OB_DoAirBodyTweak",1);
    emit("OB_AirBodyTweakX",x); emit("OB_AirBodyTweakY",y);
    if (!air && !held(29) && held(22))
    {
        if ((rising(22) || !(axis(23) >= Float(0x3cf5c28f))) && (flags&(1u<<10)) == 0) emit("NewToggleOffBoardState",1);
        emit("ToggleOffBoardState",1);
    }
    if (!(axis(21) > 0) && axis(20) > 0) emit("OB_Sprint",1);
    return out;
}
std::array<ControllerIntent,4> ProduceOffboardAnalog(const DerivedControllerInput& c,OffboardAnalogObservation observation)
{
    const auto& w = c.Words(); const Vec4 stick{Float(w[7]),0,Float(w[8]),0};
    auto horizontal = observation.effective_skeleton_z; horizontal[1] = 0; const auto forward = SafeUnit(horizontal);
    float magnitude;
    if (observation.biped_correction)
    {
        const auto normal = *observation.biped_correction; auto negative = normal;
        for (auto& v : negative) v = Float(Bits(v)^0x80000000);
        const auto projection = PlainDot(stick,negative), coefficient = Clamp(projection,0,1);
        if (!(PlainDot(SafeUnit(stick),negative) <= Float(0x3f666666))) magnitude = 0;
        else { auto corrected = stick; for (unsigned i = 0; i < 4; ++i) corrected[i] = std::fma(normal[i],coefficient,stick[i]); magnitude = PlainDot(forward,corrected); }
    }
    else magnitude = PlainDot(forward,stick);
    return {{{"OB_Mag",magnitude},{"OB_BipedWorldZ",stick[2]},{"OB_BipedWorldX",stick[0]},{"OB_BipedStickMag",ControllerMagnitude(PlainDot(stick,stick))}}};
}
void BodyFlipState::Begin(BodyFlipSettings s) { gesture_time = s.gesture_window; takeoff_time = s.takeoff_window; }
std::optional<std::size_t> BodyFlipState::Update(std::array<bool,2> present,std::uint32_t category,float dt,BodyFlipSettings s)
{
    if (present[0] || present[1]) { gesture_time = 0; selected = present[0] ? 0 : 1; }
    else { const auto value = gesture_time+dt; gesture_time = value-s.gesture_window >= 0 ? s.gesture_window : value; }
    const auto gesture = gesture_time < s.gesture_window;
    if (category == 2) { const auto value = takeoff_time+dt; takeoff_time = value-s.takeoff_window >= 0 ? s.takeoff_window : value; }
    else takeoff_time = 0;
    const auto takeoff = !(takeoff_time <= 0) && takeoff_time < s.takeoff_window;
    return gesture && takeoff ? selected : std::nullopt;
}
Vec4 TurnRemap::Apply(std::array<float,2> input) const
{
    const auto pi = Float(0x40490fdb);
    const auto first_magnitude = ControllerMagnitude(input[0]*input[0]+input[1]*input[1]);
    const auto first_angle = RemapAngle(input[0],input[1],first_magnitude);
    const auto scaled = first_magnitude*magnitude.Evaluate(first_angle >= 0 ? first_angle : first_angle+pi);
    const auto x = Clamp(Cos(first_angle)*scaled,-1,1), y = Clamp(Sin(first_angle)*scaled,-1,1);
    const auto second_magnitude = ControllerMagnitude(x*x+y*y), second_angle = RemapAngle(x,y,second_magnitude);
    const auto mapped = angle.Evaluate(second_angle >= 0 ? second_angle : second_angle+pi);
    const auto result_angle = angle_offset+(second_angle >= 0 ? mapped : mapped+pi);
    return {Clamp(Cos(result_angle)*second_magnitude,-1,1),Clamp(Sin(result_angle)*second_magnitude,-1,1),0,0};
}
void TurnConditionerState::ResetHistory()
{
    history.fill(0); for (auto& f : filters) std::fill(f.begin()+4,f.end(),0);
}
std::array<float,8> UpdateTurnConditioner(TurnConditionerState& state, TurnConditionerInput in,const TurnConditionerSettings& s)
{
    const auto& p = s.parameters; const auto sign = in.animation_156 != 0 ? -1.0f : 1.0f;
    const auto scaled = in.bundle_32_field_264*sign;
    const auto speed_fraction = Clamp(in.body_160/p[11],0,1), other_fraction = Clamp((in.bundle_36_field_160/p[10])*sign,-1,1);
    const auto base = s.input_curve.Evaluate(speed_fraction)*scaled;
    const auto attenuated = std::fma(-(1.0f-p[8]),in.body_176,1.0f)*other_fraction;
    const auto target = std::fma(attenuated,p[9],(1.0f-p[9])*base);
    auto first = Filter(state.filters[0],s.filter_coefficients[0],target); first = std::abs(first) > Float(0x3c23d70a) ? first : 0.0f;
    auto second = Filter(state.filters[1],s.filter_coefficients[1],target); second = std::abs(second) > Float(0x3c23d70a) ? second : 0.0f;
    const auto third = Filter(state.filters[2],s.filter_coefficients[2],(target-second)/p[12]);
    auto movement = in.animation_152 != 0 ? scaled : 0.0f; auto difference = movement-state.history[0]; state.history[0] = movement;
    state.history[2] = std::fma(std::abs(difference),p[2],(1.0f-p[2])*state.history[2]);
    const auto ratio = state.history[2]/p[1], squared = ratio*ratio, bounded = squared-1.0f >= 0 ? 1.0f : squared;
    state.history[3] = Clamp(bounded,state.history[3]-p[0],state.history[3]+p[0]);
    auto quick = Clamp(s.quickness_curve.Evaluate(state.history[3]),0,1); quick = s.speed_curve.Evaluate(in.body_160)*quick;
    movement = in.animation_152 != 0 ? second : 0.0f; difference = movement-state.history[1]; state.history[1] = movement;
    state.history[5] = std::fma(std::abs(difference),p[5],(1.0f-p[5])*state.history[5]);
    const auto hold = state.history[5] < p[3] ? 1.0f : 0.0f, alpha = std::fma(1.0f-hold,p[7],p[6]*hold);
    const auto next = std::fma(1.0f-alpha,state.history[4],alpha*hold); difference = next-state.history[4];
    state.history[6] = Clamp(difference,state.history[6]-p[4],state.history[6]+p[4]);
    state.history[4] = Clamp(state.history[4]+state.history[6],0,1);
    const auto smoothing = s.smoothing_curve.Evaluate(in.body_176);
    state.history[7] = std::fma(1.0f-smoothing,state.history[7],smoothing*first);
    const auto turn = Clamp(state.history[7],-1,1);
    return {turn,Clamp(target,-1,1),base,turn*sign,base*sign,quick,Clamp(third,-1,1),Clamp(state.history[4],0,1)};
}
void SlideLatch::SetCandidateEnabled(bool enabled) { Bit(words[4],0x40000000,enabled); }
float SlideLatch::Elapsed(bool right) const { return Float(words[right ? 2 : 0]); }
void SlideLatch::SetStart(bool right,bool value) { Bit(words[right ? 3 : 1],0x80000000,value); }
void SlideLatch::SetEnd(bool right,bool value) { Bit(words[right ? 3 : 1],0x40000000,value); }
void SlideLatch::AdvanceElapsed(bool right,float dt) { auto& word = words[right ? 2 : 0]; word = Bits(dt+Float(word)); }
void SlideLatch::BeginSlide(bool fakie) { words[0] = words[2] = 0; Bit(words[4],0x80000000,fakie); }
void SlideLatch::Grab(bool authored_right) { words[authored_right != CapturedFakie() ? 3 : 1] |= 0x20000000; }
void SlideLatch::Reset() { words[0] = words[2] = 0; words[1] &= 0x1fffffff; words[3] &= 0x1fffffff; words[4] &= 0x3fffffff; }
void SetTurningState::Enter() { elapsed = smoothed = 0; mode = 2; }
void UpdateSetTurning(SetTurningState& state,SlideLatch& latch,SetTurningPhysical p,Stance stance,float dt,
    const SetTurningSettings& s,SetTurningIntents intents,const std::function<void(TurningAttribute,float)>& emit)
{
    auto& w = latch.words;
    const auto a = s.remaps[0].Apply({p.field_32,p.field_56}); (void)s.remaps[0].Apply({p.field_36,p.field_56});
    const auto b = s.remaps[1].Apply({p.field_32,p.field_56}); (void)s.remaps[1].Apply({p.field_36,p.field_56});
    const auto complement = 1.0f-p.field_52; auto target = -std::fma(a[0],p.field_52,b[0]*complement);
    const auto direction = -std::fma(a[1],p.field_52,b[1]*complement);
    const auto old0 = w[1], old1 = w[3]; w[1] &= ~0x20000000u; w[3] &= ~0x20000000u;
    const auto prior0 = (old0&0x20000000) != 0, prior1 = (old1&0x20000000) != 0, enabled = (w[4]&0x40000000) != 0;
    auto mode = state.mode;
    if (mode == 2)
    {
        const auto first = enabled && ((w[3]&0x80000000) != 0 || prior1), second = enabled && ((w[1]&0x80000000) != 0 || prior0);
        if (first || second)
        {
            if (!prior0 && !prior1) { w[0] = w[2] = 0; Bit(w[4],0x80000000,stance.first); }
            mode = first ? 1 : 0;
        }
    }
    else if ((mode == 1 && (!enabled || (w[3]&0x40000000) != 0)) || (mode == 0 && (!enabled || (w[1]&0x40000000) != 0))) mode = 2;
    if (mode <= 1) { target = (mode == 1) != stance.second ? 1.0f : -1.0f; if ((w[4]&0x80000000) != 0) target = -target; }
    if (mode != state.mode) state.elapsed = 0; state.mode = mode;
    const auto blend = s.blend.Evaluate(state.elapsed), lower = state.smoothed-s.maximum_delta, upper = state.smoothed+s.maximum_delta;
    auto value = std::fma(1.0f-blend,state.smoothed,blend*target); value = lower-value >= 0 ? lower : value;
    state.elapsed += dt; state.smoothed = upper-value >= 0 ? value : upper;
    const auto speed = std::abs(p.body_168), tuck = speed > s.speed_threshold ? s.speed_tuck.Evaluate(speed-s.speed_threshold) : 0.0f;
    emit(TurningAttribute::Angle,state.smoothed); emit(TurningAttribute::Direction,direction); emit(TurningAttribute::Quickness,p.field_52);
    emit(TurningAttribute::Speed,tuck); emit(TurningAttribute::Holding,p.field_60);
    if (mode <= 1)
    {
        const auto flip = (w[4]&0x80000000) != 0; const auto turn = (mode == 1) != flip ? s.override_turn : -s.override_turn;
        emit(TurningAttribute::Turn,turn); auto slide = (mode == 0 ? intents.mode_0_slide : intents.mode_1_slide).value_or(0);
        if (flip) { const auto negative = -slide, absolute = std::abs(negative), mapped = absolute > 0.5f ? 1.0f-absolute : absolute; slide = negative >= 0 ? mapped : -mapped; }
        emit(TurningAttribute::Slide,slide);
    }
    else if (intents.fakie_turn) emit(TurningAttribute::Turn,*intents.fakie_turn);
}
float PowerSlidingAlignment(std::optional<PowerSlidingAlignmentInput> input)
{
    if (!input) return 1;
    const auto squared = Dot3(input->velocity,input->velocity); if (!(squared > Float(0x3a83126f))) return 1;
    const auto length = ControllerMagnitude(squared); auto reciprocal = ReciprocalEstimate(length);
    for (unsigned i = 0; i < 2; ++i) reciprocal = std::fma(reciprocal,std::fma(-reciprocal,length,1.0f),reciprocal);
    auto velocity = input->velocity, basis = input->basis;
    for (auto& v : velocity) v = reciprocal*v;
    if (input->flipped != 0) for (auto& v : basis) v = -v;
    return Dot3(velocity,basis);
}
void UpdatePowerSliding(PowerSlidingState& state,SlideLatch& latch,PowerSlidingInput in,const PowerSlidingSettings& s,const std::function<float()>& clock)
{
    auto& w = latch.words; const auto right = in.right_slide.value_or(0), left = in.left_slide.value_or(0); const auto active = in.category == 1;
    if (active && (state.flags&0x20000000) == 0) { state.elapsed = 0; state.previous_right = right; state.previous_left = left; state.flags &= 0x3fffffff; }
    Bit(state.flags,0x20000000,active); if (!active) return;
    const auto fast = in.speed > s.minimum_speed;
    Bit(w[3],0x80000000,fast && in.right_query && (state.flags&0x80000000) == 0 && state.previous_right < right);
    state.previous_right = right; Bit(state.flags,0x80000000,in.right_query);
    Bit(w[1],0x80000000,fast && in.left_query && (state.flags&0x40000000) == 0 && state.previous_left > left);
    state.previous_left = left; Bit(state.flags,0x40000000,in.left_query);
    const auto stop_time = s.stop_time.Evaluate(in.graph_scalar), response = s.speed_response.Evaluate(in.speed)*(1.0f-std::abs(in.graph_scalar));
    const auto threshold = s.angle_response.Evaluate(in.graph_scalar);
    state.elapsed = response < threshold ? state.elapsed+clock() : 0.0f;
    const auto stop = state.elapsed > stop_time; const auto right_time = clock()+Float(w[2]); w[2] = Bits(right_time);
    const auto left_time = clock()+Float(w[0]); w[0] = Bits(left_time);
    Bit(w[3],0x40000000,right_time > s.minimum_slide_time && (!in.right_slide || !fast || stop));
    Bit(w[1],0x40000000,left_time > s.minimum_slide_time && (!in.left_slide || !fast || stop));
}
void PublishAnimationPacket(const AnimationPacketFields& source,ProcessedPacketFields& out)
{
    const auto replace = [](std::uint32_t& w,unsigned bit,std::uint8_t value) { w = (w&~(1u<<bit))|(std::uint32_t(value&1)<<bit); };
    replace(out.flags_2468,20,source.stance_byte); out.timestep = source.timestep; out.scalar_2668 = source.scalar_10388;
    replace(out.flags_2468,3,source.flags_10375_10496_10784[0]); replace(out.flags_2468,2,source.flags_10375_10496_10784[1]);
    out.vector_1520 = source.vector_10480; replace(out.flags_2468,1,source.flags_10375_10496_10784[2]); out.matrix_1536 = source.matrix_10704;
    out.byte_1600 = source.byte_10768; out.truck_tightness = source.truck_tightness; out.scalar_2764 = source.scalar_10792; replace(out.flags_2476,20,source.flag_10371);
}
}
