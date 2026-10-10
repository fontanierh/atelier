#pragma once
#include "Input.h"
#include <variant>

namespace atelier::skate
{
struct DevicePacket
{
    std::uint32_t number=0;
    XboxState state{};
    std::uint8_t subtype=1;
};
struct DeviceError
{
    enum class Kind {Disconnected,State,Capabilities,UnsupportedPlatform};
    Kind kind=Kind::Disconnected;
    std::uint32_t code=0;
};
using DeviceSample=std::variant<DevicePacket,DeviceError>;
struct ControllerStatus
{
    enum class Kind {Unpolled,Ready,Unavailable};
    Kind kind=Kind::Unpolled;
    DeviceError error{};
};
struct RawInput
{
    std::uint16_t buttons=0;
    std::array<float,2> triggers{},left{},right{};
};
// Host-frame collection and simulation-tick publication retain separate clocks.
// Even an unchanged device packet enters Pad history; no packet deduplication.
class ControllerInputRuntime
{
public:
    void Collect(const std::array<DeviceSample,InputDeviceSlots>&);
    bool PublishActions();
    TickInput PublishedInput() const;
    GameplayActions PlayerActions() const;
    RawInput CurrentRawInput() const;
    std::array<bool,3> SessionMarkerActions() const;
    void DiscardGameplay();
    void Sample(XboxState);
    const std::array<Pad,InputDeviceSlots>& Pads() const {return pads_;}
    const PadHistory& History() const {return history_;}
    const std::array<RawInput,InputDeviceSlots>& Raw() const {return raw_;}
    const std::array<std::array<HistoryRecord,InputDeviceSlots>,2>& Cache() const {return cache_;}
    std::size_t ActiveCache() const {return active_;}
    std::uint64_t Tick() const {return tick_;}
    std::array<ControllerStatus,InputDeviceSlots> status{};
    std::array<std::optional<std::uint32_t>,InputDeviceSlots> packet_numbers{};
    std::array<std::array<float,18>,InputDeviceSlots> mapped_actions{};
    std::uint64_t publications=0,consumed_batches=0;
private:
    std::optional<std::size_t> ReadyDevice() const;
    std::array<RawInput,InputDeviceSlots> raw_{};
    std::array<std::array<HistoryRecord,InputDeviceSlots>,2> cache_{};
    std::size_t active_=0;
    PadHistory history_;
    std::array<Pad,InputDeviceSlots> pads_{};
    std::uint64_t tick_=0;
};
}
