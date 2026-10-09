#include "PlayerInputPublication.h"
#include "GroundSurfaceRuntime.h"
#include "RidingAngles.h"
#include "StockSettingsReader.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits){float f;std::memcpy(&f,&bits,4);return f;}
RawVector Raw(Vec3 v){const Vec4 f{v.x,v.y,v.z,0};RawVector out;for(std::size_t i=0;i<4;++i)std::memcpy(&out[i],&f[i],4);return out;}
Vec3 XYZ(Vec4 v){return {v[0],v[1],v[2]};}
Vec3 Add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
std::pair<Vec3,float> NormalizeLength(Vec3 v)
{
    const float square=Dot3(v,v),inverse=InverseLengthSquared(square,2);
    const float length=square==0.0f ? 0.0f : square*inverse;
    return {length>Float(0x358637bd) ? Scale(v,inverse) : Vec3{},length};
}
Vec3 Reject(Vec3 vector,Vec3 normal){return Subtract(vector,Scale(normal,Dot3(vector,normal)));}
float TravelAngle(Vec3 forward,Vec3 velocity,Vec3 normal,Vec3 ground_up)
{
    auto projected=Reject(forward,normal);if(!(Dot3(projected,velocity)>0.0f))projected=Scale(projected,-1.0f);
    const float angle=Dot3(projected,projected)*Dot3(velocity,velocity)>Float(0x37800000)
        ? RidingSignedAngle(Reject(projected,ground_up),Reject(velocity,ground_up),ground_up) : 0.0f;
    return RidingFractionWrappedAngle(angle);
}
}
bool PlayerDynamicNormalSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const StockSettingsReader reader(data);std::vector<std::uint32_t> values;PlayerDynamicNormalSettings next;
    if(!reader.Words("physics_reckoning","default","DynamicSpeedMaxDeltaGraphZ",16,values,error))return false;
    if(!reader.Float("physics_reckoning","default","DynamicSpeedDamping",next.speed_damping,error))return false;
    if(!reader.Float("physics_reckoning","default","DynamicUpVectorDamping",next.up_vector_damping,error))return false;
    if(!reader.Float("physics_reckoning","default","DynamicSpeedMaxDelta",next.maximum_delta,error))return false;
    if(!reader.Float("physics_reckoning","default","DynamicSpeedMaxDeltaXScale",next.speed_scale,error))return false;
    for(std::size_t i=0;i<8;++i){next.maximum_delta_vs_speed.x[i]=Float(values[i]);next.maximum_delta_vs_speed.y[i]=Float(values[i+8]);}
    *this=next;error.clear();return true;
}
void PlayerDynamicNormal::Update(const BoardGroundState& contacts,Vec3 gravity,float speed,const PlayerDynamicNormalSettings& settings)
{
    if(contacts.wheel_contact_count==0){acceleration={};return;}
    Vec3 sum{};for(std::size_t i=0;i<3;++i)if(contacts.parts[i].in_contact)sum=Subtract(Add(sum,contacts.accelerations[i]),gravity);
    const auto target=NormalizeLength(sum).first;delta=Scale(delta,settings.speed_damping);
    const auto error=Scale(Subtract(target,normal),settings.up_vector_damping);const auto normalized=NormalizeLength(error);
    const float maximum=settings.maximum_delta_vs_speed.Evaluate(std::abs(speed)/settings.speed_scale)*settings.maximum_delta;
    const float nonnegative=-normalized.second>=-0.0f ? 0.0f : normalized.second;
    const float amount=maximum-nonnegative>=-0.0f ? nonnegative : maximum;
    delta={std::fma(normalized.first.x,amount,delta.x),std::fma(normalized.first.y,amount,delta.y),std::fma(normalized.first.z,amount,delta.z)};
    normal=NormalizeLength(Add(normal,delta)).first;last_contact_normal=contacts.overall_normal;
}
void PublishPlayerBoardInput(PhysicalPlayerInput& out,const BoardMotionOutput& motion,const BoardGroundState& contacts,PlayerBoardInputFrame frame)
{
    const auto side=motion.effective_basis.columns[0];const float sign=(frame.processed_flags_2476&4)!=0 ? -1.0f : 1.0f;
    out.board_reckoning_side_176=Raw({side[0]*sign,side[1]*sign,side[2]*sign});
    out.skateboard.vector_64=Raw(motion.angular_velocity);out.skateboard.vector_80=Raw(motion.linear_velocity);out.skateboard.vector_96=Raw(motion.ground_velocity);
    out.skateboard.scalar_160=motion.speed;out.skateboard.scalar_164=motion.ground_speed;out.skateboard.scalar_168=motion.forward_speed;
    out.skateboard.scalar_172=TravelAngle(frame.processed_forward,motion.ground_velocity,frame.reckoning_normal_1216,frame.reckoning_ground_up);
    out.ground.vector_64=Raw(frame.retained_ground_normal_112);out.ground.vector_96=Raw(contacts.wheel_normal);
    for(std::size_t i=0;i<4;++i)out.collision.wheel_contact_3296_3299[i]=std::uint8_t(contacts.parts[i].in_contact);
    out.collision.wheel_count_0=contacts.wheel_contact_count;
    out.collision.flag_3472=std::uint8_t(contacts.parts[std::size_t(BoardBodyId::FrontTruck)].in_contact||contacts.parts[std::size_t(BoardBodyId::BackTruck)].in_contact);
    out.collision.flag_3475=std::uint8_t(contacts.parts[std::size_t(BoardBodyId::Deck)].in_contact);
    out.collision.flag_3477=std::uint8_t(out.collision.wheel_count_0>0||out.collision.flag_3472!=0||out.collision.flag_3475!=0);
}
bool PublishPlayerBoardOutputs(PhysicalPlayerInput& out,const PhysicalRidingOutputs& riding,const std::optional<BoardToolkit>& toolkit,const PlayerDynamicNormal& dynamic_normal,const ProcessedPhysicsInput& processed,std::string& error)
{
    if(!toolkit){error="Board output requires the current input toolkit";return false;}
    PublishPlayerBoardInput(out,riding.motion,riding.ground,{XYZ(toolkit->deck[2]),riding.reckoning.ground_normal,XYZ(riding.reckoning_frames.ground[1]),dynamic_normal.normal,processed.flags_2476});
    out.ground.vector_80=Raw(riding.ground.wheel_normal);out.ground.flag_273=std::uint8_t((processed.flags_2468&0x100000)!=0);
    // The surface the wheels vote for selects the next frame's ground profile (SelectSurface); untagged worlds vote 1.
    std::array<bool,4> contacts;for(unsigned i=0;i<4;++i)contacts[i]=riding.ground.parts[i].in_contact;
    if(!ChoosePlayerGroundSurface(riding.wheel_lines.physics_surfaces,contacts,false,out.surface_default_mode,error))return false;
    error.clear();return true;
}
bool PublishPlayerGrindGraphOutputs(PhysicalPlayerInput& out,const SkeletonPhysicalRecord& record,Vec4 up,const std::optional<BoardToolkit>& toolkit,const PlayerTrajectoryGrindOwner& trajectory,std::string& error)
{
    if(!toolkit){error="Grind output requires the completed physical input toolkit";return false;}
    out.air.flag_443=std::uint8_t(trajectory.GrindLockedToMiddle());out.skeleton.PublishTwist(record,toolkit->forward,up);error.clear();return true;
}
}
