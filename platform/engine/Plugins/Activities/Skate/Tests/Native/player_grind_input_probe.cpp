// SPDX-License-Identifier: Apache-2.0
// Prefixed by the frozen world probe's declaration/transport adapters only.
#include "PlayerGrindMaterials.h"
#include <fstream>
struct Input:Reader
{
    float Float(){return Scalar();}std::uint64_t Wide(){const auto low=Word();return low|(std::uint64_t(Word())<<32);}
    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> a;for(auto& x:a)x=Word();return a;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& x:a)x=f(*this);return a;}
    template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>(f(*this)):std::nullopt;}
    std::string Text(){const auto n=Word();std::string s;for(unsigned j=0;j<n;++j)s+=char(Word());return s;}
};
struct Output:Writer
{
    void Float(float v){Scalar(v);}void Wide(std::uint64_t v){Word(std::uint32_t(v));Word(std::uint32_t(v>>32));}
};
// GENERATED_PROTOCOL
namespace
{
std::vector<std::uint8_t> File(const char* path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
PlayerGrindStaticProvider ReadProvider(Input& i)
{
    const auto rails=i.Word();for(unsigned n=0;n<rails;++n){i.Text();i.Word();const auto points=i.Word();for(unsigned p=0;p<points;++p)i.Vector();if(i.Word()){const auto words=i.Word();for(unsigned j=0;j<words;++j)i.Word();}}i.Text();
    PlayerGrindConvertedData d;const auto segments=i.Word();for(unsigned n=0;n<segments;++n){const auto start=i.Array<float,4>([](Input& r){return r.Float();}),end=i.Array<float,4>([](Input& r){return r.Float();});const auto owner=i.Wide();d.primitives.push_back({start,end,owner});
        const std::array<std::uint64_t,2> guids{i.Wide(),i.Wide()};const auto segment=i.Word(),flags=i.Word();d.metadata.push_back({guids,segment,flags});
        d.authored_bounds.push_back({i.Array<float,3>([](Input& r){return r.Float();}),i.Array<float,3>([](Input& r){return r.Float();})});d.source_rail_indices.push_back(i.Wide());}
    const auto guids=i.Word();for(unsigned n=0;n<guids;++n)d.rail_guids.push_back({i.Wide(),i.Wide()});
    const auto assets=i.Word();for(unsigned n=0;n<assets;++n){PlayerGrindConvertedAsset a;a.source={i.Text(),i.Text(),i.Wide(),i.Wide()};a.identity_transform_bounds=i.Word()!=0;const auto indices=i.Word();for(unsigned j=0;j<indices;++j)a.indices.push_back(i.Word());d.assets.push_back(std::move(a));}
    std::string error;auto provider=PlayerGrindStaticProvider::FromConverted(std::move(d),error);if(!provider)Fail(error.c_str());return std::move(*provider);
}
void ObserveProvider(Output& o,const PlayerGrindStaticProvider& p)
{
    o.Word(std::uint32_t(p.Primitives().size()));for(std::size_t index=0;index<p.Primitives().size();++index){const auto& edge=p.Primitives()[index];for(float v:edge.start)o.Float(v);for(float v:edge.end)o.Float(v);o.Wide(edge.owner);
        const auto* m=p.Metadata(index);if(!m)std::abort();for(auto v:m->spline_guids)o.Wide(v);o.Word(m->segment_index);o.Word(m->flags);
        const auto* b=p.AuthoredBounds(index);for(float v:b->min)o.Float(v);for(float v:b->max)o.Float(v);const auto* s=p.Source(index);o.Error(s->stream_file.c_str());o.Error(s->asset_id.c_str());o.Wide(s->section_index);o.Wide(s->section_offset);o.Wide(*p.SourceRailIndex(index));}
    std::vector<std::size_t> query;std::string error;if(!p.Query({-1.2f,-1.2f,-1.2f},{1.2f,1.2f,1.2f},query,error))Fail(error.c_str());o.Word(std::uint32_t(query.size()));for(auto index:query)o.Word(std::uint32_t(index));
}
WorldGeometry World(unsigned kind)
{
    std::vector<WorldTriangle> triangles;QueryMetadata metadata;metadata.island_flags=3;
    const std::array<Vec3,4> corners=kind==2?std::array<Vec3,4>{{{-.06f,-.05f,-4},{.06f,-.05f,-4},{.06f,-.05f,4},{-.06f,-.05f,4}}}:
        kind==3?std::array<Vec3,4>{{{0,-.05f,-4},{4,-.05f,-4},{4,-.05f,4},{0,-.05f,4}}}:
        kind==5?std::array<Vec3,4>{{{-4,-.05f,.34f},{4,-.05f,.34f},{4,-.05f,4},{-4,-.05f,4}}}:
        std::array<Vec3,4>{{{-4,-.05f,-4},{4,-.05f,-4},{4,-.05f,4},{-4,-.05f,4}}};
    if(kind){for(auto ids:{std::array<unsigned,3>{0,2,1},std::array<unsigned,3>{0,3,2}}){const std::array<Vec3,3> v{corners[ids[0]],corners[ids[1]],corners[ids[2]]};triangles.push_back({TriangleFromVolume(v,.25f,{1,1,1},0x10),{.8f,.6f,.1f},unsigned(triangles.size()+1)});metadata.packed_surfaces.push_back(std::uint16_t(kind==4?0x40b:0x20b));}
        QueryMesh mesh;mesh.triangle_range={0,triangles.size()};mesh.local_bounds={{-4,-.05f,-4},{4,-.05f,4}};mesh.matching_group=-1;mesh.rejection_flags=0xffffffffu;mesh.geometry=77;mesh.pool=kind==4?QueryPool::Conditional:QueryPool::Ground;metadata.meshes.push_back(mesh);}
    const char* error=nullptr;auto world=WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error);if(!world)Fail(error);return std::move(*world);
}
BoardRuntime Board()
{
    std::array<BodyMassProperties,7> masses{};for(auto& m:masses)m.dynamics={{1,1,1},1,1,100,100,0,0};std::array<AffineTransform,7> parts{};
    return BoardRuntime(masses,parts,AffineTransform{},SimulationStep::Fixed60Hz(8,.001f,{0,-9.81f,0}),BoardMotion::Active);
}
void ObserveMaterials(Output& o,const BoardRuntime& b,const BoardPhysicsSettings& s)
{o.Word(b.CollisionGroup());for(auto m:{s.collision.wheel_material,s.collision.truck_material,s.collision.deck_material}){o.Float(m.static_friction);o.Float(m.dynamic_friction);o.Float(m.restitution);}}
void ObservePlan(Output& o,const PlayerGrindInvestigation& p)
{for(auto v:{p.center,p.upmost_normal,p.direction})for(float x:v)o.Float(x);o.Word(std::uint32_t(p.probes.size()));for(const auto& probe:p.probes)Observe(o,probe);}
void ObservePending(Output& o,const PlayerGrindPending& p)
{
    Observe(o,p.fields);o.Word(bool(p.spline_guids));if(p.spline_guids){o.Word(1);for(auto v:*p.spline_guids)o.Wide(v);}o.Word(bool(p.geometry));
    if(p.geometry){const auto& g=*p.geometry;Observe(o,g.input);o.Word(bool(g.plan));if(g.plan)ObservePlan(o,*g.plan);for(const auto& h:g.hits){o.Word(bool(h));if(h)Observe(o,*h);}}
}
void ObserveObservation(Output& o,const PlayerGrindObservation& m)
{
    const auto& g=m.geometry;for(auto v:{g.point_1120,g.direction_1136,g.normal_1152,g.target_up_1168,g.primitive_start_1264,g.primitive_end_1280})for(float x:v)o.Float(x);
    o.Word(bool(g.spline_guids_1296));if(g.spline_guids_1296)for(auto v:*g.spline_guids_1296)o.Wide(v);
    for(auto v:{g.upmost_normal_1408,g.high_side_1440})for(float x:v)o.Float(x);o.Word(g.kind_1464);o.Word(g.flags_1476);o.Float(g.impact_speed_1492);
    const auto& s=m.surface;o.Word(s.audio_surface_1468);o.Word(s.material_1472);o.Float(s.friction_vs_time_1496);o.Float(s.reckon_blend_selector_1500);o.Float(s.gravity_relief_1512);
    const auto& c=m.control;o.Word(std::uint32_t(c.family));o.Word(c.flags_1516);o.Word(c.flags_2468);o.Word(c.flags_2488);o.Float(c.translation_2796);o.Float(c.balance_2800);o.Float(c.exit_lean);
    for(float v:m.engagement.velocity_1184)o.Float(v);o.Word(m.engagement.kind_1248);const auto& j=m.jumper;o.Word(j.geometry_kind_16);o.Word(std::uint32_t(j.family_20));o.Float(j.energy_24);for(auto v:{j.high_side_32,j.normal_48,j.direction_64,j.upmost_normal_80,j.point_96})for(float x:v)o.Float(x);
}
struct Host final:PlayerGrindInputHost
{
    PlayerGrindLiveHost live;Output trace;std::uint32_t fail,calls=0;
    Host(BoardRuntime& b,BoardPhysicsSettings& s,const PlayerGrindMaterials& m,unsigned f):live(b,s,m),fail(f){}
    bool Done(std::string& error){if(++calls==fail){error="injected callback "+std::to_string(calls);return false;}return true;}
    bool ApplyMaterialMode(PlayerGrindMaterialMode m,std::string& error)override{trace.Word(1);trace.Word(std::uint32_t(m));if(!live.ApplyMaterialMode(m,error))return false;return Done(error);}
    bool SurfaceProbe(const WorldGeometry& w,std::array<std::uint32_t,2> a,std::size_t index,PlayerGrindProbe p,std::optional<PlayerGrindProbeHit>& result,std::string& error)override
    {trace.Word(2);for(auto v:a)trace.Word(v);trace.Word(std::uint32_t(index));Observe(trace,p);std::optional<PlayerGrindProbeHit> h;if(!live.SurfaceProbe(w,a,index,p,h,error))return false;trace.Word(bool(h));if(h)Observe(trace,*h);if(!Done(error))return false;result=h;return true;}
    bool ForceExitLine(const WorldGeometry& w,std::array<std::uint32_t,2> a,PlayerGrindForceExitProbe p,std::optional<PlayerGrindForceExitHit>& result,std::string& error)override
    {trace.Word(3);for(auto v:a)trace.Word(v);for(auto v:{p.start,p.end})for(float x:v)trace.Float(x);std::optional<PlayerGrindForceExitHit> h;if(!live.ForceExitLine(w,a,p,h,error))return false;trace.Word(bool(h));if(h)for(float v:h->normal)trace.Float(v);if(!Done(error))return false;result=h;return true;}
};
}
int main(int argc,char** argv)
{
    if(argc!=2&&argc!=3)return 2;SettingsDatabase data;std::string error;if(!data.Load(File(argv[1]),error))Fail(error.c_str());Output out;
    if(argc==3){auto state=PlayerGrindInputState::Load(data,error);out.Word(bool(state));if(state){ObserveState(out,*state);const auto& s=state->Settings();for(const auto* g:{&s.friction,&s.slope_threshold,&s.vertical_help,&s.gravity_vertical,&s.gravity_linear}){for(float v:g->x)out.Float(v);for(float v:g->y)out.Float(v);}for(float v:s.exit_lean.x)out.Float(v);for(float v:s.exit_lean.y)out.Float(v);for(float v:{s.truck_to_wheel,s.deck_to_truck,s.test_above,s.test_below,s.max_impact})out.Float(v);}else out.Error(error.c_str());for(auto v:out.words)Word(v);return 0;}
    Input i;i.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=i.Word();
    for(unsigned c=0;c<count;++c){auto provider=ReadProvider(i);auto world=World(i.Word());auto board=Board();board.SetCollisionGroup(7);BoardPhysicsSettings settings;settings.standard_wheel_material={.8f,.5f,.03f};settings.collision.truck_material={.3f,.2f,.01f};settings.collision.deck_material={.6f,.4f,.02f};settings.collision.wheel_material=settings.standard_wheel_material;PlayerGrindMaterials materials(settings);auto value=PlayerGrindInputState::Load(data,error);if(!value)Fail(error.c_str());auto& state=*value;std::optional<PlayerGrindPending> pending;ProcessedPhysicsInput p;Output initial;ObserveProvider(initial,provider);ObserveState(initial,state);ObserveMaterials(initial,board,settings);out.Word(c);out.Word(std::uint32_t(initial.words.size()));out.words.insert(out.words.end(),initial.words.begin(),initial.words.end());const auto commands=i.Word();out.Word(commands);
        for(unsigned n=0;n<commands;++n){const auto op=i.Word();Output row;bool ok=true;error.clear();std::optional<PlayerGrindPostResult> result;Host host(board,settings,materials,0);
            if(op==0){p=ReadProcessedPhysicsInput(i);const auto context=ReadPreContext(i);host.fail=i.Word();ok=state.PreUpdate(p,provider,world,context,host,pending,error);}
            else if(op==1){p=ReadProcessedPhysicsInput(i);const auto context=ReadPostContext(i);host.fail=i.Word();if(pending){auto consumed=std::move(*pending);pending.reset();ok=state.PostUpdate(p,world,std::move(consumed),context,host,result,error);}else{ok=false;error="missing pre result";}}
            else if(op==2)state.Reset();else if(op==3)SeedState(i,state);else std::abort();
            row.Word(op);row.Word(ok);row.Error(error.c_str());row.Word(host.calls);row.Word(std::uint32_t(host.trace.words.size()));row.words.insert(row.words.end(),host.trace.words.begin(),host.trace.words.end());ObserveState(row,state);Observe(row,p);ObserveMaterials(row,board,settings);row.Word(bool(pending));if(pending)ObservePending(row,*pending);row.Word(bool(result));if(result){row.Word(std::uint32_t(result->wipeout_reasons.size()));for(auto reason:result->wipeout_reasons)row.Word(std::uint32_t(reason));ObserveObservation(row,result->observation);}out.Word(std::uint32_t(row.words.size()));out.words.insert(out.words.end(),row.words.begin(),row.words.end());
        }}if(i.at!=i.bytes.size())Fail("Input framing");for(auto v:out.words)Word(v);
}
