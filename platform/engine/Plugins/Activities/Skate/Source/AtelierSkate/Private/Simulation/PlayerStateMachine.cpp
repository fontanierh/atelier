#include "PlayerStateMachine.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float ElapsedSum(float elapsed,float timestep)
{
    // Preserve the frozen producer's NaN operand priority. The compiler may
    // otherwise commute this addition and retain the timestep's payload.
    std::uint32_t a,b;std::memcpy(&a,&elapsed,4);std::memcpy(&b,&timestep,4);
    const auto nan=[](std::uint32_t w){return (w&0x7f800000u)==0x7f800000u&&(w&0x007fffffu)!=0;};
    const auto signaling=[&](std::uint32_t w){return nan(w)&&(w&0x00400000u)==0;};
    const auto quiet=[](std::uint32_t w){w|=0x00400000u;float value;std::memcpy(&value,&w,4);return value;};
    if(signaling(a))return quiet(a);
    if(signaling(b))return quiet(b);
    if(nan(a))return elapsed;
    if(nan(b))return timestep;
    return elapsed+timestep;
}
}
std::array<std::uint32_t,4> PreStatePacket::Vector48() const {return {words[12],words[13],words[14],words[15]};}
void RunPlayerPreState(PreStatePlayerFields& player,PreStateSkeletonFields& skeleton,PreStateServices& services)
{
    ++player.frame_counter_1312;PreStatePacket packet{};services.FillPacketVtable24(packet);
    skeleton.predicted_position_16112=packet.Vector48();skeleton.predicted_position_set_16416=true;skeleton.nested_flag_3184=false;
    if (player.component_1840_present) services.UpdateComponent1840();
    services.UpdateBeforeStateVtable4();
}
void RunPlayerStatePhase(StatePhaseFields& fields,StatePhaseServices& services)
{
    services.UpdateCurrentStateVtable8();
    if (fields.controller_system_on_452)
    {
        services.UpdateController();
        switch (fields.controller_state_448)
        {case 1:services.UpdateControllerMode1();break;case 2:services.UpdateControllerMode2();break;case 3:services.UpdateControllerMode3();break;case 4:services.UpdateControllerMode4();break;default:break;}
    }
    services.TouchSkateboardVtable116();services.ApplySkateboardForceQueue();services.UpdateSkateboardFixedStepCache();fields.elapsed_1344=ElapsedSum(fields.elapsed_1344,fields.timestep_2604);
}
void RunPlayerPostState(PostStateServices& services) {services.UpdateCurrentStateVtable12();}
}
