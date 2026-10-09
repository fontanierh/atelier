#include "GraphIntentOperations.h"
#include "GraphMotionSliding.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> in,out; std::size_t at = 0;
std::uint32_t R() { if (at+4 > in.size()) throw std::runtime_error("truncated input"); std::uint32_t v=0; for(unsigned i=0;i<4;++i)v|=std::uint32_t(in[at++])<<(8*i);return v; }
float F() { const auto bits=R();float v;std::memcpy(&v,&bits,4);return v; }
std::string S() { const auto size=R();if(at+size>in.size())throw std::runtime_error("truncated string");std::string v(reinterpret_cast<const char*>(in.data()+at),size);at+=size;return v; }
std::optional<float> O() { return R()!=0?std::optional<float>(F()):std::nullopt; }
void W(std::uint32_t v) {for(unsigned i=0;i<4;++i)out.push_back(std::uint8_t(v>>(8*i)));}
void V(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);W(bits);}
void V(std::optional<float> v) {W(bool(v));if(v)V(*v);}
void Text(std::string_view v) {W(std::uint32_t(v.size()));out.insert(out.end(),v.begin(),v.end());}
void Text(const std::string& v) { Text(std::string_view(v)); }
void Text(std::optional<std::string> v) {W(bool(v));if(v)Text(std::string_view(*v));}
void Bits(std::optional<std::uint32_t> v) {W(bool(v));if(v)W(*v);}
std::vector<GraphAttribute> Attributes()
{
    std::vector<GraphAttribute> a;const auto size=R();for(std::uint32_t i=0;i<size;++i){GraphAttribute v;v.name=S();v.text=S();v.float_bits=R();v.boolean_byte=std::uint8_t(R());a.push_back(v);}return a;
}
void Param(const ActionIntentParameter& p)
{
    Text(p.name);Text(p.mg_intent);Text(p.mg_intent_mag);Text(p.mg_intent_angle);Text(p.ag_intent);Text(p.text);
    Bits(p.float_bits);W(bool(p.boolean_byte));if(p.boolean_byte)W(*p.boolean_byte);V(p.default_value);V(p.scale);W(p.on_update);
    for(auto f:p.filters)W(f);W(p.angle_filter);W(p.negate_on_mirror);
}
void Mutation(IntentMutation v) {W(std::uint32_t(v.kind));if(v.kind==IntentMutation::Kind::Set)V(v.value);}
std::vector<std::uint8_t> ReadFile(const std::string& file) {std::ifstream source(file,std::ios::binary);if(!source)throw std::runtime_error("missing data");return {std::istreambuf_iterator<char>(source),{}};}
void Snapshot(const IntentMap& map,const std::vector<std::string>& names) {W(std::uint32_t(map.Size()));for(const auto& name:names){const auto v=map.Get(name);V(v?std::optional<float>(*v):std::nullopt);}}
}
int main(int argc,char** argv)
{
    try
    {
        if(argc<4)throw std::runtime_error("expected mode graph/settings assets arguments");
        const std::string mode=argv[1];std::string error;
        if(mode=="config")
        {
            Graph source;if(!source.Load(ReadFile(argv[2]),error))throw std::runtime_error(error);GraphBinding binding;if(!binding.Bind(source,error))throw std::runtime_error(error);
            std::vector<ActionIntentOperation> operations;if(!CompileActionIntentOperations(source,binding,operations,error))throw std::runtime_error(error);
            W(std::uint32_t(operations.size()));for(const auto& op:operations){Param(op.config);W(std::uint32_t(op.parameters.size()));for(const auto& p:op.parameters)Param(p);}
        }
        else
        {
            in.assign(std::istreambuf_iterator<char>(std::cin),{});const auto commands=R();
            SettingsDatabase settings;if(!settings.Load(ReadFile(argv[2]),error))throw std::runtime_error(error);
            GraphMotionSlidingSettings sliding;if(!sliding.Load(settings,error))throw std::runtime_error(error);
            for(std::uint32_t command=0;command<commands;++command)
            {
                const auto op=R();W(op);
                if(op==0)
                {
                    const auto attributes=Attributes();const auto numeric=ParseNumericCondition(GraphAttributes(attributes));
                    W(std::uint32_t(numeric.comparison));V(numeric.threshold);W(numeric.absolute);
                    const auto values=R();for(std::uint32_t i=0;i<values;++i)W(numeric.Matches(F()));
                }
                else if(op==1)
                {
                    const auto attributes=Attributes();Param(ParseActionIntentParameter(GraphAttributes(attributes)));
                    const auto filter=MotionIntentFilterOperation::Parse(GraphAttributes(attributes));Text(filter.intent);Text(filter.filtered_intent);
                    const auto& s=filter.settings;V(s.starting_value);V(s.default_value);V(s.scale);for(auto f:s.filters)W(f);
                    V(s.ramp_time);V(s.blend_rising);V(s.blend_falling);V(s.blend_out);V(s.clamp_velocity);V(s.clamp_acceleration);
                }
                else if(op==2)
                {
                    ConstMgIntentState constant;constant.value=F();constant.on_update=R()!=0;TimeMgIntentState time;time.elapsed=F();BoardAdjustIntentState board;
                    const auto steps=R();for(std::uint32_t i=0;i<steps;++i)
                    {
                        const auto phase=R();const auto value=O();const auto dt=F();Mutation(phase==0?constant.Begin():phase==1?constant.Update():constant.End());
                        if(phase==1)Mutation(time.Update(value,dt));else Mutation(time.End());V(time.elapsed);
                        const auto magnitude=O(),angle=O();const auto kind=R();const auto negate=R()!=0,mirror=R()!=0;
                        if(phase==0)board.Begin();const auto result=board.Update(magnitude,angle,kind,negate,mirror);W(bool(result));if(result){V(result->first);V(result->second);}
                    }
                }
                else if(op==3)
                {
                    const auto attributes=Attributes();const auto operation=MotionIntentFilterOperation::Parse(GraphAttributes(attributes));MotionIntentFilterState state;
                    IntentMap input,output;const auto size=R();std::vector<std::string> names;for(std::uint32_t i=0;i<size;++i)names.push_back(S());
                    const auto steps=R();for(std::uint32_t i=0;i<steps;++i)
                    {
                        const auto phase=std::uint8_t(R());const auto value=O();const auto dt=F();std::optional<std::uint32_t> flags;if(R())flags=R();
                        input.Clear();if(value)input.Insert(operation.intent,*value);std::string e;const auto ok=operation.Execute(phase,state,input,output,dt,flags,e);
                        W(ok);Text(e);V(state.elapsed);V(state.previous_delta);V(state.value);Snapshot(output,names);
                    }
                }
                else if(op==4)
                {
                    const auto attributes=Attributes();GraphCondition c;if(!ParseGraphCondition(GraphAttributes(attributes),false,c,error))throw std::runtime_error(error);
                    const auto category=R();const auto ground=R()!=0;const auto grind_name=S();const auto speed=F(),forward=F(),slope=F(),elapsed=F();
                    const auto mirror=R()!=0,fakie=R()!=0;const auto ground_y=F();const auto disable=R()!=0;const auto maximum=F();const auto present=R();
                    GraphConditionInputs inputs;
                    if(present&1)inputs.speeds=GraphSpeedInputs{speed,forward,slope};if(present&2)inputs.physical_state=GraphPhysicalStateInputs{category,ground,grind_name};
                    if(present&4)inputs.time_since_last_input=elapsed;if(present&8)inputs.mirrored=mirror;if(present&16)inputs.riding_fakie=fakie;
                    if(present&32)inputs.push_brake=GraphPushBrakeInputs{ground_y,disable,maximum};
                    IntentMap action;const auto count=R();for(std::uint32_t i=0;i<count;++i){const auto name=S();action.Insert(name,F());}
                    graph::Frame frame;const auto states=R();std::vector<std::optional<graph::Id>> parents;for(std::uint32_t i=0;i<states;++i){const auto p=R();parents.push_back(p==0xffffffff?std::nullopt:std::optional<graph::Id>(p));}
                    const auto current=R(),target=R();frame.current=current==0xffffffff?std::nullopt:std::optional<graph::Id>(current);c.target=target==0xffffffff?std::nullopt:std::optional<graph::Id>(target);
                    bool result=false;std::string e;W(c.Evaluate(inputs,action,{}, {},{},frame,parents,result,e));W(result);Text(e);
                }
                else if(op==5)
                {
                    GraphMotionSlidingState state;SlideLatch latch;for(auto& word:latch.words)word=R();float deceleration=F();const auto steps=R();
                    for(std::uint32_t i=0;i<steps;++i)
                    {
                        const auto category=R();const auto speed=F(),direction=F(),dt=F();IntentMap motion;
                        for(auto name:{"RightSlide","LeftSlide","RightSlideStart","LeftSlideStart"}){const auto value=O();if(value)motion.Insert(name,*value);}
                        state.Update(motion,category,speed,direction,dt,sliding,latch);for(auto word:latch.words)W(word);
                        for(bool right:{false,true}){const auto rv=motion.Get("RightSlide"),lv=motion.Get("LeftSlide");const auto values=CreateGraphMotionSlide(latch,right,rv?std::optional<float>(*rv):std::nullopt,lv?std::optional<float>(*lv):std::nullopt,sliding);for(auto v:values)V(v);}
                        Vec4 velocity,z;for(auto& v:velocity)v=F();for(auto& v:z)v=F();const auto flipped=R()!=0;V(GraphMotionSlideDirection(velocity,z,flipped));
                        Mat4 ground;for(auto& row:ground)for(auto& v:row)v=F();V(GraphMotionSlideDeceleration(deceleration,velocity,ground,sliding));V(GraphMotionSlideSpin(direction,sliding));
                    }
                }
                else if(op==6)
                {
                    if(argc<5)throw std::runtime_error("missing fixture graph");Graph source;if(!source.Load(ReadFile(argv[4]),error))throw std::runtime_error(error);
                    GraphBinding binding;if(!binding.Bind(source,error))throw std::runtime_error(error);CompiledGraph compiled;if(!compiled.FromBinding(binding,error))throw std::runtime_error(error);
                    ActionIntentGraphHost host;if(!host.FromGraph(source,binding,compiled,settings,error))throw std::runtime_error(error);graph::Controller controller(binding.states.size());
                    const auto size=R();std::vector<std::string> names;for(std::uint32_t i=0;i<size;++i)names.push_back(S());const auto steps=R();
                    for(std::uint32_t i=0;i<steps;++i)
                    {
                        const auto ending=R()!=0;const auto dt=F();host.action_intents.Clear();host.errors.clear();host.diagnostics_overflowed=false;
                        const auto count=R();for(std::uint32_t j=0;j<count;++j){const auto name=S();host.action_intents.Insert(name,F());}
                        const auto stance=R();host.stance=stance==0?std::nullopt:std::optional<Stance>(Stance{((stance-1)&1)!=0,((stance-1)&2)!=0});
                        const auto category=R();host.condition_inputs.physical_state=GraphPhysicalStateInputs{category,false,""};
                        const auto elapsed=O();host.condition_inputs.time_since_last_input=elapsed;
                        if(ending)controller.EndAllBehaviors(host);else controller.Update(compiled.program,dt,host);
                        V(controller.frame.dt);W(controller.frame.current.value_or(0xffffffff));W(controller.frame.last.value_or(0xffffffff));W(std::uint32_t(controller.frame.state_times.size()));for(auto t:controller.frame.state_times)V(t);
                        W(std::uint32_t(controller.active.size()));for(auto a:controller.active){W(a.behavior);W(a.instance);}Snapshot(host.motion_intents,names);Text(host.Diagnostics("|"));
                    }
                }
                else if(op==7)
                {
                    const auto attributes=Attributes();GraphCondition condition;
                    if(!ParseGraphCondition(GraphAttributes(attributes),false,condition,error))throw std::runtime_error(error);
                    std::vector<AnimationAttribute> cached;const auto count=R();
                    for(std::uint32_t i=0;i<count;++i)
                    {
                        AnimationAttribute a;a.name=EncodeAnimationName(S());const auto sequence=R();std::memcpy(&a.sequence_id,&sequence,4);a.kind=std::uint8_t(R());
                        for(auto& lane:a.payload)if(R())lane=R();cached.push_back(a);
                    }
                    GraphConditionInputs inputs;if(R()){inputs.physics_requests_dismount=R()!=0;inputs.physical_state_16=R();}
                    bool result=false;std::string e;const auto ok=condition.Evaluate(inputs,{},{},{},cached,{}, {},result,e);
                    W(ok&&result);Text(e);
                }
                else if(op==8)
                {
                    if(argc<5)throw std::runtime_error("missing fixture graph");Graph source;if(!source.Load(ReadFile(argv[4]),error))throw std::runtime_error(error);
                    GraphBinding binding;if(!binding.Bind(source,error))throw std::runtime_error(error);CompiledGraph compiled;if(!compiled.FromBinding(binding,error))throw std::runtime_error(error);
                    ActionIntentGraphHost host;if(!host.FromGraph(source,binding,compiled,settings,error))throw std::runtime_error(error);
                    const auto steps=R();for(std::uint32_t i=0;i<steps;++i)
                    {
                        graph::Frame frame;const auto current=R();frame.current=current==0xffffffff?std::nullopt:std::optional<graph::Id>(current);
                        const auto count=R();for(std::uint32_t j=0;j<count;++j)frame.state_times.push_back(O());host.errors.clear();host.diagnostics_overflowed=false;
                        W(std::uint32_t(compiled.operations.conditions.size()));for(std::uint32_t id=0;id<compiled.operations.conditions.size();++id)W(host.ConditionActivation(id,frame));Text(host.Diagnostics("|"));
                    }
                }
                else throw std::runtime_error("invalid operation");
            }
            if(at!=in.size())throw std::runtime_error("unconsumed input");
        }
        std::cout.write(reinterpret_cast<const char*>(out.data()),std::streamsize(out.size()));return std::cout?0:2;
    }
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
