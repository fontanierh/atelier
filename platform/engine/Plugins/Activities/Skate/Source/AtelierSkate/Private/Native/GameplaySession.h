// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GameplayWorld.h"
#include "SessionMarkerRuntime.h"
namespace atelier::skate
{
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
    bool Configure(std::string_view difficulty,bool goofy,float trucks,std::string& error);
    bool Tune(float pop,float spin,float speed,float power,std::string& error)
    {return gameplay->Tune(pop,spin,speed,power,error);}
    bool Activate(Vec3,float heading,std::string& error);
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
    bool AdvancePublished(std::string& error);
};
}
