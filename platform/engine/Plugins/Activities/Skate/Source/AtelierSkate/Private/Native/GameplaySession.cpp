// SPDX-License-Identifier: Apache-2.0
#include "GameplaySession.h"
#include "ClimbingMath.h"
#include "DebugString.h"
#include <algorithm>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
// The host publishes affine matrices from the retained native XYZ columns.
// Internal animation matrices also carry weights in W; leave those untouched.
Mat4 PublishedMatrix(Mat4 matrix)
{
    matrix[0][3]=0.0f;matrix[1][3]=0.0f;matrix[2][3]=0.0f;matrix[3][3]=1.0f;
    return matrix;
}
}
bool GameplaySession::Create(std::shared_ptr<const GameplayResources> resources,
    const GameplayWorldSnapshot& snapshot,Vec3 anchor,float heading,
    std::unique_ptr<GameplaySession>& output,std::string& error)
{
    if(!resources){error="Skating session requires native resources";return false;}
    auto board=BoardPhysicsSettings::Load(resources->settings,error);if(!board)return false;
    std::optional<PreparedGameplayWorld> world;
    if(!BuildGameplayWorld(snapshot,board->floor_material,world,error))return false;
    AffineTransform spawn;
    spawn.translation={anchor.x,anchor.y+board->collision.wheel_radius-board->authored[0].translation.y,anchor.z};
    const float sine=std::sin(heading),cosine=std::cos(heading);
    spawn.basis.columns={{{cosine,0,-sine},{0,1,0},{sine,0,cosine}}};
    auto result=std::make_unique<GameplaySession>();
    const bool floor_seams=world->imported_floor_seams;
    if(!GameplayRuntime::Create(std::move(resources),std::move(world->collision),
        std::move(world->grind),spawn,"easy",result->gameplay,error))return false;
    if(floor_seams)result->gameplay->physical->EnableImportedFloorSeams();
    if(!result->markers.Load(result->gameplay->resources->settings,error))return false;
    output=std::move(result);error.clear();return true;
}
bool GameplaySession::Configure(std::string_view difficulty,bool goofy,float trucks,std::string& error)
{
    std::string lower(difficulty);
    for(char& c:lower)if(c>='A'&&c<='Z')c=char(c+('a'-'A'));
    const std::array<std::string_view,3> modes{"easy","normal","hardcore"};
    const auto found=std::find(modes.begin(),modes.end(),lower);
    if(found==modes.end())
    {
        std::string quoted;
        if(!FormatRustDebugString(difficulty,quoted,error))return false;
        error="Unknown difficulty "+quoted+"; expected easy, normal or hardcore";return false;
    }
    gameplay->profile.physics_mode=std::uint32_t(found-modes.begin());
    if(std::isfinite(trucks))
    {gameplay->profile.truck_tightness=std::clamp(trucks,0.0f,1.0f);gameplay->profile.wheel_hardness=0.5f;}
    gameplay->animation->SetCustomisation(std::uint32_t(goofy),0);
    error.clear();return true;
}
bool GameplaySession::Activate(Vec3 spawn,float heading,std::string& error)
{
    input=ControllerInputRuntime{};markers.Suspend();
    if(gameplay->physical->ticks==0 && !Tick({},error))return false;
    const climbing_math::Transform transform{spawn,climbing_math::RotationY(heading),{1,1,1}};
    auto frame=transform.ToMatrix();frame[3][3]=0;
    if(!gameplay->TravelTo(frame,error))return false;
    for(unsigned i=0;i<4;++i)if(!Tick({},error))return false;
    input=ControllerInputRuntime{};elapsed_=0;error.clear();return true;
}
void GameplaySession::SuspendInput()
{input=ControllerInputRuntime{};markers.Suspend();elapsed_=0;}
void GameplaySession::Collect(const std::array<DeviceSample,InputDeviceSlots>& samples,float dt)
{input.Collect(samples);markers.CollectTime(double(dt));}
bool GameplaySession::Advance(std::string& error)
{input.PublishActions();return AdvancePublished(error);}
bool GameplaySession::AdvancePublished(std::string& error)
{markers.Advance(input,*gameplay);return gameplay->Advance(input.PublishedInput(),error);}
bool GameplaySession::Tick(XboxState state,std::string& error)
{input.Sample(state);return AdvancePublished(error);}
float GameplaySession::Period() const
{return float(gameplay->clock.PeriodNanoseconds())/1000000000.0f;}
bool GameplaySession::Step(XboxState state,float dt,std::string& error)
{
    if(!std::isfinite(dt)||dt<0){error="Invalid frame interval";return false;}
    elapsed_=VectorMin(elapsed_+dt,0.1f);
    while(elapsed_+1.0e-7f>=Period())
    {elapsed_-=Period();if(!Tick(state,error))return false;}
    return CheckPublishedPose(error);
}
void GameplaySession::SetAspectRatio(float value)
{if(std::isfinite(value)&&value>0)gameplay->camera.SetAspectRatio(value);}
bool GameplaySession::InstallCollision(PreparedGameplayWorld world,std::string& error)
{
    const bool floor_seams=world.imported_floor_seams;
    if(!gameplay->InstallWorld(std::move(world.collision),std::move(world.grind),error))return false;
    if(floor_seams)gameplay->physical->EnableImportedFloorSeams();
    return true;
}
bool GameplaySession::ReferencePose(std::vector<Mat4>& output,std::string& error) const
{
    const auto& evaluator=*gameplay->resources->animation->evaluator;
    const auto* reference=evaluator.frames.NamedPose("RIG_TPOSE",error);if(!reference)return false;
    std::vector<Sqt> pose;pose.reserve(reference->samples.size());
    for(const auto& words:reference->samples)
        pose.push_back({{Scalar(words[0]),Scalar(words[1]),Scalar(words[2]),1},
            {Scalar(words[3]),Scalar(words[4]),Scalar(words[5]),Scalar(words[6])},
            {Scalar(words[7]),Scalar(words[8]),Scalar(words[9]),1}});
    if(!evaluator.Hierarchy(pose,output,error))return false;
    for(auto& matrix:output)matrix=PublishedMatrix(matrix);
    return true;
}
GameplayPose GameplaySession::Pose() const
{
    GameplayPose output;
    output.root=PublishedMatrix(gameplay->physical->roots.animation_to_world);
    output.bones.reserve(gameplay->render_pose.size());
    for(const auto& matrix:gameplay->render_pose)output.bones.push_back(PublishedMatrix(matrix));
    const auto& bones=gameplay->resources->animation->evaluator->frames.rig.bones;
    output.names.reserve(bones.size());
    for(const auto& bone:bones)output.names.push_back(bone.name);
    output.camera=gameplay->camera.frame;
    output.velocity=gameplay->physical->board.Bodies()[std::size_t(BoardBodyId::Deck)].rates.linear_velocity;
    output.tick=gameplay->physical->ticks;
    output.state=PhysicalStateName(gameplay->player_state->Current());
    return output;
}
bool GameplaySession::CheckPublishedPose(std::string& error) const
{
    const auto finite=[](const Mat4& m){for(const auto& row:m)for(float v:row)if(!std::isfinite(v))return false;return true;};
    const auto v=gameplay->physical->board.Bodies()[std::size_t(BoardBodyId::Deck)].rates.linear_velocity;
    if(!finite(PublishedMatrix(gameplay->physical->roots.animation_to_world))
        ||!std::isfinite(v.x)||!std::isfinite(v.y)||!std::isfinite(v.z)
        ||!std::all_of(gameplay->render_pose.begin(),gameplay->render_pose.end(),
            [&](const Mat4& m){return finite(PublishedMatrix(m));}))
    {error="The skating session produced a nonfinite pose";return false;}
    error.clear();return true;
}
}
