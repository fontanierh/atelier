// SPDX-License-Identifier: Apache-2.0
#include "OffboardGroundScene.h"
// WORLD_PROTOCOL
#include "DataReader.h"
#include <fstream>
namespace
{
OffboardGroundFrame ReadFrame(Reader& r){return {r.Vector(),r.Vector(),r.Vector(),r.Vector()};}
Mat4 ReadMatrix(Reader& r){Mat4 out{};for(auto& v:out)for(auto& x:v)x=r.Scalar();return out;}
Vec4 ReadVector4(Reader& r){return {r.Scalar(),r.Scalar(),r.Scalar(),r.Scalar()};}
OffboardGroundContext ReadContext(Reader& r){return {r.Word(),std::int32_t(r.Word())};}
OffboardGroundConsumeInput ReadConsume(Reader& r){return {ReadFrame(r),r.Vector(),r.Word(),r.Scalar(),r.Vector()};}
void FrameOut(Writer& o,OffboardGroundFrame f){o.Vector(f.right);o.Vector(f.up);o.Vector(f.forward);o.Vector(f.position);}
void ContextOut(Writer& o,OffboardGroundContext c){o.Word(c.selection_flags_2948);o.Word(std::uint32_t(c.matching_id_2952));}
void LineOut(Writer& o,OffboardGroundLine p){o.Vector(p.start);o.Vector(p.end);o.Scalar(p.radius);}
void PacketOut(Writer& o,const OffboardGroundPacket& p){ContextOut(o,p.context);o.Vector(p.center);o.Vector(p.up);o.Vector(p.tangent);for(const auto& l:p.lines)LineOut(o,l);}
void HitOut(Writer& o,const std::optional<OffboardGroundLineHit>& h){o.Word(h.has_value());if(h){o.Vector(h->position);o.Vector(h->face_normal);o.Scalar(h->fraction);o.Word(h->packed_surface);}}
void HitsOut(Writer& o,const std::array<std::optional<OffboardGroundLineHit>,7>& h){for(const auto& hit:h)HitOut(o,hit);}
void AdjustmentOut(Writer& o,const OffboardGroundAdjustment& a){o.Word(a.state_752);o.Word(a.state_753);o.Word(a.state_754);FrameOut(o,a.frame_768);o.Vector(a.input_up_416);}
void OwnerOut(Writer& o,const OffboardGroundGeometry& s){o.Scalar(s.collision_offset);o.Word(s.pending.has_value());if(s.pending){PacketOut(o,s.pending->first);HitsOut(o,s.pending->second);}}
void SearchOut(Writer& o,const OffboardGroundEdgeSearch& s){o.Vector(s.min);o.Vector(s.max);FrameOut(o,s.frame);ContextOut(o,s.context);o.Word(s.narrow_forward);}
void EdgesOut(Writer& o,const std::vector<OffboardGroundEdge>& e){o.Word(std::uint32_t(e.size()));for(const auto& x:e){o.Vector(x.start);o.Vector(x.end);}}
void SelectionOut(Writer& o,const std::optional<OffboardGroundEdgeSelection>& s){o.Word(s.has_value());if(s){o.Vector(s->edge.start);o.Vector(s->edge.end);o.Vector(s->closest);}}
void Status(Writer& o,bool okay,const std::string& error){o.Word(okay);o.Error(error.empty()?nullptr:error.c_str());}
struct WorldState{std::optional<WorldGeometry> value;std::string error;};
WorldState ReadWorld(Reader& r){const auto count=r.Word();std::vector<WorldTriangle> triangles;for(std::uint32_t n=0;n<count;++n)triangles.push_back(Cached(ReadTriangle(r)));const bool enabled=r.Word()!=0;auto metadata=Metadata(r);const char* error=nullptr;auto world=enabled?WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error):std::optional<WorldGeometry>(WorldGeometry(std::move(triangles)));return {std::move(world),error?error:""};}
struct Registry
{
    std::vector<OffboardGroundEdgeBody> bodies,dynamic,vehicles;std::vector<OffboardGroundAlternateRecord> alternates;std::vector<OffboardGroundIndexedBody> indexed;bool alternate=false;
    OffboardGroundEdgeSources Sources() const{return {dynamic,vehicles,alternates,indexed,alternate};}
};
Registry ReadRegistry(Reader& r)
{
    Registry out;const auto count=r.Word();out.bodies.reserve(count);
    for(std::uint32_t n=0;n<count;++n){OffboardGroundEdgeBody b;b.local_to_world=ReadFrame(r);b.local_bounds=r.Box();const auto segments=r.Word();for(std::uint32_t k=0;k<segments;++k)b.segments.push_back({{r.Vector(),r.Vector()},r.Box()});out.bodies.push_back(std::move(b));}
    auto count_indices=r.Word();for(std::uint32_t n=0;n<count_indices;++n)out.dynamic.push_back(out.bodies.at(r.Word()));
    count_indices=r.Word();for(std::uint32_t n=0;n<count_indices;++n)out.vehicles.push_back(out.bodies.at(r.Word()));
    const auto records=r.Word();for(std::uint32_t n=0;n<records;++n){OffboardGroundAlternateRecord a;a.enabled=r.Word()!=0;for(auto& c:a.choices){const bool exists=r.Word()!=0;const auto index=r.Word();const auto group=std::int32_t(r.Word());if(exists)c=std::make_pair(&out.bodies.at(index),group);}out.alternates.push_back(a);}
    const auto indexed=r.Word();for(std::uint32_t n=0;n<indexed;++n){const auto id=r.Word();const auto disabled=r.Word()!=0;const auto index=r.Word();out.indexed.push_back({id,disabled,&out.bodies.at(index)});}out.alternate=r.Word()!=0;return out;
}
std::vector<std::uint8_t> File(const char* path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
}
int main(int argc,char** argv)
{
    if(argc<2)return 2;SettingsDatabase data;std::string error;if(!data.Load(File(argv[1]),error))return 2;OffboardGroundGeometry initial;Writer header;const auto loaded=initial.Load(data,error);Status(header,loaded,error);if(loaded)OwnerOut(header,initial);for(auto w:header.words)Word(w);if(!loaded||argc>2)return std::cout?0:2;
    Reader input;input.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=input.Word();Word(count);
    for(std::uint32_t index=0;index<count;++index)
    {
        auto world=ReadWorld(input);const auto commands=input.Word();auto state=initial;Writer out;Status(out,world.value.has_value(),world.error);OwnerOut(out,state);out.Word(commands);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=input.Word();out.Word(op);error.clear();
            if(op==0){const auto frame=ReadMatrix(input);const auto velocity=ReadVector4(input);const auto context=ReadContext(input);const auto flags=input.Word();bool okay=false;if(world.value)okay=state.Submit(*world.value,frame,velocity,context,flags,error);else error=world.error;Status(out,okay,error);}
            else if(op==1)AdjustmentOut(out,state.Consume(ReadConsume(input)));else if(op==2)state.Reset();else if(op==3){world=ReadWorld(input);Status(out,world.value.has_value(),world.error);}
            else if(op==4)
            {
                const auto frame=ReadFrame(input);const auto context=ReadContext(input);const auto velocity=input.Vector();const auto flags=input.Word();auto registry=ReadRegistry(input);const auto search=SearchOffboardGroundEdges(frame,context,velocity,flags);SearchOut(out,search);
                const auto scene=world.value?OffboardGroundScene::Create(*world.value,registry.Sources(),error):std::nullopt;if(!world.value)error=world.error;Status(out,scene.has_value(),error);
                if(scene)
                {
                    const auto candidates=scene->EdgeCandidates(search);EdgesOut(out,candidates);const auto selected=SelectOffboardGroundEdge(search,candidates);SelectionOut(out,selected);
                    const auto packet=selected?PrepareOffboardGroundPacket(frame,context,*selected,state.collision_offset):std::nullopt;out.Word(packet.has_value());
                    if(packet){PacketOut(out,*packet);std::array<std::optional<OffboardGroundLineHit>,7> hits;const auto okay=scene->QueryLines(*packet,hits,error);Status(out,okay,error);if(okay)HitsOut(out,hits);}
                }
            }
            else if(op==5){const auto point=input.Vector();const OffboardGroundEdge edge{input.Vector(),input.Vector()};out.Vector(ClosestOffboardGroundEdgePoint(point,edge));}
            else Fail("Unknown offboard ground geometry operation");
            OwnerOut(out,state);
        }
        Word(index);Word(std::uint32_t(out.words.size()));for(auto w:out.words)Word(w);
    }
    return input.at==input.bytes.size()&&std::cout?0:2;
}
