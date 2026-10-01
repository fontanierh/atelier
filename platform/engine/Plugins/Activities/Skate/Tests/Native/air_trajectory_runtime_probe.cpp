// SPDX-License-Identifier: Apache-2.0
// Shared probe declarations and independent converted-provider transport are
// prefixed by the checker; the full root runtime executes every owner method.
#include "AirTrajectoryRuntime.h"
#include <memory>
[[noreturn]] void Fail(const char* e){std::cerr<<e<<'\n';std::exit(2);}
struct Input
{
    std::uint32_t Word(){return ::Word();}
    float Float(){return ::Float();}
    std::uint64_t Wide(){const auto low=Word();return low|(std::uint64_t(Word())<<32);}
    Vec3 Vector(){const float x=Float(),y=Float(),z=Float();return {x,y,z};}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& x:a)x=f(*this);return a;}
    std::string Text(){const auto n=Word();std::string s;for(unsigned i=0;i<n;++i)s+=char(Word());return s;}
};
struct Output
{
    std::vector<std::uint32_t>& words;
    void Word(std::uint32_t v){words.push_back(v);}
    void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void Wide(std::uint64_t v){Word(std::uint32_t(v));Word(std::uint32_t(v>>32));}
    void Error(const char* e){const auto n=e?std::strlen(e):0;Word(std::uint32_t(n));for(std::size_t i=0;i<n;++i)Word(static_cast<unsigned char>(e[i]));}
};
// GENERATED_PROVIDER_TRANSPORT
namespace {
void ObserveGrindSettings(const AirTrajectoryGrindRuntime& g)
{
    const auto& l=g.limits;Out(l.lock_distance);Out(l.max_speed_squared_ledge);Out(l.max_speed_squared_rail);Out(l.max_downward_speed);
    for(auto f:l.ledge_scalars)Out(f);Out(l.tip_scalar);Out(l.maximum_adjust_angle);for(auto f:l.deck_dimensions)Out(f);
    Graph(g.height);for(float f:{g.padding,g.maximum_adjust,g.velocity_scalar,g.max_angle,g.score,g.truck_distance,g.penalty_domain})Out(f);
}
void ObserveRuntime(const AirTrajectoryRuntime& r)
{
    Observe(r.selector);Settings(r.settings);Out(std::uint32_t(r.PendingResults().has_value()));
    if(r.PendingResults()){Out(std::uint32_t(r.PendingResults()->size()));for(const auto& v:*r.PendingResults())Result(v);}
    ObserveGrindSettings(r.GrindSettings());Out(std::uint32_t(bool(r.GrindWorld())));
    if(r.GrindWorld()){Output out{output};ObserveProvider(out,*r.GrindWorld());}
    Out(std::uint32_t(r.NearbyGrinds().size()));for(auto i:r.NearbyGrinds())Out(std::uint32_t(i));
}
AirTrajectoryGrindContext ReadContext()
{
    const auto board=Vector(),body=Vector();const auto actor=Word(),matching=Word();ProcessedPhysicsInput p;
    for(std::size_t i=0;i<4;++i)std::memcpy(&p.vectors_544_560_592_608[2][i],&body[i],4);
    p.actor_query_2948=actor;p.actor_query_2952=matching;return AirTrajectoryGrindContext::FromProcessed(p,board);
}
void MutateSettings(AirTrajectoryRuntime& r,std::uint32_t field,std::uint32_t word)
{
    float v;std::memcpy(&v,&word,4);auto& s=r.settings;
    switch(field){case 0:s.trajectory_radius=v;break;case 1:s.minimum_valid_time=v;break;case 2:std::memcpy(&s.minimum_trajectory_frames,&word,4);break;case 3:s.minimum_normal_delta_second_pass=v;break;case 4:s.trajectory_max_time=v;break;case 5:s.trajectory_error_start=v;break;case 6:s.trajectory_error_end=v;break;case 7:s.cone_x_second_pass=v;break;case 8:s.cone_z_second_pass=v;break;case 9:s.score_middle_bonus=v;break;case 10:s.maximum_trajectory_adjust=v;break;case 11:s.wall_ride_minimum_height=v;break;case 12:s.trajectory_max_drop=v;break;case 13:s.vert_jump_align_max_ground_normal_y=v;break;case 14:s.speed_factor_min=v;break;case 15:s.speed_factor_max=v;break;default:std::abort();}
}
WorldGeometry RuntimeWorld(unsigned kind)
{
    if(kind<6)return World(kind);auto w=World(kind==8?2:1);
    if(kind==6)return WorldGeometry(w.Triangles());const char* e=nullptr;const auto* m=w.Metadata(e);if(!m)std::abort();auto metadata=*m;
    if(kind==7)for(auto& mesh:metadata.meshes)mesh.matching_group=17;
    if(kind==8){metadata.island_flags=0;for(auto& mesh:metadata.meshes)mesh.pool=QueryPool::Conditional;}
    auto result=WorldGeometry::WithQueryMetadata(w.Triangles(),std::move(metadata),e);if(!result)Fail(e);return std::move(*result);
}
}
int main(int argc,char** argv)
{
    if(argc!=2)return 2;std::ifstream file(argv[1],std::ios::binary);std::vector<std::uint8_t> bank(std::istreambuf_iterator<char>(file),{});SettingsDatabase database;std::string error;if(!database.Load(bank,error))Fail(error.c_str());
    std::vector<unsigned char> bytes(std::istreambuf_iterator<char>(std::cin),{});if(bytes.size()%4)return 2;for(std::size_t at=0;at<bytes.size();at+=4)input.push_back(std::uint32_t(bytes[at])|(std::uint32_t(bytes[at+1])<<8)|(std::uint32_t(bytes[at+2])<<16)|(std::uint32_t(bytes[at+3])<<24));Input reader;const auto count=Word();
    for(unsigned index=0;index<count;++index){AirTrajectoryRuntime runtime;error.clear();const bool loaded=runtime.Load(database,error);Out(index);const auto case_mark=output.size();Out(0u);Status(loaded,error);if(!loaded){if(count!=1)std::abort();output[case_mark]=std::uint32_t(output.size()-case_mark-1);continue;}
        auto world=RuntimeWorld(Word());const auto initial=output.size();Out(0u);ObserveRuntime(runtime);output[initial]=std::uint32_t(output.size()-initial-1);const auto commands=Word();Out(commands);
        for(unsigned j=0;j<commands;++j){const auto op=Word();Out(op);const auto mark=output.size();Out(0u);bool ok=true,value=true;error.clear();
            if(op==0){const auto info=ReadLaunch();const auto in=ReadSelectorInput();ok=runtime.Launch(info,in,world,value,error);}
            else if(op==1){const auto in=ReadSelectorInput();const auto context=ReadContext();ok=runtime.Update(in,world,context,value,error);}
            else if(op==2)runtime.selector.Reset();
            else if(op==3)runtime.selector.CancelPending();
            else if(op==4)value=runtime.selector.UpdateWithoutCompletion();
            else if(op==5)runtime.BindGrindWorld(std::make_shared<PlayerGrindStaticProvider>(ReadProvider(reader)));
            else if(op==6){const auto field=Word(),word=Word();MutateSettings(runtime,field,word);}
            else if(op==7)world=RuntimeWorld(Word());
            else if(op==8){const auto q=ReadRequest();auto result=AirTrajectoryQueryResult::Miss();ok=AirTrajectoryRuntime::Query(world,q,result,error);Status(ok,error);Result(result);}
            else if(op==9){const auto normal=Vector(),velocity=Vector();const float direction=Float();Out(AirTrajectoryVertDepartureNormal(normal,velocity,direction));}
            else std::abort();Status(ok,error);Out(std::uint32_t(value));const auto state_mark=output.size();Out(0u);ObserveRuntime(runtime);output[state_mark]=std::uint32_t(output.size()-state_mark-1);output[mark]=std::uint32_t(output.size()-mark-1);
        }output[case_mark]=std::uint32_t(output.size()-case_mark-1);
    }if(cursor!=input.size())return 2;for(auto w:output)for(unsigned i=0;i<4;++i)std::cout.put(static_cast<char>(w>>(8*i)));
}
