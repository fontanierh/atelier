// SPDX-License-Identifier: Apache-2.0
#include "OffboardStaticScene.h"
// WORLD_PROTOCOL
namespace
{
void V(Writer& out,Vec4 v){for(auto x:v)out.Scalar(x);}
void M(Writer& out,const Mat4& m){for(const auto& v:m)V(out,v);}
Vec4 ReadV(Reader& r){return {r.Scalar(),r.Scalar(),r.Scalar(),r.Scalar()};}
OffboardToolkitInput ReadInput(Reader& r){return {ReadV(r),ReadV(r),ReadV(r),ReadV(r),ReadV(r),ReadV(r),ReadV(r)};}
OffboardLineProbe ReadLine(Reader& r){return {ReadV(r),ReadV(r),r.Scalar()};}
AirTrajectoryQueryRequest ReadRequest(Reader& r){AirTrajectoryQueryRequest q;q.trajectory.position=ReadV(r);q.trajectory.velocity=ReadV(r);q.trajectory.acceleration=ReadV(r);q.trajectory.scalar_48=r.Scalar();q.radius=r.Scalar();q.start_error=r.Scalar();q.end_error=r.Scalar();return q;}
void LineOut(Writer& o,const OffboardLineProbe& p){V(o,p.start);V(o,p.end);o.Scalar(p.radius);}
void DescriptorOut(Writer& o,const OffboardProbeDescriptor& d){LineOut(o,d.line);o.Word(std::uint32_t(d.forward_index));o.Word(d.reverse_index.has_value());o.Word(std::uint32_t(d.reverse_index.value_or(0)));}
void DescriptorsOut(Writer& o,const std::vector<OffboardProbeDescriptor>& d){o.Word(std::uint32_t(d.size()));for(const auto& p:d)DescriptorOut(o,p);}
void LayoutOut(Writer& o,const OffboardProbeLayout& l){for(const auto& p:l.trajectories)LineOut(o,p);DescriptorsOut(o,l.secondary);DescriptorsOut(o,l.primary);}
void RequestOut(Writer& o,const AirTrajectoryQueryRequest& q){V(o,q.trajectory.position);V(o,q.trajectory.velocity);V(o,q.trajectory.acceleration);o.Scalar(q.trajectory.scalar_48);o.Scalar(q.radius);o.Scalar(q.start_error);o.Scalar(q.end_error);}
void BatchOut(Writer& o,const OffboardQueryBatch& b){V(o,b.input.position);V(o,b.input.forward);V(o,b.input.up);V(o,b.input.right);V(o,b.input.velocity);V(o,b.input.animation_up);V(o,b.input.animation_right);o.Word(std::uint32_t(b.matching_group));o.Word(b.mesh_reject_mask);for(const auto& q:b.trajectories)RequestOut(o,q);o.Word(std::uint32_t(b.lines.size()));for(const auto& p:b.lines)LineOut(o,p);DescriptorsOut(o,b.secondary);DescriptorsOut(o,b.primary);}
void QueryOut(Writer& o,const AirTrajectoryQueryResult& q){V(o,q.contact_position);V(o,q.contact_normal);V(o,q.landing_normal);o.Scalar(q.contact_time);M(o,q.contact_transform);o.Word(std::uint32_t(q.contact_frame));o.Word(q.surface);o.Word(q.geometry);}
void HitOut(Writer& o,const std::optional<OffboardLineHit>& hit){o.Word(hit.has_value());if(hit){V(o,hit->position);V(o,hit->normal);o.Scalar(hit->fraction);o.Word(hit->surface);M(o,hit->mesh_frame);o.Word(hit->geometry);}}
void LinesOut(Writer& o,const std::vector<std::optional<OffboardLineHit>>& hits){o.Word(std::uint32_t(hits.size()));for(const auto& h:hits)HitOut(o,h);}
void GroundLinesOut(Writer& o,const std::vector<std::optional<OffboardLineHit>>& hits){o.Word(std::uint32_t(hits.size()));for(const auto& h:hits){o.Word(h.has_value());if(h){o.Vector({h->position[0],h->position[1],h->position[2]});o.Vector({h->normal[0],h->normal[1],h->normal[2]});o.Scalar(h->fraction);o.Word(h->surface);}}}
void ResultsOut(Writer& o,const OffboardQueryResults& r){for(const auto& q:r.trajectories)QueryOut(o,q);LinesOut(o,r.lines);o.Word(std::uint32_t(r.edges.size()));for(const auto& e:r.edges){V(o,e[0]);V(o,e[1]);}}
void PrefixOut(Writer& o,const OffboardContactPrefix& p){V(o,p.position);V(o,p.normal);M(o,p.support_frame);V(o,p.target_position);V(o,p.target_normal);V(o,p.edge_position);V(o,p.edge_normal);o.Scalar(p.scalar_160);o.Word(p.kind_164);o.Scalar(p.distance_168);o.Scalar(p.distance_172);o.Word(p.flags_176);o.Word(p.support_180);}
void SampleOut(Writer& o,const OffboardContactSample& p){V(o,p.position);V(o,p.normal);o.Scalar(p.forward_distance);o.Scalar(p.height);o.Word(p.flags);o.Scalar(p.sort_distance);}
void SamplesOut(Writer& o,const OffboardContactSamples& s){o.Word(std::uint32_t(s.ground.size()));for(const auto& p:s.ground)SampleOut(o,p);o.Word(std::uint32_t(s.other.size()));for(const auto& p:s.other)SampleOut(o,p);o.Word(std::uint32_t(s.original_ground_count));}
void CollectedOut(Writer& o,const std::optional<OffboardCollectedContacts>& c){o.Word(c.has_value());if(c){BatchOut(o,c->batch);ResultsOut(o,c->results);PrefixOut(o,c->prefix);SamplesOut(o,c->samples);}}
void OwnerOut(Writer& o,const OffboardContactToolkit& s)
{
    LayoutOut(o,s.layout);o.Word(s.pending.has_value());if(s.pending){BatchOut(o,s.pending->first);ResultsOut(o,s.pending->second);}
    o.Word(s.readiness);PrefixOut(o,s.prefix);const auto& c=s.candidate;V(o,c.position);V(o,c.normal);V(o,c.direction);o.Word(c.flags);o.Scalar(c.low);o.Scalar(c.high);o.Scalar(c.order);o.Word(std::uint32_t(c.segment));o.Word(c.kind);
    o.Word(s.history.accepted);for(auto v:s.history.samples)o.Word(v);o.Word(std::uint32_t(s.history.cursor));
}
struct WorldState{std::optional<WorldGeometry> value;std::string error;};
WorldState ReadWorld(Reader& reader)
{
    const auto count=reader.Word();std::vector<WorldTriangle> triangles;for(std::uint32_t n=0;n<count;++n)triangles.push_back(Cached(ReadTriangle(reader)));
    const bool enabled=reader.Word()!=0;auto metadata=Metadata(reader);const char* error=nullptr;
    auto world=enabled?WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error):std::optional<WorldGeometry>(WorldGeometry(std::move(triangles)));
    return {std::move(world),error?error:""};
}
void Status(Writer& o,bool okay,const std::string& error){o.Word(okay);o.Error(error.empty()?nullptr:error.c_str());}
std::optional<OffboardStaticScene> Scene(const WorldState& state,std::string& error)
{if(!state.value){error=state.error;return std::nullopt;}return OffboardStaticScene::Create(*state.value,error);}
}
int main()
{
    Reader input;input.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=input.Word();
    for(std::uint32_t index=0;index<count;++index)
    {
        auto world=ReadWorld(input);const auto commands=input.Word();OffboardContactToolkit owner;Writer out;
        Status(out,world.value.has_value(),world.error);OwnerOut(out,owner);out.Word(commands);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=input.Word();out.Word(op);std::string error;
            if(op==0)owner.BeginInput();else if(op==1)owner.ResetHistory();else if(op==3)CollectedOut(out,owner.Refresh());
            else if(op==2||op==4)
            {
                const auto packet=ReadInput(input);const auto group=std::int32_t(input.Word());const auto scene=Scene(world,error);bool okay=false;
                if(op==2){if(scene)okay=owner.Submit(packet,group,*scene,error);Status(out,okay,error);}
                else {OffboardQueryResults results;if(scene)okay=scene->Execute(owner.layout.Prepare(packet,group),results,error);Status(out,okay,error);if(okay)ResultsOut(out,results);}
            }
            else if(op==5)
            {
                const auto num=input.Word();std::vector<OffboardLineProbe> requests;for(std::uint32_t k=0;k<num;++k)requests.push_back(ReadLine(input));const auto group=std::int32_t(input.Word());
                const auto scene=Scene(world,error);std::vector<std::optional<OffboardLineHit>> result;const auto okay=scene&&scene->Lines(requests,group,result,error);Status(out,okay,error);if(okay)GroundLinesOut(out,result);
            }
            else if(op==6)
            {
                const auto request=ReadRequest(input);const auto group=std::int32_t(input.Word());const auto reject=input.Word();const auto scene=Scene(world,error);AirTrajectoryQueryResult result;
                const auto okay=scene&&scene->Trajectory(request,group,reject,result,error);Status(out,okay,error);if(okay)QueryOut(out,result);
            }
            else if(op==7){world=ReadWorld(input);Status(out,world.value.has_value(),world.error);}
            else Fail("Unknown offboard contact operation");
            OwnerOut(out,owner);
        }
        Word(index);Word(std::uint32_t(out.words.size()));for(auto w:out.words)Word(w);
    }
    return input.at==input.bytes.size()&&std::cout?0:2;
}
