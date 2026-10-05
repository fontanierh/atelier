// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GameplayWorld.h"
#include "SessionMarkerRuntime.h"
#include <cstdint>
namespace atelier::skate
{
// Host-only button; strip it before publishing the original Xbox pad.
inline constexpr std::uint16_t GameplayTransferButton=0x0800;
struct GameplayPose
{
    Mat4 root;
    std::vector<Mat4> bones;
    std::vector<std::string> names;
    std::optional<camera::CameraFrame> camera;
    Vec3 velocity;
    std::uint64_t tick;
    std::string state;
};
// Host-only: this session's successful pumps, which native neither names nor scores. A rise is a run of ground ticks
// whose pumping is active (pauses under a quarter second join it); it counts once, when the speed its intentional ticks
// added reaches minimum_gain (m/s). Coasting through a transition, a slope or a push adds none.
struct GameplayPumps
{
    float minimum_gain=0.5f;
    std::uint32_t count=0;
    float gain=0,last_gain=0,quiet=0;
    bool counted=false;
    void Observe(const GameplayRuntime&,float dt);
};
// Sole in-process session used by the Unreal adapter. The host elapsed clock
// selects whole ticks; GameplayRuntime owns the actual simulation timestep.
class GameplaySession
{
public:
    static bool Create(std::shared_ptr<const GameplayResources>,const GameplayWorldSnapshot&,
        Vec3 wheel_ground_anchor,float heading,std::unique_ptr<GameplaySession>& output,std::string& error);
    std::unique_ptr<GameplayRuntime> gameplay;
    ControllerInputRuntime input;
    SessionMarkerRuntime markers;
    GameplayPumps pumps;
    bool Configure(std::string_view difficulty,bool goofy,float trucks,std::string& error);
    bool Tune(float pop,float spin,float speed,float power,float vert_assist,std::string& error)
    {return gameplay->Tune(pop,spin,speed,power,vert_assist,error);}
    bool Tune(float pop,float spin,float speed,float power,std::string& error)
    {return Tune(pop,spin,speed,power,0.0f,error);}
    bool Feel(const FeelTuning& feel,std::string& error) {return gameplay->Feel(feel,error);}
    bool Activate(Vec3,float heading,std::string& error);
    // A session on no world, ticked once where nothing is: made ahead of a ride (on any thread), it takes a live
    // session's collision (AdoptWorld) and Activate places it, so no ride inherits another's state.
    static bool CreateBlank(std::shared_ptr<const GameplayResources>,std::unique_ptr<GameplaySession>& output,std::string& error);
    // Take over another session's installed collision and grind world (that session is left without).
    bool AdoptWorld(GameplaySession& from,std::string& error);
    void SuspendInput();
    void Collect(const std::array<DeviceSample,InputDeviceSlots>&,float dt);
    bool Advance(std::string& error);
    bool Tick(XboxState,std::string& error);
    bool Step(XboxState,float frame_interval,std::string& error);
    float Period() const;
    void SetAspectRatio(float);
    bool InstallCollision(PreparedGameplayWorld,std::string& error);
    GameplayPose Pose() const;
    bool ReferencePose(std::vector<Mat4>& output,std::string& error) const;
    bool CheckPublishedPose(std::string& error) const;
    void Launch(Vec3 velocity){gameplay->Launch(velocity);}
    float Elapsed() const{return elapsed_;}
private:
    float elapsed_=0;
    bool floor_seams_=false;   // the installed world's imported floor seams, which AdoptWorld carries over
    bool AdvancePublished(std::string& error);
};
}
