#pragma once
#include <array>
#include <cassert>
#include <cstdint>
#include <optional>
#include <vector>
#include <utility>

namespace atelier::skate
{
class Pad
{
public:
    using Record = std::array<std::uint32_t,4>;
    Pad() = default;
    explicit Pad(std::vector<Record> records) : records_(std::move(records)), count_(records_.size()) {}
    Pad(std::vector<Record> records, std::size_t count) : records_(std::move(records)), count_(count) { assert(count <= records_.size()); }
    std::size_t Count() const { return count_; }
    const std::vector<Record>& Records() const { return records_; }
    void Update(const std::vector<float>& values);
private:
    std::vector<Record> records_;
    std::size_t count_ = 0;
};
constexpr std::size_t InputHistoryCapacity = 30, InputDeviceSlots = 4, InputMaxValues = 24;
struct HistoryRecord
{
    std::array<float,InputMaxValues> storage{};
    std::size_t count = 0;
    HistoryRecord() = default;
    explicit HistoryRecord(const std::vector<float>& values);
    void ClearCount() { count = 0; }
};
class PadHistory
{
public:
    std::size_t ReadIndex() const { return read_; }
    std::size_t WriteIndex() const { return write_; }
    void Publish(const std::vector<HistoryRecord>& records);
    bool DrainToLatest(std::array<Pad,InputDeviceSlots>& pads);
private:
    std::array<std::array<HistoryRecord,InputDeviceSlots>,InputHistoryCapacity> batches_{};
    std::size_t read_ = 0, write_ = 1;
};
class ActionMap
{
public:
    virtual ~ActionMap() = default;
    virtual float Value(std::uint32_t action) = 0;
    virtual std::uint8_t State(std::uint32_t action) = 0;
};
class GameplayActions : public ActionMap
{
public:
    GameplayActions() = default;
    explicit GameplayActions(std::array<float,18> values) : values_(values) {}
    static GameplayActions FromPad(const Pad& pad);
    const std::array<float,18>& Values() const { return values_; }
    float Value(std::uint32_t action) override { assert(action >= 64 && action <= 81); return values_[action-64]; }
    std::uint8_t State(std::uint32_t action) override { return Value(action) != 0; }
private:
    std::array<float,18> values_{};
};
class TickInput
{
public:
    TickInput(std::uint64_t tick, GameplayActions actions, bool available) : tick_(tick), actions_(actions), available_(available) {}
    std::uint64_t Tick() const { return tick_; }
    GameplayActions Actions() const { return actions_; }
    bool ControllerAvailable() const { return available_; }
private:
    std::uint64_t tick_;
    GameplayActions actions_;
    bool available_;
};
struct XboxState
{
    std::uint16_t buttons = 0;
    std::array<std::uint8_t,2> triggers{};
    std::array<std::int16_t,2> left{}, right{};
};
std::array<float,24> ConvertXbox(const XboxState& state, std::uint8_t device_byte_13);
float ControllerMagnitude(float squared);
float LeftStickAngle(float x, float y);
class RawControllerInput
{
public:
    explicit RawControllerInput(std::array<std::uint32_t,7> words) : words_(words) {}
    const std::array<std::uint32_t,7>& Words() const { return words_; }
    void Update(const RawControllerInput& previous, ActionMap& map, bool state_502, bool state_104);
private:
    std::array<std::uint32_t,7> words_;
    void SetBit(std::uint32_t bit, std::uint8_t value);
};
struct MagnitudeHeldSettings { std::optional<float> attribute; float missing_attribute_value = 0; };
class DerivedControllerInput
{
public:
    explicit DerivedControllerInput(std::array<std::uint32_t,26> words) : words_(words) {}
    const std::array<std::uint32_t,26>& Words() const { return words_; }
    void Initialize();
    void Update(ActionMap& map, float timestep, bool state_502, bool state_104, const MagnitudeHeldSettings& settings);
private:
    std::array<std::uint32_t,26> words_;
    void AdvanceOrReset(std::size_t slot, bool advance, float timestep);
};
}
