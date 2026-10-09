// Test-only friends are appended to immutable snapshot headers by the checker.
#include "GameplayWorld.h"
#include "ControllerInputRuntime.h"
#include "WorldContactProducer.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    std::vector<std::uint8_t> data;std::size_t at=0;
    std::uint32_t Word(){if(at+4>data.size())std::abort();std::uint32_t v=0;for(unsigned n=0;n<4;++n)v|=std::uint32_t(data[at++])<<(n*8);return v;}
    std::uint64_t Wide(){const auto low=Word();return low|(std::uint64_t(Word())<<32);}
    float Float(){const auto word=Word();float v;std::memcpy(&v,&word,4);return v;}
    template<std::size_t N>std::array<float,N> Floats(){std::array<float,N> v;for(auto& x:v)x=Float();return v;}
    Vec3 Vector(){return {Float(),Float(),Float()};}
    Bounds Box(){return {Vector(),Vector()};}
    Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Float();return b;}
    ContactMaterial Material(){return {Float(),Float(),Float()};}
    XboxState Xbox(){XboxState s;s.buttons=std::uint16_t(Word());for(auto& v:s.triggers)v=std::uint8_t(Word());for(auto& v:s.left)v=std::int16_t(Word());for(auto& v:s.right)v=std::int16_t(Word());return s;}
    DeviceSample Sample(){const auto kind=Word();if(kind==0){DevicePacket p;p.number=Word();p.state=Xbox();p.subtype=std::uint8_t(Word());return p;}return DeviceError{DeviceError::Kind(kind-1),Word()};}
    GameplayWorldSnapshot Snapshot(){GameplayWorldSnapshot s;const auto n=Word();for(std::uint32_t j=0;j<n;++j)s.triangles.push_back({Vector(),Vector(),Vector()});const auto r=Word();for(std::uint32_t j=0;j<r;++j){std::vector<std::array<float,3>> rail;const auto k=Word();for(std::uint32_t p=0;p<k;++p)rail.push_back(Floats<3>());s.rails.push_back(std::move(rail));}return s;}
    ContactPrimitive Primitive(){switch(Word()){
        case 0:return Sphere{Vector(),Float()};
        case 1:return Capsule{Vector(),Vector(),Float(),Float()};
        case 2:{const std::array<Vec3,3> v{Vector(),Vector(),Vector()};const auto fat=Float();const auto cos=Floats<3>();const auto flags=Word();const AffineTransform t{Basis(),Vector()};return TransformTriangleVolume(v,fat,cos,flags,t);}
        case 3:return RoundedBox{Vector(),Basis(),Vector(),Float()};
        default:std::abort();}}
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t v){words.push_back(v);}void Wide(std::uint64_t v){Word(std::uint32_t(v));Word(std::uint32_t(v>>32));}
    void Float(float v){std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}
    template<std::size_t N>void Floats(const std::array<float,N>& v){for(auto x:v)Float(x);}
    void Vector(Vec3 v){Float(v.x);Float(v.y);Float(v.z);}void Box(Bounds b){Vector(b.min);Vector(b.max);}
    void Text(const std::string& v){Word(std::uint32_t(v.size()));for(unsigned char c:v)Word(c);}
    void Status(bool ok,const std::string& error){Word(ok);Text(error);}
    void Block(std::uint32_t tag,const Output& v){Word(tag);Word(std::uint32_t(v.words.size()));words.insert(words.end(),v.words.begin(),v.words.end());}
    void Transform(const AffineTransform& t){for(const auto& c:t.basis.columns)Floats(c);Vector(t.translation);}
    void TriangleOut(const WorldTriangle& w){const auto& t=w.triangle;for(auto v:t.vertices)Vector(v);Vector(t.feature.normal);for(auto e:t.feature.edges)Vector(e);Word(t.feature.flags);Floats(t.feature.edge_cosines);Floats(t.edge_lengths);Float(t.fatness);Float(w.material.static_friction);Float(w.material.dynamic_friction);Float(w.material.restitution);Word(w.tag);}
    void Metadata(const QueryMetadata& m){Word(std::uint32_t(m.packed_surfaces.size()));for(auto s:m.packed_surfaces)Word(s);Word(std::uint32_t(m.meshes.size()));for(const auto& q:m.meshes){Word(std::uint32_t(q.triangle_range.start));Word(std::uint32_t(q.triangle_range.end));Transform(q.local_to_world);Transform(q.world_to_local);Box(q.local_bounds);Word(std::uint32_t(q.matching_group));Word(q.rejection_flags);Word(q.geometry);Word(std::uint32_t(q.pool));}Word(std::uint32_t(m.static_edges.size()));for(const auto& e:m.static_edges){Vector(e.start);Vector(e.end);Box(e.local_bounds);}Word(m.island_flags);}
    void Hit(WorldLineQueryResult r){Status(!r.error,r.error?r.error:"");Word(r.hit.has_value());if(r.hit){Vector(r.hit->geometry.position);Vector(r.hit->geometry.normal);Float(r.hit->geometry.fraction);Floats(r.hit->geometry.volume_parameter);Word(r.hit->tag);}}
};
namespace atelier::skate
{
struct GameplayWorldInputObserver
{
    static void Record(Output& o,const HistoryRecord& r){o.Word(std::uint32_t(r.count));o.Floats(r.storage);}
    static void History(Output& o,const PadHistory& h){o.Word(std::uint32_t(h.read_));o.Word(std::uint32_t(h.write_));for(const auto& b:h.batches_)for(const auto& r:b)Record(o,r);}
    static void Clock(ControllerInputRuntime& c,std::uint64_t tick,std::uint64_t pub,std::uint64_t consumed){c.tick_=tick;c.publications=pub;c.consumed_batches=consumed;}
    static void Raw(Output& o,const RawInput& r){o.Word(r.buttons);o.Floats(r.triggers);o.Floats(r.left);o.Floats(r.right);}
    static void Actions(Output& o,GameplayActions a){for(std::uint32_t n=64;n<82;++n){o.Float(a.Value(n));o.Word(a.State(n));}}
    static void Controller(Output& o,const ControllerInputRuntime& c)
    {
        o.Wide(c.Tick());o.Wide(c.publications);o.Wide(c.consumed_batches);o.Word(std::uint32_t(c.ActiveCache()));
        for(const auto& r:c.Raw())Raw(o,r);for(const auto& b:c.Cache())for(const auto& r:b)Record(o,r);
        History(o,c.History());
        for(std::size_t n=0;n<InputDeviceSlots;++n){const auto& s=c.status[n];o.Word(std::uint32_t(s.kind));if(s.kind==ControllerStatus::Kind::Unavailable){o.Word(std::uint32_t(s.error.kind));o.Word(s.error.code);}o.Word(c.packet_numbers[n].has_value());if(c.packet_numbers[n])o.Word(*c.packet_numbers[n]);const auto& p=c.Pads()[n];o.Word(std::uint32_t(p.Count()));o.Word(std::uint32_t(p.Records().size()));for(const auto& r:p.Records())for(auto w:r)o.Word(w);o.Floats(c.mapped_actions[n]);Actions(o,GameplayActions::FromPad(p));}
        auto tick=c.PublishedInput();o.Wide(tick.Tick());o.Word(tick.ControllerAvailable());Actions(o,tick.Actions());Actions(o,c.PlayerActions());Raw(o,c.CurrentRawInput());for(auto b:c.SessionMarkerActions())o.Word(b);
    }
};
}
void ProviderOut(Output& o,const PlayerGrindStaticProvider& p)
{
    const auto& primitives=p.Primitives();o.Word(std::uint32_t(primitives.size()));
    for(std::size_t n=0;n<primitives.size();++n){const auto& v=primitives[n];o.Floats(v.start);o.Floats(v.end);o.Wide(v.owner);const auto* m=p.Metadata(n);o.Word(m!=nullptr);if(m){for(auto g:m->spline_guids)o.Wide(g);o.Word(m->segment_index);o.Word(m->flags);}const auto guids=p.SplineGuids(v.owner);o.Word(guids.has_value());if(guids)for(auto g:*guids)o.Wide(g);const auto* s=p.Source(n);o.Word(s!=nullptr);if(s){o.Text(s->stream_file);o.Text(s->asset_id);o.Wide(s->section_index);o.Wide(s->section_offset);}const auto rail=p.SourceRailIndex(n);o.Word(rail.has_value());if(rail)o.Wide(*rail);const auto* b=p.AuthoredBounds(n);o.Word(b!=nullptr);if(b){o.Floats(b->min);o.Floats(b->max);}}
    // Include lookup behavior beyond the valid owner/index range.
    for(auto owner:{std::uint64_t(0),std::uint64_t(1),std::uint64_t(2),std::uint64_t(0xffffffff),UINT64_MAX}){const auto g=p.SplineGuids(owner);o.Word(g.has_value());if(g)for(auto v:*g)o.Wide(v);}
    for(auto n:{primitives.size(),primitives.size()+1}){o.Word(p.Metadata(n)!=nullptr);o.Word(p.Source(n)!=nullptr);o.Word(p.SourceRailIndex(n).has_value());o.Word(p.AuthoredBounds(n)!=nullptr);}
}
void WorldOut(Output& o,const std::optional<PreparedGameplayWorld>& p)
{
    o.Word(p.has_value());if(!p)return;o.Word(p->imported_floor_seams);const auto& w=p->collision;o.Word(std::uint32_t(w.Triangles().size()));for(const auto& t:w.Triangles())o.TriangleOut(t);const char* e=nullptr;const auto* m=w.Metadata(e);o.Status(m!=nullptr,e?e:"");if(m)o.Metadata(*m);o.Float(w.MaximumFatness());o.Word(std::uint32_t(w.TriangleBounds().size()));for(auto b:w.TriangleBounds())o.Box(b);ProviderOut(o,*p->grind);
}
void Query(Input& i,Output& o,const std::optional<PreparedGameplayWorld>& prepared)
{
    const auto start=i.Vector(),end=i.Vector();const auto radius=i.Float();const bool has=i.Word()!=0;const auto box=i.Box();const auto min=i.Floats<3>(),max=i.Floats<3>();
    if(!prepared){o.Status(false,"Fixture has no prepared world");return;}o.Status(true,"");const auto& w=prepared->collision;const auto b=w.LineCandidateBounds(start,end,radius);o.Word(b.has_value());if(b)o.Box(*b);const auto ranges=w.CandidateRanges(has?std::optional<Bounds>(box):std::nullopt);o.Word(std::uint32_t(ranges.size()));for(auto r:ranges){o.Word(std::uint32_t(r.start));o.Word(std::uint32_t(r.end));}const auto candidates=w.LineCandidates(start,end,radius);o.Word(std::uint32_t(candidates.size()));for(auto n:candidates)o.Word(std::uint32_t(n));const auto meshes=w.CandidateMeshIndices(has?std::optional<Bounds>(box):std::nullopt);o.Status(!meshes.error,meshes.error?meshes.error:"");o.Word(std::uint32_t(meshes.indices.size()));for(auto n:meshes.indices)o.Word(std::uint32_t(n));o.Hit(w.QueryThinLine(start,end));o.Hit(w.QuerySweptLine(start,end,radius));std::vector<std::size_t> ids;std::string error;const bool ok=prepared->grind->Query(min,max,ids,error);o.Status(ok,error);o.Word(std::uint32_t(ids.size()));for(auto n:ids)o.Word(std::uint32_t(n));
}
void Contacts(Input& i,Output& o,const std::optional<PreparedGameplayWorld>& prepared,WorldContactProducer& producer)
{
    std::vector<BoardWorldVolume> v;const auto n=i.Word();for(std::uint32_t j=0;j<n;++j){const auto body=i.Word();const auto primitive=i.Primitive();const auto velocity=i.Vector();v.push_back({body,primitive,velocity,i.Material()});}const WorldContactSettings q{i.Float(),i.Float(),i.Float(),i.Float(),i.Word()!=0};const ContactRetentionSettings r{i.Word(),i.Float(),i.Word()!=0};if(!prepared){o.Status(false,"Fixture has no prepared world");return;}o.Status(true,"");const auto& c=producer.QueryPrimitives(prepared->collision,v,q,r);o.Word(producer.DroppedContacts());o.Word(std::uint32_t(c.size()));for(const auto& row:c)for(auto w:row)o.Word(w);
}
int main()
{
    Input i;i.data.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=i.Word();Output total;
    for(std::uint32_t index=0;index<count;++index){const auto kind=i.Word();const auto commands=i.Word();Output body;body.Word(commands);
        ControllerInputRuntime c;std::optional<PreparedGameplayWorld> world;WorldContactProducer producer;
        for(std::uint32_t n=0;n<commands;++n){const auto op=i.Word();Output row,result;
            if(kind==0){switch(op){case 0:{const auto material=i.Material();const auto source=i.Snapshot();std::string error;const bool ok=BuildGameplayWorld(source,material,world,error);result.Status(ok,error);if(ok){producer=WorldContactProducer{};if(world->imported_floor_seams)producer.EnableImportedFloorSeams();}break;}case 1:Query(i,result,world);break;case 2:Contacts(i,result,world,producer);break;case 3:world.reset();producer=WorldContactProducer{};result.Status(true,"");break;case 4:result.Status(true,"");break;default:std::abort();}Output snapshot;WorldOut(snapshot,world);row.Block(0,result);row.Block(1,snapshot);}
            else if(kind==1){switch(op){case 0:{std::array<DeviceSample,InputDeviceSlots> samples;for(auto& s:samples)s=i.Sample();c.Collect(samples);result.Word(1);break;}case 1:result.Word(c.PublishActions());break;case 2:c.DiscardGameplay();result.Word(1);break;case 3:c.Sample(i.Xbox());result.Word(1);break;case 4:{const auto tick=i.Wide(),pub=i.Wide(),consumed=i.Wide();GameplayWorldInputObserver::Clock(c,tick,pub,consumed);result.Word(1);break;}case 5:result.Word(1);break;default:std::abort();}Output snapshot;GameplayWorldInputObserver::Controller(snapshot,c);row.Block(0,result);row.Block(1,snapshot);}else std::abort();body.Word(n);body.Word(op);body.Word(std::uint32_t(row.words.size()));body.words.insert(body.words.end(),row.words.begin(),row.words.end());}
        total.Word(index);total.Word(kind);total.Word(std::uint32_t(body.words.size()));total.words.insert(total.words.end(),body.words.begin(),body.words.end());}
    if(i.at!=i.data.size())std::abort();for(auto word:total.words)for(unsigned n=0;n<4;++n)std::cout.put(char(word>>(n*8)));
}
