#include "GroundPumpingRuntime.h"
#include "RidingAngles.h"
#include "BoardGroundAngle.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
Vec4 Four(Vec3 value) {return {value.x,value.y,value.z,0};}
Vec3 Three(Vec4 value) {return {value[0],value[1],value[2]};}
float Wrap(float angle)
{
    const auto turns=angle*Float(0x3e22f983),fraction=turns-std::floor(turns);
    return (fraction-(fraction>0.5f?1.0f:0.0f))*Float(0x40c90fdb);
}
}
void UpdatePhysicalGroundPumping(PumpingState& state,const PumpingConfiguration& config,GroundPumpingMode mode,
    const BoardToolkit& toolkit,const PhysicalRidingOutputs& riding,const SkeletonAnimationRecord& record,
    const SkeletonBoardFrames& board_frames,std::uint32_t flags)
{
    const auto up=Four(riding.reckoning.up),animated_at=board_frames.animation_target[2];float angle=0;
    if (std::abs(Dot3(toolkit.deck[2],up))>std::abs(Dot3(animated_at,up)))
    {
        const auto axis=Three(riding.reckoning_frames.ground[0]);
        const auto deck=Wrap(RidingSignedAngle(Three(toolkit.deck[2]),Three(up),axis));
        const auto animated=Wrap(RidingSignedAngle(Three(animated_at),Three(up),axis));
        angle=std::abs(deck-animated);
    }
    const PumpingSample sample{toolkit.deck[3],Four(riding.reckoning.ground_normal),
        record.com_to_deck_world,angle,std::uint8_t((flags>>1)&1)};
    UpdateGroundPumping(state,config.settings,mode.controller,sample);
}
bool UpdatePhysicalRevertPumping(PumpingState& state,const PumpingConfiguration& config,const BoardToolkit& toolkit,
    const PhysicalRidingOutputs& riding,const SkeletonAnimationRecord& record,const ProcessedPhysicsInput& p,
    float balance,std::string& error)
{
    const auto angle=balance!=0?0:std::abs(std::abs(BoardGroundAngleBetween(Three(toolkit.deck[2]),
        riding.reckoning.up))-Float(0x3fc90fdb));
    const PumpingSample sample{toolkit.deck[3],Four(riding.reckoning.ground_normal),
        record.com_to_deck_world,angle,std::uint8_t((p.flags_2472>>16)&1)};
    GroundPumpingMode mode;if (!config.Mode(p.state_variant_index_2528,mode,error)) return false;
    UpdatePumping(state,config.settings,mode.controller,sample,p.timestep_2604);return true;
}
}
