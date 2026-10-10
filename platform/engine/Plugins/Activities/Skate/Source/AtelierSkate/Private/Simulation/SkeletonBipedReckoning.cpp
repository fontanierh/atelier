#include "SkeletonBiped.h"
#include "StockSettingsReader.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 BipedFilterControl(const GroundNormalFilter& filter){Vec4 v;std::memcpy(v.data(),filter.words.data(),16);return v;}
Vec3 BipedReckoningXYZ(Vec4 v){return {v[0],v[1],v[2]};}
float BipedReckoningBits(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
}
bool BipedSkeletonState::Load(const SettingsDatabase& data,std::string& error)
{
    BipedSkeletonState next;StockSettingsReader reader(data);std::vector<std::uint32_t> words;
    if(!reader.Words("physics_reckoning","default","GroundNormalSmoothing",4,words,error))return false;
    std::memcpy(next.ground_normal_smoothing.data(),words.data(),16);
    if(!reader.Words("physics_reckoning","default","TiltVsRotGround",16,words,error))return false;
    std::memcpy(next.tilt_vs_rotation.x.data(),words.data(),32);std::memcpy(next.tilt_vs_rotation.y.data(),words.data()+8,32);
    if(!reader.Words("physics_reckoning","default","TiltVsSlopeGround",16,words,error))return false;
    std::memcpy(next.tilt_vs_slope.x.data(),words.data(),32);std::memcpy(next.tilt_vs_slope.y.data(),words.data()+8,32);*this=next;return true;
}
BipedReckoningOutput UpdateBipedReckoning(GroundOrientation& orientation,ReckoningFrames& frames,PhysicalBodySpinState& body_spin,
    AirReckoningState& air,const BipedSkeletonState& settings,const BipedReckoningInput& input)
{
    orientation.dynamic_up=BipedReckoningXYZ(input.previous_up);frames.target_lean_angle=0;air.secondary_lean_angle=0;orientation.up_velocity={};
    const auto ground=orientation.ground_filter.Update(settings.ground_normal_smoothing,input.requested_up);orientation.ground_normal=BipedReckoningXYZ(ground);frames.heading=input.requested_forward;
    const auto retained=1-input.blend;Vec4 candidate;for(unsigned n=0;n<4;++n)candidate[n]=std::fma(input.previous_up[n],input.blend,input.requested_up[n]*retained);
    const auto square=Dot3(candidate,candidate),inverse=InverseLengthSquared(square,2),length=square==0?0:square*inverse;auto up=input.previous_up;
    if(length>BipedReckoningBits(0x358637bd))for(unsigned n=0;n<4;++n)up[n]=candidate[n]*inverse;
    orientation.up=BipedReckoningXYZ(up);orientation.target=BipedReckoningXYZ(up);
    // FilterRaw re-writes the existing four control bits, then executes the
    // unchanged filter. This retains the original private filter() semantics.
    orientation.slow_filter.FilterRaw(BipedFilterControl(orientation.slow_filter),up);
    orientation.fast_filter.FilterRaw(BipedFilterControl(orientation.fast_filter),up);
    orientation.slow_filter.PublishCurrent(up);orientation.fast_filter.PublishCurrent(up);
    frames.CalculateTransform(up,ground);frames.CalculateTilt(input.reverse_stance,settings.tilt_vs_rotation,settings.tilt_vs_slope);
    std::string error;if(!UpdatePhysicalBodySpinGround(body_spin,input.enable_body_spin_input?input.physical_body_spin_2812:0,error))std::abort();
    return {input.previous_up,up,up,{},ground};
}
BipedReckoningOutput FinishBipedReckoning(const BipedSkeletonState& settings,BipedReckoningUpdate update,PhysicalRidingOutputs& riding,
    AirReckoning& air,const ProcessedPhysicsInput& p,float spin)
{
    const auto old=riding.reckoning.up;
    return UpdateBipedReckoning(riding.reckoning,riding.reckoning_frames,riding.body_spin,air.state,settings,
        {{old.x,old.y,old.z,0},update.up,update.forward,update.blend,(p.flags_2468&0x100000)!=0,true,spin});
}
}
