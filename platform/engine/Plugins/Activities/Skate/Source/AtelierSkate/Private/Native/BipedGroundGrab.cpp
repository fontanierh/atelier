#include "BipedGroundRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t w){float v;std::memcpy(&v,&w,4);return v;}
Vec4 Value(RawVector w){Vec4 v;std::memcpy(v.data(),w.data(),16);return v;}
std::pair<Mat4,Vec4> GrabBounds(Mat4 frame,Vec4 offset,Vec4 extents)
{
    auto forward=frame[2];forward[1]=0;const float q=forward[0]*forward[0]+forward[1]*forward[1]+forward[2]*forward[2];
    const float r=InverseLengthSquared(q,2),length=q==0?0:q*r;
    if(length>Word(0x358637bd))for(float& v:forward)v*=r;else forward={0,0,1,0};
    const Vec4 up{0,1,0,0},right=Cross3(up,forward);Vec4 position;
    for(unsigned n=0;n<4;++n)position[n]=std::fma(up[n],offset[1],std::fma(forward[n],offset[2]+extents[2],frame[3][n]));
    return {Mat4{{right,up,forward,position}},extents};
}
}
void BipedGroundRuntime::SyncGrab(BipedRuntimeOwners v)
{
    const auto& p=v.processed;
    if((p.flags_2484&0x20000000)!=0||(p.flags_2480&0x40000)!=0||p.secondary_ground_timer_2852>0)return;
    if((p.flags_2476&0x400000)==0){v.grab.Invalidate();return;}
    if(state.flags_144_to_150[4]){if(!(p.state_timer_2664<=.5f))state.flags_144_to_150[4]=false;return;}
    Mat4 frame;for(unsigned n=0;n<4;++n)frame[n]=Value(p.effective_anim_transform_192[n]);const auto position=Value(p.vectors_544_560_592_608[2]);
    const auto bounds=GrabBounds(frame,grab_settings.offset_32,grab_settings.extent_16);
    if((v.grab.Cache().flags_12836&0x40)!=0)
    {
        if(const auto candidate=v.grab.Best(position))
        {
            auto extents=grab_settings.extent_0;for(float& x:extents)x*=Word(0x3f733333);const auto inner=GrabBounds(frame,grab_settings.offset_32,extents);
            const auto bone=ComposeSkeletonAffine(v.physical.roots.animation_to_world,v.physical.animation_record.pose[23])[3];
            state.flags_144_to_150[0]=QualifyGrabRecord(*candidate,bone,inner.first,inner.second,grab_settings.margin_444,grab_settings.angle_452*Word(0x3c8efa35),grab_settings.angle_436*Word(0x3c8efa35));
            if(state.flags_144_to_150[0]){const auto key=GrabRecordDescriptor(*candidate);state.counter_152=key.kind;state.counter_156=key.id;}
        }
    }
    v.grab.Query({position,position,bounds.first,bounds.second,grab_settings.margin_444,grab_settings.angle_456*Word(0x3c8efa35),grab_settings.angle_440*Word(0x3c8efa35),4,5,p.actor_query_2948,static_cast<std::int32_t>(p.actor_query_2952)});
    if(state.flags_144_to_150[0])v.grab.RequestPrimary({state.counter_152,state.counter_156});
    else v.grab.RequestInteractable(frame,{p.actor_query_2948,static_cast<std::int32_t>(p.actor_query_2952)});
}
}
