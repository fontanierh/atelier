// SPDX-License-Identifier: Apache-2.0
#include "PlayerStateMachine.h"
#include "PlayerStateSelector.h"
#include "PlayerStateLifecycle.h"
#include "DataReader.h"
#include <cstring>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    detail::DataReader r;explicit Input(const std::vector<std::uint8_t>& b):r{b} {r.at=0;}
    std::uint32_t Word(){return r.Word();}float Float(){return r.Float();}
    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> v;for(auto& x:v)x=Word();return v;}
    template<class T,std::size_t N,class C>std::array<T,N> Array(C callback){std::array<T,N> v;for(auto& x:v)x=callback(*this);return v;}
    template<class T,class C>std::optional<T> Optional(C callback){if(Word())return callback(*this);return std::nullopt;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;void Word(std::uint32_t w){for(unsigned i=0;i<4;++i)bytes.push_back(std::uint8_t(w>>(i*8)));}
    void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}void String(std::string_view s){Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
};
// GENERATED_PROTOCOL
struct StateCalls final:PhysicalStateCalls
{
    Output& trace;PhysicalStateId reported;StateCalls(Output& t,PhysicalStateId id):trace(t),reported(id){}
    PhysicalStateId GetType(StateBinding b) override {trace.Word(3);Observe(trace,b);return reported;}
    void Exit(StateCall c) override {trace.Word(4);Observe(trace,c);}
    void Enter(StateCall c) override {trace.Word(5);Observe(trace,c);}
};
struct ControllerActions final:SkateboardControllerActions
{
    Output& trace;explicit ControllerActions(Output& t):trace(t){}
    void HoldSkateboard() override {trace.Word(1);}void LetGoOfSkateboard() override {trace.Word(2);}
};
struct PhaseCalls final:PreStateServices,StatePhaseServices,PostStateServices
{
    Output& trace;PreStatePacket supplied;PhaseCalls(Output& t,PreStatePacket p):trace(t),supplied(p){}
    void FillPacketVtable24(PreStatePacket& p) override {trace.Word(10);Observe(trace,p);p=supplied;}
    void UpdateComponent1840() override {trace.Word(11);}void UpdateBeforeStateVtable4() override {trace.Word(12);}
    void UpdateCurrentStateVtable8() override {trace.Word(20);}void UpdateController() override {trace.Word(21);}
    void UpdateControllerMode1() override {trace.Word(22);}void UpdateControllerMode2() override {trace.Word(23);}
    void UpdateControllerMode3() override {trace.Word(24);}void UpdateControllerMode4() override {trace.Word(25);}
    void TouchSkateboardVtable116() override {trace.Word(26);}void ApplySkateboardForceQueue() override {trace.Word(27);}
    void UpdateSkateboardFixedStepCache() override {trace.Word(28);}void UpdateCurrentStateVtable12() override {trace.Word(30);}
};
void Snapshot(Output& o,const StateSelector& selector,const PhysicalPlayerStateLifecycle& lifecycle,const StateChangeData& data,const PreStatePlayerFields& player,const PreStateSkeletonFields& skeleton,const StatePhaseFields& phase)
{
    Observe(o,selector);Observe(o,lifecycle.Active());Observe(o,data);Observe(o,player);Observe(o,skeleton);Observe(o,phase);
}
int main()
{
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(bytes);Output out;
    out.Word(std::uint32_t(PhysicalStates.size()));for(auto id:PhysicalStates){out.Word(std::uint32_t(id));out.Word(PhysicalStateOwnerOffset(id));out.Word(PhysicalStateCategory(id));out.Word(IsGrindState(id));out.String(PhysicalStateName(id));}
    const auto cases=i.Word();
    for(std::uint32_t c=0;c<cases;++c)
    {
        auto selector=ReadStateSelector(i);PhysicalPlayerStateLifecycle lifecycle(PhysicalStateId(i.Word()));auto data=ReadStateChangeData(i);auto player=ReadPreStatePlayerFields(i);auto skeleton=ReadPreStateSkeletonFields(i);auto phase=ReadStatePhaseFields(i);out.Word(c);Snapshot(out,selector,lifecycle,data,player,skeleton,phase);const auto count=i.Word();
        for(std::uint32_t n=0;n<count;++n)
        {
            const auto op=i.Word();bool ok=true;std::uint32_t result=0,unknown=0;Output trace;
            if(op==0)selector=ReadStateSelector(i);
            else if(op==1){const auto raw=i.Word();const auto input=ReadStateSelectionInput(i);PhysicalStateId selected=PhysicalStateId::Sleeping;std::string error;ok=selector.Calculate(PhysicalStateId(raw),input,selected,error);if(ok)result=std::uint32_t(selected);else unknown=raw;trace.Word(StateConditionOffGroundSkitching(input.board_body,input.skitching_off_ground));trace.Word(StateConditionOffGround(input.board_body,input.normal_off_ground));trace.Word(StateIsSkateboardAnimated(input.skeleton));}
            else if(op==2)data=ReadStateChangeData(i);
            else if(op==3){const auto raw=i.Word();const auto reported=PhysicalStateId(i.Word());StateCalls states(trace,reported);ControllerActions actions(trace);StateBinding selected{};ok=lifecycle.SetPhysicsState(raw,data,states,actions,selected,unknown);if(ok)result=std::uint32_t(selected.state);}
            else if(op==4){const auto packet=ReadPreStatePacket(i);PhaseCalls services(trace,packet);RunPlayerPreState(player,skeleton,services);}
            else if(op==5){phase.timestep_2604=i.Float();phase.controller_state_448=i.Word();phase.controller_system_on_452=i.Word()!=0;PhaseCalls services(trace,{});RunPlayerStatePhase(phase,services);}
            else if(op==6)phase=ReadStatePhaseFields(i);
            else if(op==7){PhaseCalls services(trace,{});RunPlayerPostState(services);}
            else if(op==8){player=ReadPreStatePlayerFields(i);skeleton=ReadPreStateSkeletonFields(i);}
            else return 2;
            out.Word(c);out.Word(n);out.Word(op);out.Word(ok);out.Word(result);out.Word(unknown);out.Word(std::uint32_t(trace.bytes.size()/4));out.bytes.insert(out.bytes.end(),trace.bytes.begin(),trace.bytes.end());Snapshot(out,selector,lifecycle,data,player,skeleton,phase);
        }
    }
    if(!i.r.ok||i.r.at!=bytes.size())return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));
}
