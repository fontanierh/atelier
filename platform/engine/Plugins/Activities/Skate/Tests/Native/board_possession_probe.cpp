// SPDX-License-Identifier: Apache-2.0
#include "BoardPossession.h"
#include "BoardPossessionManager.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> out;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){auto w=Word();float x;std::memcpy(&x,&w,4);return x;}
Vec4 Vector(){return {Float(),Float(),Float(),Float()};}
Mat4 Matrix(){Mat4 m;for(auto& v:m)v=Vector();return m;}
void Out(std::uint32_t w){out.push_back(w);}
void Out(float x){std::uint32_t w;std::memcpy(&w,&x,4);Out(w);}
template<class T,std::size_t N>void Out(const std::array<T,N>& v){for(const auto& x:v)Out(x);}
void Out(BoardPossessionFill f){Out(f.angle_36);Out(f.angle_40);for(bool b:{f.held_311,f.free_312,f.returning_313,f.hiding_321,f.flag_322,f.flag_323,f.flag_324})Out(std::uint32_t(b));}
void Out(const BoardPossessionState& s)
{
    const auto& r=s.retrieval;Out(r.initial_0);Out(r.target_64);Out(r.current_128);for(float x:{r.elapsed_192,r.duration_196,r.progress_200,r.weight_204})Out(x);
    for(const auto& h:s.hands){Out(h.child);Out(h.parent);Out(h.dynamics);}Out(s.selected_hand_424);
}
void Out(SkateboardControllerFields f){Out(f.word_444);Out(f.state_448);Out(std::uint32_t(f.system_on_452));}
SkateboardControllerFields Fields(){const auto word=Word(),state=Word(),enabled=Word();return {word,state,enabled!=0};}
BoardPossessionState State()
{
    BoardPossessionState s;auto& r=s.retrieval;r.initial_0=Matrix();r.target_64=Matrix();r.current_128=Matrix();r.elapsed_192=Float();r.duration_196=Float();r.progress_200=Float();r.weight_204=Float();
    for(auto& h:s.hands){h.child=Matrix();h.parent=Matrix();for(auto& d:h.dynamics)for(auto& x:d)x=Word();}s.selected_hand_424=Word();return s;
}
PointGraph<8> Graph(){PointGraph<8> g;for(auto& x:g.x)x=Float();for(auto& y:g.y)y=Float();return g;}
BoardPossessionSettings Settings()
{
    BoardPossessionSettings s;s.hide_distance=Float();s.hide_offset=Float();s.return_distance=Float();s.mounted_return_distance=Float();s.mounting_time=Float();s.retrieval_time=Graph();s.retrieval_weight=Graph();s.throw_pitch=Float();s.throw_velocity=Graph();s.throw_target_pitch=Float();s.throw_pitch_scalar=Float();s.throw_roll_scalar=Float();s.throw_yaw_scalar=Float();return s;
}
BoardPossessionObservation Observation()
{
    BoardPossessionObservation o;auto& p=o.processed;p.board_frame_64=Matrix();p.player_frame_192=Matrix();p.position_592=Vector();p.velocity_912=Vector();p.direction_400=Vector();p.hide_direction_464=Vector();p.flags_2476=Word();p.flags_2480=Word();p.flags_2488=Word();
    o.board_collision_flags_872=Word();o.board_state_840=Word();for(auto& x:o.hand_contacts)x=Word()!=0;for(auto& x:o.physical_hand_positions)x=Vector();o.animation_board_frame_12624=Matrix();for(auto& x:o.animation_hand_frames)x=Matrix();o.attachment_frame_0=Matrix();return o;
}
struct Recorder : BoardPossessionEffects
{
    std::vector<std::uint32_t> events;
    void Call(std::uint32_t op){events.push_back(op);events.push_back(0);}
    template<class T>void Call(std::uint32_t op,const T& value){const auto start=out.size();Out(value);events.push_back(op);events.push_back(static_cast<std::uint32_t>(out.size()-start));events.insert(events.end(),out.begin()+static_cast<std::ptrdiff_t>(start),out.end());out.resize(start);}
    void EnableAnimationSoft() override{Call(0);}void EnableAnimationAngularOnly() override{Call(1);}void DisableAnimation() override{Call(2);}void DisableLinearDrive() override{Call(3);}void StandardBoard() override{Call(4);}void ReleasedBoard() override{Call(5);}void CollisionVolumes(bool b) override{Call(6,std::uint32_t(b));}void ClearAlignment() override{Call(7);}
    void Alignment(BoardPossessionAlignment a) override{const auto start=out.size();Out(a.first_1008);Out(a.second_1024);Out(a.factor_1040);Out(std::uint32_t(a.flag_1044));events.push_back(8);events.push_back(10);events.insert(events.end(),out.begin()+static_cast<std::ptrdiff_t>(start),out.end());out.resize(start);}
    void Velocity(Vec4 v) override{Call(9,v);}void Position(Vec4 v) override{Call(10,v);}void HookFrame(Mat4 m) override{Call(11,m);}void TargetPositionVelocity(Vec4 v) override{Call(12,v);}void Torque(Vec4 v) override{Call(13,v);}
};
void Out(BoardPossessionManager m)
{
    for(auto h:m.hands){Out(h.vectors_0_to_64);Out(h.word_80);Out(std::uint32_t(h.flag_84));Out(h.scalars_96_100);for(bool b:h.flags_104_to_107)Out(std::uint32_t(b));}
    Out(m.vectors_224_to_272);Out(m.scalars_288_to_296);Out(m.word_300);for(bool b:m.flags_304_to_307)Out(std::uint32_t(b));Out(m.words_308_to_316);
}
BoardPossessionManager Manager()
{
    BoardPossessionManager m;for(auto& h:m.hands){for(auto& v:h.vectors_0_to_64)v=Vector();h.word_80=Word();h.flag_84=Word()!=0;for(auto& x:h.scalars_96_100)x=Float();for(auto& b:h.flags_104_to_107)b=Word()!=0;}
    for(auto& v:m.vectors_224_to_272)v=Vector();for(auto& x:m.scalars_288_to_296)x=Float();m.word_300=Word();for(auto& b:m.flags_304_to_307)b=Word()!=0;for(auto& w:m.words_308_to_316)w=Word();return m;
}
}
int main()
{
    const auto count=Word();for(std::uint32_t index=0;index<count;++index)
    {
        const auto s=Settings();auto f=Fields();auto state=Word()?State():BoardPossessionState{};auto o=Observation();Recorder e;const auto commands=Word();Out(index);Out(commands);const auto mark=out.size();Out(0u);const auto start=out.size();Out(f);Out(state);
        for(std::uint32_t i=0;i<commands;++i)
        {
            const auto op=Word();Out(op);const auto command_mark=out.size();Out(0u);const auto command_start=out.size();e.events.clear();switch(op)
            {
            case 0:f=Fields();break;case 1:o=Observation();break;case 2:state.Update(f,o,s,e);break;case 3:state.Hold(f,o,e);break;
            case 4:state.LetGo(f,o,s,e);break;case 5:state.Stop(f,o,s,e);break;case 6:state.Hide(o,e);break;case 7:state.Retrieve(f,o,s,e);break;
            case 8:state.UpdateState(f,o,s,e);break;case 9:state.UpdateDriveFrames(o);break;case 10:state.DisableHand();break;
            case 11:Out(FillBoardPossession(f,state,o.processed,Matrix()));break;
            case 12:{const auto request=Vector(),omega=Vector();std::array<Vec4,3> inertia;for(auto& v:inertia)v=Vector();Out(BoardThrowVelocity(o.processed,s));Out(BoardThrowTorques(o.processed,s));Out(BoardPossessionAngularAcceleration(request,omega,inertia));break;}
            case 13:state=State();break;
            case 14:f.word_444=0;state.Stop(f,o,s,e);state.retrieval={};break;
            case 15:{auto manager=Manager();const auto previous=Word(),current=Word();bool enabled=Word()!=0;auto a=Vector(),b=Vector();std::array<std::uint32_t,4> words;for(auto& w:words)w=Word();manager.Enter(previous,current,{enabled,a,b,words});Out(manager);Out(std::uint32_t(enabled));Out(a);Out(b);Out(words);break;}
            case 16:{auto manager=Manager();manager.Reset();Out(manager);break;}
            default:return 2;
            }
            Out(static_cast<std::uint32_t>(e.events.size()));for(auto w:e.events)Out(w);Out(f);Out(state);out[command_mark]=static_cast<std::uint32_t>(out.size()-command_start);
        }out[mark]=static_cast<std::uint32_t>(out.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:out){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
