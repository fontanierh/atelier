#include "OffboardGrabRuntime.h"
#include "OffboardGrabMath.h"
// WORLD_PROTOCOL
namespace
{
Vec4 V(Reader& r){return {r.Scalar(),r.Scalar(),r.Scalar(),r.Scalar()};}
Mat4 M(Reader& r){Mat4 m{};for(auto& v:m)v=V(r);return m;}
void VO(Writer& o,Vec4 v){for(const auto x:v)o.Scalar(x);}void MO(Writer& o,const Mat4& m){for(const auto& v:m)VO(o,v);}
void Status(Writer& o,bool okay,const std::string& error){o.Word(okay);o.Error(error.empty()?nullptr:error.c_str());}
OffboardGrabDescriptor Descriptor(Reader& r){return {r.Word(),r.Word()};}
OffboardGroundContext Context(Reader& r){return {r.Word(),std::int32_t(r.Word())};}
OffboardGrabQuery Query(Reader& r)
{OffboardGrabQuery q;q.position=V(r);q.sort_position=V(r);q.bounds_frame=M(r);q.bounds_extents=V(r);q.margin=r.Scalar();q.angle_a=r.Scalar();q.angle_b=r.Scalar();q.mode=r.Word();q.capacity=r.Word();q.selection_flags_2948=r.Word();q.matching_id_2952=std::int32_t(r.Word());return q;}
OffboardGrabLine Line(Reader& r){return {V(r),V(r),r.Scalar(),std::int32_t(r.Word()),r.Word(),std::uint8_t(r.Word()),r.Word()};}
std::shared_ptr<const OffboardGrabGeometry> Geometry(Reader& r)
{auto g=std::make_shared<OffboardGrabGeometry>();g->id=r.Word();auto count=r.Word();for(std::uint32_t n=0;n<count;++n)g->points.push_back(V(r));count=r.Word();for(std::uint32_t n=0;n<count;++n)g->approach_vectors.push_back(V(r));g->word_60=r.Word();return g;}
GrabObject Object(Reader& r)
{
    GrabObject o;o.id=r.Word();o.provider=r.Word()==0?GrabProvider::Dmo:GrabProvider::LivingWorld;o.selection_variant=std::uint8_t(r.Word());o.matching_group=std::int32_t(r.Word());o.record_enabled=r.Word()!=0;o.disabled=r.Word()!=0;o.assembly_ready=r.Word()!=0;
    if(r.Word()){GrabAssemblyData a;a.identity=r.Word();if(r.Word()){GrabPartData p;p.identity=r.Word();if(r.Word())p.rates=GrabRatesData{r.Word(),V(r),V(r)};for(auto& c:p.coefficients_0_to_36)c=r.Scalar();a.first_part=p;}o.assembly=a;}
    o.frame=M(r);o.object_vector_128=V(r);const auto count=r.Word();for(std::uint32_t n=0;n<count;++n){const auto descriptor=Descriptor(r);const auto geometry=Geometry(r);o.splines.push_back({descriptor,geometry,r.Word()});}return o;
}
struct WorldState{std::optional<WorldGeometry> value;std::string error;};
WorldState ReadWorld(Reader& r){const auto count=r.Word();std::vector<WorldTriangle> triangles;for(std::uint32_t n=0;n<count;++n)triangles.push_back(Cached(ReadTriangle(r)));const bool enabled=r.Word()!=0;auto metadata=Metadata(r);const char* error=nullptr;auto world=enabled?WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error):std::optional<WorldGeometry>(WorldGeometry(std::move(triangles)));return {std::move(world),error?error:""};}
struct RegistryState{std::optional<OffboardGrabRegistry> value;std::string error;};
RegistryState Registry(Reader& r,const WorldState& world)
{const auto count=r.Word();std::vector<GrabObject> objects;for(std::uint32_t n=0;n<count;++n)objects.push_back(Object(r));const auto nb=r.Word();std::vector<GrabMeshAssembly> bindings;for(std::uint32_t n=0;n<nb;++n)bindings.push_back({r.Word(),r.Word()});std::string error;auto registry=world.value?OffboardGrabRegistry::Create(*world.value,std::move(objects),std::move(bindings),error):std::nullopt;if(!world.value)error=world.error;return {std::move(registry),std::move(error)};}
void RecordOut(Writer& o,const OffboardGrabRecord& r)
{for(const auto w:r.words)o.Word(w);o.Word(r.geometry->id);o.Word(r.geometry->word_60);o.Word(std::uint32_t(r.geometry->points.size()));for(const auto& v:r.geometry->points)VO(o,v);o.Word(std::uint32_t(r.geometry->approach_vectors.size()));for(const auto& v:r.geometry->approach_vectors)VO(o,v);}
void RecordsOut(Writer& o,const std::vector<OffboardGrabRecord>& records){o.Word(std::uint32_t(records.size()));for(const auto& r:records)RecordOut(o,r);}
void RecordOption(Writer& o,const std::optional<OffboardGrabRecord>& r){o.Word(r.has_value());if(r)RecordOut(o,*r);}
void QueryOut(Writer& o,const OffboardGrabQuery& q){VO(o,q.position);VO(o,q.sort_position);MO(o,q.bounds_frame);VO(o,q.bounds_extents);o.Scalar(q.margin);o.Scalar(q.angle_a);o.Scalar(q.angle_b);o.Word(q.mode);o.Word(std::uint32_t(q.capacity));o.Word(q.selection_flags_2948);o.Word(std::uint32_t(q.matching_id_2952));}
void LineOut(Writer& o,const OffboardGrabLine& l){VO(o,l.start);VO(o,l.end);o.Scalar(l.radius);o.Word(std::uint32_t(l.group));o.Word(l.reject_flags);o.Word(l.source_pool_mask);o.Word(l.selection_flags);}
void HitOut(Writer& o,std::optional<OffboardGrabHit> h){o.Word(h.has_value());if(h){o.Scalar(h->fraction);o.Word(h->assembly.has_value());if(h->assembly)o.Word(*h->assembly);}}
void ObjectOption(Writer& o,std::optional<std::optional<std::uint32_t>> value){o.Word(value.has_value());if(value){o.Word(value->has_value());if(*value)o.Word(**value);}}
void OwnerOut(Writer& o,const OffboardGrabCache& c)
{
    const auto start=o.words.size();o.Word(0);o.Word(std::uint32_t(c.queries.size()));for(const auto& q:c.queries)QueryOut(o,q);o.Word(c.query_result.has_value());if(c.query_result)RecordsOut(o,*c.query_result);RecordsOut(o,c.pending);RecordsOut(o,c.validated);
    o.Word(c.validation.has_value());if(c.validation){o.Word(std::uint32_t(c.validation->size()));for(const auto& h:*c.validation)HitOut(o,h);}for(const auto d:c.requests){o.Word(d.has_value());if(d){o.Word(d->kind);o.Word(d->id);}}
    for(const auto& d:c.data)RecordOption(o,d);for(const auto d:c.data_ready)o.Word(d);o.Word(c.interactable_request.has_value());if(c.interactable_request)for(const auto& l:*c.interactable_request)LineOut(o,l);ObjectOption(o,c.interactable_result);o.Word(c.interactable_latched);o.Word(c.flags_12836);VO(o,c.query_position);VO(o,c.validation_position);o.words[start]=std::uint32_t(o.words.size()-start-1);
}
std::optional<OffboardGrabScene> Scene(const WorldState& world,const RegistryState& registry,std::string& error)
{if(!world.value){error=world.error;return std::nullopt;}if(!registry.value){error=registry.error;return std::nullopt;}error.clear();return OffboardGrabScene(*world.value,*registry.value);}
}
int main()
{
    Reader input;input.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=input.Word();Word(count);
    for(std::uint32_t index=0;index<count;++index)
    {
        auto world=ReadWorld(input);auto registry=Registry(input,world);const auto commands=input.Word();OffboardGrabCache cache;OffboardGrabRuntime owner(cache);Writer out;Status(out,world.value.has_value(),world.error);Status(out,registry.value.has_value(),registry.error);OwnerOut(out,cache);out.Word(commands);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=input.Word();out.Word(op);std::string error;
            if(op==0)owner.Query(Query(input));else if(op==1)owner.RequestPrimary(Descriptor(input));
            else if(op==2){const auto frame=M(input);owner.RequestInteractable(frame,Context(input));}
            else if(op==3||op==4){std::optional<OffboardGroundContext> ctx;if(op==4)ctx=Context(input);const auto scene=Scene(world,registry,error);const auto okay=scene&&(op==3?owner.ExecuteQueries(*scene,error):owner.Sync(*scene,*ctx,error));Status(out,okay,error);}
            else if(op==5){const auto p=owner.Publish();for(const auto& r:p.records)RecordOption(out,r);ObjectOption(out,p.object);}
            else if(op==6)owner.Invalidate();else if(op==7)owner.EnterReset();else if(op==8)RecordOption(out,owner.Best(V(input)));
            else if(op==9||op==10||op==11||op==15)
            {
                std::optional<OffboardGrabQuery> q;std::optional<OffboardGrabDescriptor> d;std::optional<OffboardGrabLine> l;Vec4 position{},extents{};Mat4 frame{};float margin=0,a=0,b=0;
                if(op==9)q=Query(input);else if(op==11)l=Line(input);else d=Descriptor(input);
                if(op==15){position=V(input);frame=M(input);extents=V(input);margin=input.Scalar();a=input.Scalar();b=input.Scalar();}
                const auto scene=Scene(world,registry,error);bool okay=false;std::vector<OffboardGrabRecord> records;std::optional<OffboardGrabRecord> record;std::optional<OffboardGrabHit> hit;
                if(scene){if(q)okay=scene->Query(*q,records,error);else if(l)okay=scene->Line(*l,hit,error);else okay=scene->Resolve(*d,record,error);}Status(out,okay,error);
                if(okay){if(op==9)RecordsOut(out,records);else if(op==10)RecordOption(out,record);else if(op==11){HitOut(out,hit);const auto id=hit?scene->EligibleObject(*hit):std::nullopt;out.Word(id.has_value());if(id)out.Word(*id);}else{out.Word(record.has_value());if(record)out.Word(QualifyGrabRecord(*record,position,frame,extents,margin,a,b));}}
            }
            else if(op==12){world=ReadWorld(input);Status(out,world.value.has_value(),world.error);}
            else if(op==13){registry=Registry(input,world);Status(out,registry.value.has_value(),registry.error);}
            else if(op==14){const auto i=input.Word();const auto frame=M(input);const auto okay=registry.value&&i<registry.value->objects.size();if(okay)registry.value->objects[i].frame=frame;else error="Fixture object index is unavailable";Status(out,okay,error);}
            else if(op==16){const auto position=V(input),a=V(input),b=V(input);VO(out,ClosestGrabPoint(position,{a,b}));}
            else return 2;OwnerOut(out,cache);
        }
        Word(index);Word(std::uint32_t(out.words.size()));for(const auto w:out.words)Word(w);
    }
    return input.at==input.bytes.size()&&std::cout?0:2;
}
