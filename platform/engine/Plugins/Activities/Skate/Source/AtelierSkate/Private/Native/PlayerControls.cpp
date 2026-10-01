// SPDX-License-Identifier: Apache-2.0
#include "PlayerControls.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::array<float,3> Cross(std::array<float,3> a,std::array<float,3> b)
{
  return {std::fma(-a[2],b[1],a[1]*b[2]),
    std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1])};
}
std::array<float,3> Normalize(std::array<float,3> v)
{
  const float squared=(v[0]*v[0]+v[1]*v[1])+v[2]*v[2];
  float inverse=1.0f/std::sqrt(squared);
  for(unsigned iteration=0;iteration<2;++iteration)
  {
    const float correction=std::fma(-squared,inverse*inverse,1.0f);
    inverse=std::fma(inverse*0.5f,correction,inverse);
  }
  for(auto& component:v)component*=inverse;
  return v;
}
}
StickPoint PlayerCameraRelativeAxes(StickPoint stick,const Basis3& camera)
{
  auto right=camera.columns[0],up=camera.columns[1],forward=camera.columns[2];
  if(std::abs(forward[1])<Float(0x3f7d70a4))
  {
    right=Normalize(Cross({0,1,0},forward));
    forward=Normalize(Cross(right,{0,1,0}));
    up=Normalize(Cross(forward,right));
  }
  const std::array<float,3> local{-stick[0],0,stick[1]};
  std::array<float,3> world;
  for(std::size_t i=0;i<3;++i)
    world[i]=std::fma(forward[i],local[2],std::fma(up[i],local[1],right[i]*local[0]));
  const float negative_x=world[0]>=0?0.0f:-world[0];
  const float positive_x=world[0]>0?world[0]:0.0f;
  const float negative_z=world[2]>=0?0.0f:-world[2];
  const float positive_z=world[2]<=0?0.0f:world[2];
  return {positive_x-negative_x,positive_z-negative_z};
}
float PlayerSimulationActions::Value(std::uint32_t action)
{
  if(offboard_axes_){if(action==64)return (*offboard_axes_)[0];if(action==65)return (*offboard_axes_)[1];}
  return source_.Value(action);
}
std::uint8_t PlayerSimulationActions::State(std::uint32_t action)
{
  if(offboard_axes_&&(action==64||action==65))return std::uint8_t(Value(action)!=0.0f);
  return source_.State(action);
}
PlayerControls::PlayerControls(){controller.Initialize();}
std::optional<PlayerControls> PlayerControls::Load(const SettingsDatabase& data,
  std::vector<GestureSet> bank,std::string& error)
{
  GestureInputPublication gestures;
  if(!gestures.Load(data,std::move(bank),error))return std::nullopt;
  PlayerControls result;result.gestures_=std::move(gestures);error.clear();return result;
}
void PlayerControls::Update(ActionMap& map,float dt,float magnitude_threshold,
  std::uint32_t physical_capabilities)
{
  offboard_axes_.reset();
  controller.Update(map,dt,bumper_state_502,bumper_state_104,{magnitude_threshold,0});
  intents=ProduceRiding(controller,actor_flags,preferences);
  const auto append=[this](std::vector<ControllerIntent> values)
    {intents.insert(intents.end(),values.begin(),values.end());};
  append(ProduceManual(controller,actor_flags));
  append(ProduceWipeout(controller,actor_flags,physical_capabilities));
  append(ProduceAnticipation(controller));append(ProduceTrick(controller));
  action_intents.Clear();
  for(const auto& intent:intents)action_intents.Insert(intent.name,intent.value);
  ++ticks;
}
bool PlayerControls::UpdateForPhysics(ActionMap& map,const PhysicalPlayerInput& physical,
  const PhysicalSimulationSettings& settings,const camera::CameraRuntime& camera,
  std::string& error)
{
  const bool remap=physical.state.category_12==500&&physical.off_board.flag_304==0
    &&physical.state.state_16!=503;
  std::optional<StickPoint> axes;
  if(remap)
  {
    if(!camera.frame){error="Native offboard input requires a completed presentation camera frame";return false;}
    // Rust evaluates source.value(64) before source.value(65).
    const float horizontal=map.Value(64);const float vertical=map.Value(65);
    axes=PlayerCameraRelativeAxes({horizontal,vertical},camera.frame->basis);
  }
  PlayerSimulationActions simulation(map,axes);
  Update(simulation,settings.board.step.simulation.time_step,
    settings.board.input_magnitude_threshold,physical.scoring.capabilities_204);
  offboard_axes_=axes;
  offboard_direction=axes?std::optional<Vec4>(Vec4{(*axes)[0],0,(*axes)[1],0}):std::nullopt;
  error.clear();return true;
}
bool PlayerControls::PublishGestures(std::uint32_t difficulty,std::uint32_t state,
  std::string& error)
{
  if(!gestures_){error.clear();return true;}
  const auto& words=controller.Words();
  const bool ok=gestures_->Publish({StickPoint{Float(words[7]),Float(words[8])},
    StickPoint{Float(words[9]),Float(words[10])}},difficulty,actor_flags,state,action_intents,error);
  if(ok)error.clear();
  return ok;
}
bool PlayerControls::Sample(const TickInput& input,const PhysicalPlayerInput& physical,
  const PhysicalSimulationSettings& settings,const AnimationProfile& profile,
  const camera::CameraRuntime& camera,std::string& error)
{
  auto actions=input.Actions();
  if(!UpdateForPhysics(actions,physical,settings,camera,error))
  {
    // Original Bevy sample() panics at this boundary. Preserve its exact
    // message as a failed native call; the coordinator must propagate it.
    error="Offboard controller publication: "+error;return false;
  }
  return PublishGestures(profile.physics_mode,physical.state.state_16,error);
}
} // namespace atelier::skate
