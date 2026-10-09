#include "PlayerControls.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <cstdlib>
using namespace atelier::skate;
namespace {
std::vector<std::uint8_t> input,output;std::size_t at=0;
void Fail(const std::string& error){std::cerr<<error<<'\n';std::exit(2);}
std::uint32_t R(){if(at+4>input.size())Fail("truncated word");std::uint32_t v=0;for(unsigned i=0;i<4;++i)v|=std::uint32_t(input[at++])<<(8*i);return v;}
float F(){const auto w=R();float v;std::memcpy(&v,&w,4);return v;}
std::uint64_t U64(){const auto low=std::uint64_t(R());return low|(std::uint64_t(R())<<32);}
std::string S(){const auto n=R();if(n>input.size()-at)Fail("truncated string");std::string s(reinterpret_cast<const char*>(input.data()+at),n);at+=n;return s;}
void W(std::uint32_t v){for(unsigned i=0;i<4;++i)output.push_back(std::uint8_t(v>>(8*i)));}
void WF(float v){std::uint32_t w;std::memcpy(&w,&v,4);W(w);}
void WS(std::string_view s){W(std::uint32_t(s.size()));output.insert(output.end(),s.begin(),s.end());}
std::vector<std::uint8_t> File(const char* path){std::ifstream f(path,std::ios::binary);if(!f)Fail("missing native data");return {std::istreambuf_iterator<char>(f),{}};}
void Snapshot(const PlayerControls& p,const std::vector<std::string>& names){
  for(const auto v:p.controller.Words())W(v);W(bool(p.offboard_direction));if(p.offboard_direction)for(const auto v:*p.offboard_direction)WF(v);
  W(std::uint32_t(p.ticks));W(std::uint32_t(p.ticks>>32));W(p.actor_flags);W(p.bumper_state_502);W(p.bumper_state_104);W(p.preferences.automatic_push_enabled);W(p.preferences.automatic_push_right);
  W(std::uint32_t(p.intents.size()));for(const auto& v:p.intents){WS(v.name);WF(v.value);}W(std::uint32_t(p.action_intents.Size()));for(const auto& n:names){const auto v=p.action_intents.Get(n);W(v!=nullptr);if(v)WF(*v);}
}
struct Map final:ActionMap {
  std::array<float,18> values;std::array<std::uint8_t,18> states;std::vector<std::pair<std::uint32_t,std::uint32_t>> trace;
  void Read(){for(auto& v:values)v=F();for(auto& s:states)s=std::uint8_t(R());}
  float Value(std::uint32_t a) override{trace.emplace_back(0,a);return values.at(a-64);}
  std::uint8_t State(std::uint32_t a) override{trace.emplace_back(1,a);return states.at(a-64);}
};
void Frame(PhysicalPlayerInput& p,PhysicalSimulationSettings& f,AnimationProfile& profile,camera::CameraRuntime& c){
  p.state.category_12=R();p.state.state_16=R();p.off_board.flag_304=std::uint8_t(R());p.scoring.capabilities_204=R();f.board.step.simulation.time_step=F();f.board.input_magnitude_threshold=F();profile.physics_mode=R();const bool present=R()!=0;camera::CameraFrame frame;for(auto& axis:frame.basis.columns)for(auto& lane:axis)lane=F();if(present)c.frame=frame;else c.frame.reset();
}
}
int main(int argc,char** argv){
  if(argc!=3)Fail("expected settings and gestures");SettingsDatabase settings;std::string error;if(!settings.Load(File(argv[1]),error))Fail(error);std::vector<GestureSet> bank;if(!LoadGestureData(File(argv[2]),bank,error))Fail(error);
  input.assign(std::istreambuf_iterator<char>(std::cin),{});std::vector<std::string> names;for(auto n=R();n;--n)names.push_back(S());const auto commands=R();PlayerControls p;PhysicalPlayerInput physical;PhysicalSimulationSettings physics;AnimationProfile profile;camera::CameraRuntime camera;
  for(std::uint32_t i=0;i<commands;++i){const auto op=R();W(op);bool ok=true;error.clear();Map map;std::vector<std::uint32_t> extra;
    if(op==0){if(R()!=0){auto result=PlayerControls::Load(settings,bank,error);if(!result)Fail(error);p=std::move(*result);}else p=PlayerControls();}
    else if(op==1){p.actor_flags=R();p.bumper_state_502=R()!=0;p.bumper_state_104=R()!=0;p.preferences.automatic_push_enabled=R()!=0;p.preferences.automatic_push_right=R()!=0;p.ticks=U64();std::array<std::uint32_t,26> words;for(auto& v:words)v=R();p.controller=DerivedControllerInput(words);}
    else if(op==2){const float dt=F(),threshold=F();const auto caps=R();map.Read();p.Update(map,dt,threshold,caps);}
    else if(op==3){Frame(physical,physics,profile,camera);map.Read();ok=p.UpdateForPhysics(map,physical,physics,camera,error);}
    else if(op==4){map.Read();auto actions=p.SimulationActions(map);for(auto n=R();n;--n){const auto kind=R(),a=R();if(kind==0){const float value=actions.Value(a);std::uint32_t w;std::memcpy(&w,&value,4);extra.push_back(w);}else extra.push_back(actions.State(a));}}
    else if(op==5){const auto difficulty=R(),state=R();ok=p.PublishGestures(difficulty,state,error);}
    else if(op==6){const auto name=S();p.action_intents.Insert(name,F());}
    else if(op==7){Frame(physical,physics,profile,camera);const auto tick=U64();const bool available=R()!=0;std::array<float,18> values;for(auto& v:values)v=F();ok=p.Sample(TickInput(tick,GameplayActions(values),available),physical,physics,profile,camera,error);}
    else Fail("unknown operation");
    W(ok);WS(error);W(std::uint32_t(extra.size()));for(const auto v:extra)W(v);W(std::uint32_t(map.trace.size()));for(const auto& t:map.trace){W(t.first);W(t.second);}Snapshot(p,names);
  }
  if(at!=input.size())Fail("unconsumed input");std::cout.write(reinterpret_cast<const char*>(output.data()),std::streamsize(output.size()));return std::cout?0:2;
}
