// SPDX-License-Identifier: Apache-2.0
#include "BipedFeet.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word(){if(bytes.size()-at<4)std::abort();std::uint32_t w=0;for(unsigned n=0;n<4;++n)w|=std::uint32_t(bytes[at++])<<(n*8);return w;}
    float Float(){const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& x:a)x=f(*this);return a;}
    template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>(f(*this)):std::nullopt;}
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w){words.push_back(w);}void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void Status(bool okay,const std::string& error){Word(okay);Word(std::uint32_t(error.size()));for(const unsigned char c:error)Word(c);}
    template<std::size_t N>void Curve(const PointGraph<N>& g){for(float f:g.x)Float(f);for(float f:g.y)Float(f);}
};
std::vector<std::uint8_t> File(const char* path){std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};}
// GENERATED_PROTOCOL
void IkOut(Output& o,const foot_ik::State& s)
{
 o.Word(s.feet_enabled);
 for(const auto& l:s.limbs){o.Word(std::uint32_t(l.mode));o.Float(l.board_blend);o.Float(l.external_blend);o.Float(l.target_blend);o.Word(l.external_target_set);o.Word(l.local_target_set);for(const auto& v:{l.external_target_local_delta,l.part_position})for(float x:v)o.Float(x);}
 for(const auto& f:s.frames){for(const auto& m:{f.target,f.world,f.external_world,f.board,f.parent_world,f.external_parent_world,f.parent_board})for(const auto& v:m)for(float x:v)o.Float(x);o.Word(f.within_contact_bounds);}
 for(const auto& t:s.external_targets)Observe(o,t);
 for(const auto& c:s.contacts.feet){o.Word(c.query_state);for(float x:c.position)o.Float(x);o.Float(c.desired_offset);o.Float(c.offset);}o.Word(s.contacts.support_failed);o.Word(s.contacts.support_failed_this_update);
}
void SeedIk(Input& i,foot_ik::State& s)
{
 s.EnableFeet(i.Word()!=0);
 for(auto& l:s.limbs){const auto mode=i.Word();if(mode>3)std::abort();l.mode=foot_ik::Mode(mode);l.board_blend=i.Float();l.external_blend=i.Float();l.target_blend=i.Float();l.external_target_set=i.Word()!=0;l.local_target_set=i.Word()!=0;l.external_target_local_delta=i.Array<float,4>([](Input& r){return r.Float();});l.part_position=i.Array<float,4>([](Input& r){return r.Float();});}
 for(auto& t:s.external_targets)t=ReadBipedExternalTarget(i);
}
void Snapshot(Output& o,const BoardPossessionManager& manager,const foot_ik::State& ik,OffBoardOutputFields& fields)
{const auto at=o.words.size();o.Word(0);Observe(o,manager);IkOut(o,ik);PublishBipedFeet(manager,fields);Observe(o,fields);o.words[at]=std::uint32_t(o.words.size()-at-1);}
void Raw(RawVector& v,Vec4 f){std::memcpy(v.data(),f.data(),16);}
void AirInput(Input& i,ProcessedPhysicsInput& p,SkeletonAnimationRecord& record,SkeletonRootFrames& roots)
{
 for(auto& f:record.pose)f=i.Array<Vec4,4>([](Input& r){return r.Array<float,4>([](Input& r){return r.Float();});});
 roots.animation_to_world=i.Array<Vec4,4>([](Input& r){return r.Array<float,4>([](Input& r){return r.Float();});});roots.world_to_animation=i.Array<Vec4,4>([](Input& r){return r.Array<float,4>([](Input& r){return r.Float();});});
 for(std::size_t n=0;n<2;++n){const auto l=ReadBipedFootLine(i);Raw(p.line_tests_960_1008_1056[n].position,l.position);Raw(p.line_tests_960_1008_1056[n].normal,l.normal);p.line_tests_960_1008_1056[n].surface=l.surface;p.line_tests_960_1008_1056[n].valid=std::uint8_t(l.valid);}
 Raw(p.vectors_544_560_592_608[2],i.Array<float,4>([](Input& r){return r.Float();}));Raw(p.vectors_544_560_592_608[3],i.Array<float,4>([](Input& r){return r.Float();}));p.flags_2476=i.Word();p.flags_2480=i.Word();p.flags_2484=i.Word();p.state_2508=i.Word();
}
int main()
{
 Input i;i.bytes={std::istreambuf_iterator<char>(std::cin),{}};Output o;const auto count=i.Word();o.Word(count);
 for(unsigned c=0;c<count;++c)
 {
  BoardPossessionManager manager;foot_ik::State ik;ProcessedPhysicsInput processed;SkeletonAnimationRecord record;SkeletonRootFrames roots;OffBoardOutputFields fields;fields.flag_329=171;fields.scalar_112=.137f;fields.vector_160={1,2,3,4};const auto n=i.Word();o.Word(c);o.Word(n);Snapshot(o,manager,ik,fields);
  for(unsigned k=0;k<n;++k)
  {
   const auto op=i.Word();o.Word(op);
   if(op==0){const auto targets=UpdateBipedFeetTargets(manager,ReadBipedFeetInput(i));for(const auto& t:targets)Observe(o,t);}
   else if(op==1)UpdateBipedGroundFeet(manager,ReadBipedFeetInput(i),ik);
   else if(op==2){AirInput(i,processed,record,roots);UpdateBipedAirFeet(manager,processed,record,roots,ik);}
   else if(op==3){processed.state_2504=i.Word();processed.state_2508=i.Word();EnterBipedAirFeet(manager,processed,ik);}
   else if(op==4){const auto index=i.Word();if(index>=4)return 2;SetBipedFootNormal(ik.external_targets[index],i.Array<float,4>([](Input& r){return r.Float();}));}
   else if(op==5){manager=ReadBoardPossessionManager(i);SeedIk(i,ik);}
   else if(op==6)manager.Reset();else if(op==7)ik.Reset();else return 2;
   Snapshot(o,manager,ik,fields);
  }
 }
 if(i.at!=i.bytes.size())return 2;for(auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));return std::cout?0:2;
}
