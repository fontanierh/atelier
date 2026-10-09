#include "ControllerInputRuntime.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
std::optional<std::size_t> ControllerInputRuntime::ReadyDevice() const
{
    for(std::size_t i=0;i<InputDeviceSlots;++i)
        if(status[i].kind==ControllerStatus::Kind::Ready)return i;
    return std::nullopt;
}
void ControllerInputRuntime::Collect(const std::array<DeviceSample,InputDeviceSlots>& samples)
{
    const auto next=active_^1;
    for(std::size_t i=0;i<InputDeviceSlots;++i)
    {
        if(const auto* packet=std::get_if<DevicePacket>(&samples[i]))
        {
            raw_[i].buttons=packet->state.buttons;
            for(std::size_t axis=0;axis<2;++axis)
            {
                raw_[i].triggers[axis]=float(packet->state.triggers[axis])/255.0f;
                raw_[i].left[axis]=float(packet->state.left[axis])/32768.0f;
                raw_[i].right[axis]=float(packet->state.right[axis])/32768.0f;
            }
            const auto values=ConvertXbox(packet->state,std::uint8_t(packet->subtype==7));
            cache_[next][i]=HistoryRecord(std::vector<float>(values.begin(),values.end()));
            packet_numbers[i]=packet->number;
            status[i]={ControllerStatus::Kind::Ready,{}};
        }
        else
        {
            raw_[i]={};cache_[next][i].ClearCount();packet_numbers[i].reset();
            status[i]={ControllerStatus::Kind::Unavailable,std::get<DeviceError>(samples[i])};
        }
    }
    active_=next;
    history_.Publish(std::vector<HistoryRecord>(cache_[active_].begin(),cache_[active_].end()));
    ++publications;
}
bool ControllerInputRuntime::PublishActions()
{
    ++tick_;
    if(!history_.DrainToLatest(pads_))return false;
    for(std::size_t i=0;i<InputDeviceSlots;++i)
        mapped_actions[i]=GameplayActions::FromPad(pads_[i]).Values();
    ++consumed_batches;return true;
}
TickInput ControllerInputRuntime::PublishedInput() const
{
    const auto device=ReadyDevice();
    return {tick_,device ? GameplayActions::FromPad(pads_[*device]) : GameplayActions{},device.has_value()};
}
GameplayActions ControllerInputRuntime::PlayerActions() const
{
    return GameplayActions::FromPad(pads_[ReadyDevice().value_or(0)]);
}
RawInput ControllerInputRuntime::CurrentRawInput() const
{
    const auto device=ReadyDevice();return device ? raw_[*device] : RawInput{};
}
std::array<bool,3> ControllerInputRuntime::SessionMarkerActions() const
{
    const auto device=ReadyDevice();if(!device)return {false,false,false};
    const auto& pad=pads_[*device];if(pad.Count()==0)return {false,false,false};
    const auto flags=[&](std::size_t i){return i<pad.Records().size() ? pad.Records()[i][1] : 0u;};
    const bool modifier=(flags(8)&0xff00)!=0;
    return {modifier,modifier && (flags(1)&0xff000000)!=0,modifier && (flags(0)&0xff00)!=0};
}
void ControllerInputRuntime::DiscardGameplay()
{
    history_=PadHistory{};pads_={};mapped_actions={};
}
void ControllerInputRuntime::Sample(XboxState state)
{
    std::array<DeviceSample,InputDeviceSlots> samples;
    for(auto& sample:samples)sample=DeviceError{};
    samples[0]=DevicePacket{std::uint32_t(publications)+1,state,1};
    Collect(samples);PublishActions();
}
}
