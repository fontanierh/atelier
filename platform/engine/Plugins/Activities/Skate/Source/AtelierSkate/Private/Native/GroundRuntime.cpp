// SPDX-License-Identifier: Apache-2.0
#include "GroundRuntime.h"
#include "GroundControlSettings.h"
#include "StockSettingsReader.h"
#include "GroundCorrections.h"
#include "DeckAngularCorrections.h"
#include "RidingAngles.h"
#include <cmath>
#include <string>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
constexpr auto Deck=static_cast<std::size_t>(BoardBodyId::Deck);
Vec3 XYZ(Vec4 v) {return {v[0],v[1],v[2]};}
Vec4 XYZW(Vec3 v) {return {v.x,v.y,v.z,0};}
class BoardServices final:public GroundBoardServices
{
public:
    BoardServices(GroundRuntime& runtime,BoardRuntime& board,const WorldGeometry& world,
        const GroundSettings& settings,GroundPhysicalFrame physical):runtime(runtime),board(board),world(world),settings(settings),physical(physical) {}
    GroundRuntime& runtime;
    BoardRuntime& board;
    const WorldGeometry& world;
    const GroundSettings& settings;
    GroundPhysicalFrame physical;
    std::optional<GroundLaunchInfo> launch;
    // A service that leaves the deck's torque non-finite fails with its input, so the session's error names it.
    bool DeckFinite(const char* service,Vec4 v,std::string& error) const
    {
        const auto& t=board.Bodies()[Deck].rates.torque_acceleration;
        if(std::isfinite(t.x)&&std::isfinite(t.y)&&std::isfinite(t.z))return true;
        error=std::string(service)+" left the deck torque non-finite from ("+std::to_string(v[0])+", "+std::to_string(v[1])+", "+std::to_string(v[2])+")";return false;
    }
    bool AngleBetween(Vec4 a,Vec4 b,Vec4 axis,float& output,std::string&) override
    {output=RidingSignedAngle(XYZ(a),XYZ(b),XYZ(axis));return true;}
    bool GroundDot3(Vec4 a,Vec4 b,float& output,std::string&) override {output=Dot3(a,b);return true;}
    bool GroundScaleToMagnitude(Vec4 v,float square,float size,Vec4& output,std::string&) override
    {output=atelier::skate::GroundScaleToMagnitude(v,square,size);return true;}
    bool BuildHangForce(Vec4& output,std::string&) override
    {output=runtime.BuildHangForce(board,XYZW(physical.hang_geometry.edge_start),XYZW(physical.hang_geometry.edge_end));return true;}
    bool ApplyHangForce(Vec4 force,std::string& error) override {runtime.ApplyHangForce(board,force);return DeckFinite("ApplyHangForce",force,error);}
    bool DetectHungUpGeometry(bool& output,std::string& error) override
    {return DetectGroundHungGeometry(world,physical.hang_geometry,runtime.deck_center_to_truck,output,error);}
    bool RequestHungWipeout(std::string&) override {physical.wipeout.Request(12,0);return true;}
    bool WheelCatchDisplacement(Vec4& output,std::string&) override
    {
        const auto f=board.PartTransforms()[Deck].basis.columns;
        output=GroundWheelCatchDisplacement({f[1][0],f[1][1],f[1][2],0},{f[2][0],f[2][1],f[2][2],0});return true;
    }
    bool ApplyWheelCatchDisplacement(Vec4 v,std::string& error) override {runtime.ApplyAngularDisplacement(board,v);return DeckFinite("ApplyWheelCatchDisplacement",v,error);}
    bool PinToCapturedPosition(float x,float z,std::string&) override {runtime.PinToPosition(board,x,z,physical.time_step);return true;}
    bool CenterOfMassHeight(float& output,std::string&) override
    {output=GroundCentreOfMassHeight(physical.skeleton_record.com_to_deck_world);return true;}
    bool SetContactWheelMaterials(std::string&) override {physical.wheel_material=settings.wheel_material;return true;}
    bool ContactResponse(GroundContactFrame frame,Vec4 previous,GroundBoardContactResponse& output,std::string&) override
    {runtime.contact=CalculateWallRideResponse(runtime.wall_ride,physical.wall_ride,frame,previous);output=runtime.contact;return true;}
    bool UpdateBodyAccumulator(std::string& error) override {runtime.UpdateBodyAccumulator(board);return DeckFinite("UpdateBodyAccumulator",{},error);}
    bool SetAnimatedVelocity(Vec4 v,std::string&) override {runtime.SetAnimatedVelocity(board,v);return true;}
    bool WriteProcessedVelocity(Vec4 v,std::string&) override {physical.processed_velocity=v;return true;}
    bool BuildAnimatedPose(GroundLaunchInfo& output,std::string&) override {output=GroundLaunchInfo{};return true;}
    bool PublishAnimatedPose(const GroundLaunchInfo& info,std::string& error) override
    {
        if (!physical.launch_physical) {error="Ground wall jump requires actual Skeleton/Reckoning launch observations82BE33D0";return false;}
        auto value=info;value.Fill(*physical.launch_physical,runtime.launch_cone_x,runtime.launch_cone_z);launch=std::move(value);return true;
    }
    bool UpdateExternalPlayer(const GroundLaunchInfo&,Vec4 velocity,std::string& error) override
    {
        if (!launch) {error="Ground launch packet was not filled";return false;}
        launch->WallJump(velocity);return true;
    }
    bool CommitExternalPlayer(std::string& error) override
    {
        if (!launch) {error="Ground launch packet was not prepared";return false;}
        return physical.launch_and_update.LaunchAndUpdate(*launch,error);
    }
    bool FinalizeAnimatedBoard(std::string&) override
    {
        // The original finalizer is a confirmed single return instruction.
        return true;
    }
    bool CollisionForce(Vec4 normal,std::optional<GroundBoardCollisionResponse>& output,std::string&) override
    {auto p=physical.collision;p.ground_normal=normal;output=runtime.CalculateCollisionForce(p);return true;}
    bool CollisionForceDotVelocity(Vec4 f,Vec4 v,float& output,std::string&) override
    {output=GroundCollisionForceProjection(f,v);return true;}
    bool ApplyVector(Vec4 v,std::string& error) override {runtime.ApplyAngularTarget(board,v);return DeckFinite("ApplyVector",v,error);}
    bool ApplyAngularDisplacement(Vec4 v,std::string& error) override {runtime.ApplyAngularDisplacement(board,v);return DeckFinite("ApplyAngularDisplacement",v,error);}
};
}
bool GroundRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    GroundRuntime value{};StockSettingsReader reader(data);
    const auto f=[&](std::string_view category,std::string_view field,float& output) {return reader.Float(category,"default",field,output,error);};
    if (!f("physics_trajectory","ConeAngleX",value.launch_cone_x)
        ||!f("physics_trajectory","ConeAngleZ",value.launch_cone_z)
        ||!f("physics_grinds","DeckCenterToTruck",value.deck_center_to_truck)
        ||!LoadGroundWallRideSettings(data,value.wall_ride,error)
        ||!f("physics_collision","MaxVelDelta",value.collision.maximum_velocity_delta)
        ||!f("physics_collision","ForceYOffset",value.collision.force_y_offset)
        ||!f("physics_collision","CollisionForceScalar",value.collision.force_scalar)
        ||!f("physics_collision","TargetDisplacementVel",value.collision.target_displacement_velocity)
        ||!reader.Curve8Layout20("physics_collision","default","CollisionTorqueVsAngle",value.collision.torque_vs_angle,error)) return false;
    *this=std::move(value);error.clear();return true;
}
GroundContactResponse GroundRuntime::ContactResponseWithPrevious(GroundContactFrame frame,WallRidePhysical p,Vec4 previous) const
{return CalculateWallRideResponse(wall_ride,p,frame,previous);}
std::optional<GroundBoardCollisionResponse> GroundRuntime::CalculateCollisionForce(RidingCollisionPhysical p)
{
    const auto result=CalculateRidingCollisionResponse(collision,p);
    if (!result||!result->applied) return std::nullopt;
    collision_force=GroundBoardCollisionResponse{result->force,result->point,result->angular_displacement};return collision_force;
}
void GroundRuntime::UpdateBodyAccumulator(BoardRuntime& board) {ApplyGroundBodyTorque(board.BodiesMut()[Deck].rates);}
void GroundRuntime::ApplyAngularTarget(BoardRuntime& board,Vec4 v) {ApplyDeckLimitedDisplacement(board.BodiesMut()[Deck].rates,XYZ(v));}
void GroundRuntime::ApplyAngularDisplacement(BoardRuntime& board,Vec4 v) {ApplyDeckAngularDisplacement(board.BodiesMut()[Deck].rates,XYZ(v));}
void GroundRuntime::SetAnimatedVelocity(BoardRuntime& board,Vec4 velocity)
{for (auto& body:board.BodiesMut()) body.rates.linear_velocity=XYZ(velocity);}
Vec4 GroundRuntime::BuildHangForce(const BoardRuntime& board,Vec4 start,Vec4 end) const
{return GroundHangForce(start,end,XYZW(board.PartTransforms()[Deck].translation));}
void GroundRuntime::ApplyHangForce(BoardRuntime& board,Vec4 force)
{const auto position=board.PartTransforms()[Deck].translation;GroundApplyWorldForce(board.BodiesMut()[Deck],position,XYZ(force),position);}
void GroundRuntime::PinToPosition(BoardRuntime& board,float x,float z,float dt)
{SetAnimatedVelocity(board,GroundPinningVelocity(XYZW(board.PartTransforms()[Deck].translation),x,z,dt));}
std::optional<GroundBoardOutcome> GroundRuntime::UpdateBoard(BoardRuntime& board,const WorldGeometry& world,
    const GroundSettings& settings,PhysicsGroundState& state,GroundControllers controllers,GroundBoardInput input,
    GroundPhysicalFrame physical,GroundBoardError& error)
{
    input.speed_wobble.activation_threshold=settings.wobble_activation;
    input.speed_wobble.amplitude_multiplier=settings.wobble_amplitude;
    auto queue=std::move(board.ForcesMut());board.ForcesMut()=BoardForceQueue{};
    std::array<InertiaDynamics,BoardBodyCount> inertias;
    std::array<std::size_t,BoardBodyCount> indices;
    for (std::size_t i=0;i<inertias.size();++i) {inertias[i]=board.Bodies()[i].inertia;indices[i]=i;}
    BodyInertias bindings{indices.data(),indices.size(),inertias.data(),inertias.size()};
    BoardServices services(*this,board,world,settings,physical);
    const auto result=UpdateGroundBoard(state,{controllers.speed_wobble,controllers.truck_steering,
        controllers.speed_model,controllers.manual,controllers.heading_previous,queue,bindings},settings.Board(),input,services,error);
    // Direct torque and velocity mutations remain live, including partial
    // failure. Only the detached drag field is copied back, then the queue.
    for (std::size_t i=0;i<inertias.size();++i) board.BodiesMut()[i].inertia.linear_drag=inertias[i].linear_drag;
    board.ForcesMut()=std::move(queue);
    return result;
}
}
