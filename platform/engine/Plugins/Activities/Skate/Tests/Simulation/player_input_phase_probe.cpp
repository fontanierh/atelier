#include "PlayerInputPhase.h"
#include "SkeletonPhysicalRecord.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    detail::DataReader r;explicit Input(const std::vector<std::uint8_t>& b):r{b} {r.at=0;}
    std::uint32_t Word(){return r.Word();}float Float(){return r.Float();}std::uint64_t Wide(){const auto lo=Word();return lo|(std::uint64_t(Word())<<32);}
    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> v;for(auto& x:v)x=Word();return v;}
    template<std::size_t N>std::array<float,N> Floats(){std::array<float,N> v;for(auto& x:v)x=Float();return v;}
    template<class T,std::size_t N,class C>std::array<T,N> Array(C callback){std::array<T,N> v;for(auto& x:v)x=callback(*this);return v;}
    template<class T,class C>std::optional<T> Optional(C callback){if(Word())return callback(*this);return std::nullopt;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;void Word(std::uint32_t w){for(unsigned i=0;i<4;++i)bytes.push_back(std::uint8_t(w>>(i*8)));}void Wide(std::uint64_t w){Word(std::uint32_t(w));Word(std::uint32_t(w>>32));}void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}void String(std::string_view s){Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}void Block(const Output& row){Word(std::uint32_t(row.bytes.size()/4));bytes.insert(bytes.end(),row.bytes.begin(),row.bytes.end());}
};
// GENERATED_PROTOCOL
struct Frame
{
    std::uint32_t fail=0,manager=0,pre_state=0,pre_category=0,teleport=0,teleport_state=0,teleport_category=0,query56=0,query44=0;
    bool available=false;float transition=0;RawVector position{};float body_speed=0;std::uint32_t skeleton_a=0,skeleton_b=0,skeleton_c=0;float spin=0,crouch=0;std::array<std::uint32_t,2> grind{};
    explicit Frame(Input& i){fail=i.Word();manager=i.Word();pre_state=i.Word();pre_category=i.Word();teleport=i.Word();teleport_state=i.Word();teleport_category=i.Word();query56=i.Word();query44=i.Word();available=i.Word()!=0;transition=i.Float();position=i.Words<4>();body_speed=i.Float();skeleton_a=i.Word();skeleton_b=i.Word();skeleton_c=i.Word();spin=i.Float();crouch=i.Float();grind=i.Words<2>();}
};
struct Services final:InputPhaseServices
{
    Frame frame;Output trace;std::uint32_t calls=0;explicit Services(Frame f):frame(f){}
    void Begin(std::uint32_t id,const PlayerInputState* p=nullptr,const PhysicalPlayerInput* f=nullptr,const ProcessedPhysicsInput* o=nullptr,const AnimationInputPacket* packet=nullptr){Output e;e.Word(id);e.Word((p?1:0)|(f?2:0)|(o?4:0)|(packet?8:0));if(p)Observe(e,*p);if(f)Observe(e,*f);if(o)Observe(e,*o);if(packet)Observe(e,*packet);trace.Block(e);++calls;}
    bool Done(std::string& error){if(frame.fail==calls){error="service "+std::to_string(calls);return false;}return true;}
    bool UpdatePreInputManager(PlayerInputState& p,PhysicalPlayerInput& f,std::string& e)override{Begin(1,&p,&f);++p.state_count_1312;if(frame.manager){f.state.state_16=frame.pre_state;f.state.category_12=frame.pre_category;}return Done(e);}
    bool ResetProcessedInput(ProcessedPhysicsInput& o,std::string& e)override{Begin(2,nullptr,nullptr,&o);ResetProcessedPhysicsInput(o);return Done(e);}
    bool ActorQuery56(std::uint32_t& value,std::string& e)override{Begin(3);value=frame.query56;return Done(e);}
    bool ActorQuery44(std::uint32_t& value,std::string& e)override{Begin(4);value=frame.query44;return Done(e);}
    bool ResetPlayerProbe(PlayerInputState& p,PhysicalPlayerInput& f,std::string& e)override{Begin(5,&p,&f);p.probe={};return Done(e);}
    bool CheckTeleport(PlayerInputState& p,PhysicalPlayerInput& f,ProcessedPhysicsInput& o,std::string& e)override{Begin(6,&p,&f,&o);if(frame.teleport){ResetPhysicalPlayerOutputs(f);f.state.state_16=frame.teleport_state;f.state.category_12=frame.teleport_category;p.flags_1296|=1u<<29;}return Done(e);}
    bool ActorInputAvailable(bool& value,std::string& e)override{Begin(7);value=frame.available;return Done(e);}
    bool TransitionAction(float& value,std::string& e)override{Begin(8);value=frame.transition;return Done(e);}
    bool CalculateGroundPosition(const PhysicalPlayerInput& f,RawVector& value,std::string& e)override{Begin(9,nullptr,&f);value=frame.position;return Done(e);}
    bool PrepareBoardToolkit(PlayerInputState& p,PhysicalPlayerInput& f,ProcessedPhysicsInput& o,std::string& e)override{Begin(10,&p,&f,&o);o.scalar_2616=frame.body_speed;return Done(e);}
    bool ProcessSkeleton(const AnimationInputPacket& packet,PhysicalPlayerInput& f,ProcessedPhysicsInput& o,std::string& e)override{Begin(11,nullptr,&f,&o,&packet);o.flags_2468|=frame.skeleton_a;o.flags_2472|=frame.skeleton_b;o.flags_2476|=frame.skeleton_c;o.spin_input_2672=frame.spin;o.crouch_2776=frame.crouch;return Done(e);}
    bool UpdateGrindManager(PlayerInputState& p,PhysicalPlayerInput& f,ProcessedPhysicsInput& o,std::string& e)override{Begin(12,&p,&f,&o);o.grind_words_2532_2536=frame.grind;return Done(e);}
};
std::vector<std::uint8_t> Read(std::string path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char**argv)
{
    if(argc!=2)return 2;SettingsDatabase data;std::string text;if(!data.Load(Read(argv[1]),text)){std::cerr<<text;return 2;}const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(bytes);Output out;const auto cases=i.Word();
    for(std::uint32_t c=0;c<cases;++c)
    {
        PlayerInputState p;if(!LoadPlayerInputState(data,p,text)){std::cerr<<text;return 2;}out.Word(c);Observe(out,p);p=ReadPlayerInputState(i);auto f=ReadPhysicalPlayerInput(i);auto o=ReadProcessedPhysicsInput(i);std::optional<InputContinuation> continuation;std::optional<ProcessedPhysicsSnapshot> completed;const auto commands=i.Word();
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=i.Word();InputPhaseError error;Output trace;std::uint32_t calls=0;bool ok=true;
            if(op<=2)
            {
                const auto tick=i.Wide();f=ReadPhysicalPlayerInput(i);auto publication=ReadAnimationPacketFields(i);auto external=ReadExternalPhysicsInput(i);auto packet=ReadPacket(i,publication,external);Services services{Frame(i)};
                if(op==0){ok=ProcessPlayerInputPhase(p,f,packet,o,services,error);if(ok)completed=ProcessedPhysicsSnapshot{tick,o};}
                else if(op==1){InputContinuation next;ok=StartPlayerInputPhase(p,f,packet,o,services,next,error);if(ok)continuation=next;}
                else{if(!continuation)return 2;const auto next=*continuation;continuation.reset();ok=FinishPlayerInputPhase(next,p,f,packet,o,services,error);if(ok)completed=ProcessedPhysicsSnapshot{tick,o};}
                trace=std::move(services.trace);calls=services.calls;
            }
            else if(op==3)ResetProcessedPhysicsInput(o);
            else if(op==4)ResetPhysicalPlayerOutputs(f);
            else if(op==5){const auto v=i.Floats<4>();const bool flipped=i.Word()!=0;f.skeleton.PublishDeckAngles(v,flipped);}
            else if(op==6){SkeletonPhysicalRecord record;record.pose[6][3]=i.Floats<4>();record.pose[10][3]=i.Floats<4>();const auto forward=i.Floats<4>(),up=i.Floats<4>();f.skeleton.PublishTwist(record,forward,up);}
            else if(op==7){const auto grind=i.Optional<AttributeName>([](Input& in){return in.Words<5>();}),surface=i.Optional<AttributeName>([](Input& in){return in.Words<5>();});f.grinds.ResetNames(grind,surface);}
            else return 2;
            out.Word(c);out.Word(n);out.Word(op);out.Word(ok);out.Word(std::uint32_t(error.kind));out.Word(error.state_variant);out.String(error.service);Output row;Observe(row,p);Observe(row,f);Observe(row,o);row.Word(bool(continuation));row.Word(bool(completed));if(completed){row.Wide(completed->tick);Observe(row,completed->input);}row.Word(calls);row.Block(trace);out.Block(row);
        }
    }
    if(!i.r.ok||i.r.at!=bytes.size())return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));
}
