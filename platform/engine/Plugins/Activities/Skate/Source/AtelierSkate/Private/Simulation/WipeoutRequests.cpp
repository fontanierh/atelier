#include "WipeoutRequests.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
namespace atelier::skate
{
namespace {float Word(std::uint32_t word) {float f;std::memcpy(&f,&word,4);return f;}}
void WipeoutRequests::InitializePlayer() {cooldown=Word(0x3d23d70a);}
void WipeoutRequests::Teleport() {cooldown=Word(0x3ecccccd);}
void WipeoutRequests::EnterGround() {if (mode!=1) {balance=0;mode=1;}}
void WipeoutRequests::Request(std::size_t index,float value)
{
    if (index>=reasons.size()) std::abort();
    reasons[index]=true;values[index]=value;++count;
}
void WipeoutRequests::ClearAfterSelection() {reasons.fill(false);values.fill(0);count=0;}
void WipeoutRequests::ResetSystems() {mode=0;count=0;}
bool WipeoutRequests::RequestsRunout(const WipeoutRequestInput& frame) const
{
    return (count==1&&(reasons[2]||reasons[24]||reasons[10])&&(frame.flags_2468&(1u<<5))==0
        &&(frame.flags_2476&(1u<<26))==0&&std::fabs(frame.animation_up_y)>Word(0x3f4f5c29))
        ||((frame.flags_2484&(1u<<12))!=0&&frame.category==400);
}
bool WipeoutRequests::RequestsWipeout(const WipeoutRequestInput& frame) const
{
    return !RequestsRunout(frame)&&(std::any_of(reasons.begin(),reasons.end(),[](bool v){return v;})||(frame.flags_2480&(1u<<3))!=0);
}
}
