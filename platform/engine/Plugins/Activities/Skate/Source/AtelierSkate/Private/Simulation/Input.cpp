#include "Input.h"
#include "SimulationMath.h"
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
std::int32_t Signed(std::uint32_t bits) { std::int32_t value; std::memcpy(&value,&bits,4); return value; }
float Positive(float value) { return -value >= 0 ? 0.0f : value; }
std::array<float,4> ConditionStick(std::array<std::int16_t,2> stick)
{
    auto x = float(stick[0])*Float(0x38000000), y = float(stick[1])*Float(0x38000000);
    const auto length = ControllerMagnitude(std::fma(y,y,x*x));
    float factor;
    if (length < Float(0x3a83126f)) factor = 0;
    else
    {
        const auto scaled = (length-0.25f)*Float(0x3fb6db6e);
        const auto bounded = scaled < 0 ? 0.0f : scaled > 1 ? 1.0f : scaled;
        factor = bounded/length;
    }
    x = factor*x; y = factor*y;
    return {Positive(x),Positive(-x),Positive(y),Positive(-y)};
}
}
void Pad::Update(const std::vector<float>& values)
{
    if (values.size() > count_)
    {
        if (values.size() > records_.size()) records_.resize(values.size());
        std::fill(records_.begin()+count_,records_.begin()+values.size(),Record{});
    }
    count_ = values.size();
    for (std::size_t i = 0; i < values.size(); ++i)
    {
        auto& r = records_[i]; r[0] = Bits(values[i]);
        const auto down = std::uint32_t(values[i] > 0.5f), held = (r[1]>>8)&255;
        if (Signed(r[3]) < 3) { ++r[3]; r[1] &= 0xffff; }
        else if (down == held) r[1] &= 0xffff;
        else { r[1] = (r[1]&255)|(down<<8)|(down != 0 ? 1u<<24 : 1u<<16); r[3] = 0; }
        if (r[1]&0xff00)
        {
            if (r[2] == 0) { r[1] = (r[1]&~255u)|1; r[2] = 24; }
            else if (--r[2] == 0) { r[1] = (r[1]&~255u)|1; r[2] = 12; }
            else r[1] &= ~255u;
        }
        else { r[2] = 0; r[1] &= ~255u; }
    }
}
HistoryRecord::HistoryRecord(const std::vector<float>& values) : count(values.size())
{
    assert(values.size() <= InputMaxValues); std::copy(values.begin(),values.end(),storage.begin());
}
void PadHistory::Publish(const std::vector<HistoryRecord>& records)
{
    assert(records.size() <= InputDeviceSlots);
    std::copy(records.begin(),records.end(),batches_[write_].begin());
    write_ = (write_+1)%InputHistoryCapacity;
}
bool PadHistory::DrainToLatest(std::array<Pad,InputDeviceSlots>& pads)
{
    if ((read_+1)%InputHistoryCapacity == write_) return false;
    auto latest = read_;
    while ((read_+1)%InputHistoryCapacity != write_) { read_ = (read_+1)%InputHistoryCapacity; latest = read_; }
    for (std::size_t i = 0; i < InputDeviceSlots; ++i)
    {
        const auto& r = batches_[latest][i];
        pads[i].Update(std::vector<float>(r.storage.begin(),r.storage.begin()+r.count));
    }
    return true;
}
GameplayActions GameplayActions::FromPad(const Pad& pad)
{
    const auto value = [&](std::size_t slot) { return pad.Count() == 0 ? 0.0f : Float(pad.Records().at(slot)[0]); };
    return GameplayActions({value(16)-value(17),value(18)-value(19),value(6),value(20)-value(21),value(22)-value(23),
        value(7),value(10),value(11),value(8),value(9),value(0),value(1),value(2),value(3),value(14),value(15),value(12),value(13)});
}
std::array<float,24> ConvertXbox(const XboxState& state, std::uint8_t device_byte_13)
{
    std::array<float,24> result{};
    for (std::size_t bit = 0; bit < 10; ++bit) result[bit] = state.buttons&(1u<<bit) ? 1 : 0;
    result[10] = float(state.triggers[0])*Float(0x3b808081); result[11] = float(state.triggers[1])*Float(0x3b808081);
    for (std::size_t bit = 12; bit < 16; ++bit) result[bit] = state.buttons&(1u<<bit) ? 1 : 0;
    const auto left = ConditionStick(state.left), right = ConditionStick(state.right);
    std::copy(left.begin(),left.end(),result.begin()+16); std::copy(right.begin(),right.end(),result.begin()+20);
    if (device_byte_13 != 0) for (auto slot : {10,11,21,22}) result[slot] = 0;
    return result;
}
float ControllerMagnitude(float squared)
{
    auto inverse = ReciprocalSquareRootEstimate(squared);
    for (unsigned i = 0; i < 2; ++i)
    {
        const auto correction = std::fma(-squared,inverse*inverse,1.0f);
        inverse = std::fma(inverse*0.5f,correction,inverse);
    }
    return squared == 0 ? 0.0f : squared*inverse;
}
float LeftStickAngle(float x, float y)
{
    if (x == 0 && y == 0) return 0;
    const auto vertical = -y, reciprocal = ReciprocalEstimate(vertical);
    const auto refined = std::fma(reciprocal,std::fma(-reciprocal,vertical,1.0f),reciprocal);
    const auto basic = Atan(std::fma(x,refined,0.0f));
    const auto sign = Bits(x)&0x80000000;
    const auto angle = 0 > vertical ? Float(0x40490fdb|sign)+basic : basic;
    return vertical == 0 ? Float(0x3fc90fdb|sign) : angle;
}
void RawControllerInput::SetBit(std::uint32_t bit, std::uint8_t value)
{
    words_[6] = (words_[6]&~(1u<<bit))|(std::uint32_t(value&1)<<bit);
}
void RawControllerInput::Update(const RawControllerInput& previous, ActionMap& map, bool state_502, bool state_104)
{
    const std::array<std::uint32_t,6> axes{64,65,67,68,70,71};
    for (std::size_t i = 0; i < axes.size(); ++i) words_[i] = Bits(map.Value(axes[i]));
    for (auto pair : {std::pair<std::uint32_t,std::uint32_t>{66,31},{69,30},{72,29},{73,28}}) SetBit(pair.second,map.State(pair.first));
    constexpr auto both = (1u<<29)|(1u<<28);
    if ((words_[6]&both) == both)
    {
        const auto prior = previous.words_[6]&both;
        if ((prior == (1u<<29) || prior == (1u<<28)) && (state_502 || state_104)) words_[6] = (words_[6]&~both)|prior;
        else words_[6] &= ~(1u<<28);
    }
    for (std::uint32_t action = 74; action <= 81; ++action) SetBit(101-action,map.State(action));
}
void DerivedControllerInput::Initialize()
{
    const auto last = words_[6]&0xfffff, current = words_[13]&0xfffff;
    words_.fill(0); words_[6] = last; words_[13] = current;
    std::fill(words_.begin()+16,words_.begin()+20,0x7effffff);
}
void DerivedControllerInput::AdvanceOrReset(std::size_t slot, bool advance, float timestep)
{
    words_[slot] = advance ? Bits(Float(words_[slot])+timestep) : 0;
}
void DerivedControllerInput::Update(ActionMap& map, float timestep, bool state_502, bool state_104, const MagnitudeHeldSettings& settings)
{
    std::array<std::uint32_t,7> previous_words;
    std::copy(words_.begin()+7,words_.begin()+14,previous_words.begin());
    const RawControllerInput previous(previous_words);
    std::copy(previous_words.begin(),previous_words.end(),words_.begin());
    auto current = previous; current.Update(previous,map,state_502,state_104);
    std::copy(current.Words().begin(),current.Words().end(),words_.begin()+7);
    AdvanceOrReset(14,Float(current.Words()[4]) == 1,timestep); AdvanceOrReset(15,Float(current.Words()[5]) == 1,timestep);
    const auto before = previous_words[6], now = current.Words()[6];
    for (auto triple : {std::array<std::size_t,3>{31,16,17},{30,18,19}})
    {
        const auto was = (before&(1u<<triple[0])) != 0, down = (now&(1u<<triple[0])) != 0;
        AdvanceOrReset(triple[1],!(!was && down),timestep); AdvanceOrReset(triple[2],!(was && !down),timestep);
    }
    for (auto pair : {std::pair<std::size_t,std::uint32_t>{20,80},{21,81},{22,78},{23,79}})
        AdvanceOrReset(pair.first,map.State(pair.second) != 0,timestep);
    const auto lx = map.Value(64), ly = map.Value(65), rx = map.Value(67), ry = map.Value(68);
    const auto right = ControllerMagnitude(std::fma(ry,ry,rx*rx)), left = ControllerMagnitude(std::fma(ly,ly,lx*lx));
    const auto threshold = settings.attribute.value_or(settings.missing_attribute_value);
    AdvanceOrReset(24,!(left <= threshold),timestep); AdvanceOrReset(25,!(right <= threshold),timestep);
}
}
