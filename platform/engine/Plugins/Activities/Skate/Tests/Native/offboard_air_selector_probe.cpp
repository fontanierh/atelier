#include "OffboardAirSelector.h"
#include "OffboardAirMath.h"
#include "OffboardStaticScene.h"
// WORLD_PROTOCOL
#include <fstream>
namespace
{
Vec4 V(Reader& r){return {r.Scalar(),r.Scalar(),r.Scalar(),r.Scalar()};}
Mat4 M(Reader& r){Mat4 m{};for(auto& v:m)v=V(r);return m;}
AirTrajectory T(Reader& r){return {V(r),V(r),V(r),r.Scalar()};}
OffboardAirContext Context(Reader& r){return {r.Word(),std::int32_t(r.Word()),V(r),V(r)};}
OffboardAirLaunchPacket Packet(Reader& r)
{OffboardAirLaunchPacket p;p.velocity_0=V(r);p.secondary_velocity_16=V(r);p.position_32=V(r);p.up_48=V(r);p.forward_64=V(r);p.board_position_80=V(r);p.scalar_96=r.Scalar();p.scalar_100=r.Scalar();p.scalar_104=r.Scalar();p.kind_108=r.Word();p.kind_112=r.Word();p.has_board_position_116=r.Word()!=0;p.flag_117=r.Word()!=0;return p;}
OffboardAirLaunchInput LaunchInput(Reader& r)
{
    OffboardAirLaunchInput p;p.board_position_112=V(r);p.forward_224=V(r);p.up_544=V(r);p.position_592=V(r);p.velocity_608=V(r);p.velocity_912=V(r);
    if(r.Word())p.departure_geometry=OffboardDepartureGeometry{V(r),V(r)};p.flags_2472=r.Word();p.flags_2476=r.Word();p.flags_2480=r.Word();p.previous_state_2504=r.Word();p.current_state_2508=r.Word();p.current_category_2512=r.Word();p.previous_category_2516=r.Word();p.raw_x_2692=r.Scalar();p.raw_z_2688=r.Scalar();return p;
}
void VO(Writer& o,Vec4 v){for(const auto x:v)o.Scalar(x);}void MO(Writer& o,const Mat4& m){for(const auto& v:m)VO(o,v);}
void TO(Writer& o,AirTrajectory t){VO(o,t.position);VO(o,t.velocity);VO(o,t.acceleration);o.Scalar(t.scalar_48);}
void QO(Writer& o,AirTrajectoryQueryResult q){VO(o,q.contact_position);VO(o,q.contact_normal);VO(o,q.landing_normal);o.Scalar(q.contact_time);MO(o,q.contact_transform);o.Word(std::uint32_t(q.contact_frame));o.Word(q.surface);o.Word(q.geometry);}
void RequestOut(Writer& o,AirTrajectoryQueryRequest q){TO(o,q.trajectory);o.Scalar(q.radius);o.Scalar(q.start_error);o.Scalar(q.end_error);}
void PredictionOut(Writer& o,OffboardAirPrediction p){QO(o,p.result);RequestOut(o,p.request);}
void PacketOut(Writer& o,const OffboardAirLaunchPacket& p)
{for(const auto& v:{p.velocity_0,p.secondary_velocity_16,p.position_32,p.up_48,p.forward_64,p.board_position_80})VO(o,v);o.Scalar(p.scalar_96);o.Scalar(p.scalar_100);o.Scalar(p.scalar_104);o.Word(p.kind_108);o.Word(p.kind_112);o.Word(p.has_board_position_116);o.Word(p.flag_117);}
void CandidateOut(Writer& o,OffboardAirCandidate c){TO(o,c.trajectory);VO(o,c.normal_64);VO(o,c.contact_velocity_80);VO(o,c.contact_position_96);o.Word(std::uint32_t(c.start_frame_112));o.Word(std::uint32_t(c.landing_frame_116));o.Word(c.valid_120);o.Word(c.special_121);}
void SamplingOut(Writer& o,const OffboardAirSampling& p)
{
    o.Word(p.pending_8492);o.Word(p.restart_allowed_8493);o.Word(p.preinitialized_8494);TO(o,p.fallback_8208);const auto& s=p.selection;
    TO(o,s.trajectory_8144);VO(o,s.normal_6144);VO(o,s.velocity_6160);VO(o,s.position_6176);o.Word(s.valid_6200);o.Word(s.result_present_3888);o.Word(std::uint32_t(s.landing_frame_8480));o.Scalar(s.scalar_8392);o.Word(s.word_8396);o.Scalar(s.candidate_scalar_100);
    VO(o,p.adjustment_8336);o.Scalar(p.blend_8384);o.Scalar(p.elapsed_8388);o.Word(std::uint32_t(p.frame_8484));
}
void ResultOut(Writer& o,const BipedAirTrajectoryResult& r)
{for(const auto& v:{r.position_272,r.velocity_288,r.normal_304,r.contact_velocity_320,r.contact_position_336,r.adjustment_352,r.apex_368})VO(o,v);o.Scalar(r.time_remaining_384);o.Scalar(r.duration_388);o.Scalar(r.scalar_392);o.Scalar(r.apex_time_396);o.Word(std::uint32_t(r.frame_400));o.Word(r.valid_404);o.Word(r.word_408);}
void OwnerOut(Writer& o,const OffboardAirSelector& owner,const OffboardAirLaunchPacket& p,const BipedAirTrajectoryResult& r)
{
    const auto prefix=o.words.size();o.Word(0);const auto& c=owner.core;SamplingOut(o,c.sampling);PacketOut(o,c.launch);
    o.Word(std::uint32_t(c.candidates.size()));for(const auto& v:c.candidates)CandidateOut(o,v);
    o.Word(std::uint32_t(c.predictions.size()));for(const auto& v:c.predictions)PredictionOut(o,v);
    o.Word(std::uint32_t(c.scores.size()));for(const auto v:c.scores)o.Scalar(v);o.Word(c.selected_index.has_value());if(c.selected_index)o.Word(std::uint32_t(*c.selected_index));CandidateOut(o,c.selected_candidate);
    VO(o,c.offset_8272);VO(o,c.correction_8304);VO(o,c.ledge_normal_8320);o.Word(c.ledge_selected_8496);o.Word(c.just_changed_8497);o.Word(c.requery_pending_8499);o.Word(std::uint32_t(c.requery_count_8488));VO(o,c.requery_position_8352);VO(o,c.requery_normal_8368);
    o.Word(owner.CompletedLaunch().has_value());if(owner.CompletedLaunch()){o.Word(std::uint32_t(owner.CompletedLaunch()->size()));for(const auto& v:*owner.CompletedLaunch())QO(o,v);}
    o.Word(owner.CompletedRequery().has_value());if(owner.CompletedRequery())PredictionOut(o,*owner.CompletedRequery());PacketOut(o,p);ResultOut(o,r);o.words[prefix]=std::uint32_t(o.words.size()-prefix-1);
}
void SettingsOut(Writer& o,const OffboardAirSelectorSettings& s){o.Scalar(s.query.height);o.Scalar(s.query.sphere_radius);o.Word(std::uint32_t(s.query.start_index));for(const auto x:s.blend.x)o.Scalar(x);for(const auto y:s.blend.y)o.Scalar(y);o.Scalar(s.deck_center_to_truck);}
void Status(Writer& o,bool okay,const std::string& error){o.Word(okay);o.Error(error.empty()?nullptr:error.c_str());}
void Selected(Writer& o,std::optional<std::size_t> index){o.Word(index.has_value());if(index)o.Word(std::uint32_t(*index));}
struct WorldState{std::optional<WorldGeometry> value;std::string error;};
WorldState ReadWorld(Reader& r){const auto count=r.Word();std::vector<WorldTriangle> triangles;for(std::uint32_t n=0;n<count;++n)triangles.push_back(Cached(ReadTriangle(r)));const bool enabled=r.Word()!=0;auto metadata=Metadata(r);const char* error=nullptr;auto world=enabled?WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error):std::optional<WorldGeometry>(WorldGeometry(std::move(triangles)));return {std::move(world),error?error:""};}
void SearchOut(Writer& o,const OffboardGroundEdgeSearch& s){o.Vector(s.min);o.Vector(s.max);o.Vector(s.frame.right);o.Vector(s.frame.up);o.Vector(s.frame.forward);o.Vector(s.frame.position);o.Word(s.context.selection_flags_2948);o.Word(std::uint32_t(s.context.matching_id_2952));o.Word(s.narrow_forward);}
void EdgesOut(Writer& o,const std::vector<OffboardGroundEdge>& edges){o.Word(std::uint32_t(edges.size()));for(const auto& e:edges){o.Vector(e.start);o.Vector(e.end);}}
void LedgeOut(Writer& o,const OffboardAirLedgeAdjustment& a){o.Vector(a.edge.start);o.Vector(a.edge.end);VO(o,a.point);TO(o,a.lowered_trajectory);o.Word(std::uint32_t(a.landing_frame));o.Scalar(a.radius);}
void InspectLedge(Writer& o,const OffboardAirSelector& owner,const WorldState& world,OffboardAirContext context,float half,std::uint32_t hit_count)
{
    auto next=owner.core;std::string error;const auto okay=owner.CompletedLaunch()&&next.ObserveLaunch(*owner.CompletedLaunch(),error);if(!owner.CompletedLaunch())error="No completed launch observation";Status(o,okay,error);if(!okay)return;
    const auto first=next.candidates.at(0);const auto prediction=next.predictions.at(0);const auto search=SearchOffboardAirLedge(first,prediction,context);o.Word(search.has_value());if(!search)return;SearchOut(o,*search);
    const std::vector<OffboardGroundEdgeBody> empty;const std::vector<OffboardGroundAlternateRecord> alt;const std::vector<OffboardGroundIndexedBody> idx;
    const auto scene=world.value?OffboardGroundScene::Create(*world.value,{empty,empty,alt,idx,false},error):std::nullopt;if(!world.value)error=world.error;Status(o,scene.has_value(),error);if(!scene)return;
    const auto edges=scene->EdgeCandidates(*search);EdgesOut(o,edges);const auto filtered=FilterOffboardAirLedges(edges,first.trajectory.position);EdgesOut(o,filtered);
    const auto a=ChooseOffboardAirLedge(first,prediction,context,owner.settings.query.sphere_radius,filtered);o.Word(a.has_value());if(!a)return;LedgeOut(o,*a);auto c=first;a->Apply(c);CandidateOut(o,c);
    const auto lines=OffboardAirLedgeLines(*a,half);o.Word(lines.has_value());if(lines)for(const auto& l:*lines){o.Vector(l.start);o.Vector(l.end);o.Scalar(l.radius);}Status(o,ConsumeOffboardAirLedgeLines(hit_count,error),error);
}
std::vector<std::uint8_t> File(const char* p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
}
int main(int argc,char** argv)
{
    if(argc<2)return 2;SettingsDatabase data;std::string error;if(!data.Load(File(argv[1]),error))return 2;OffboardAirSelectorSettings settings;Writer header;
    const auto loaded=settings.Load(data,error);Status(header,loaded,error);if(loaded)SettingsOut(header,settings);for(const auto w:header.words)Word(w);if(!loaded)return std::cout?0:2;
    if(argc>2){SettingsDatabase invalid;if(!invalid.Load(File(argv[2]),error))return 2;Writer out;const auto ok=settings.Load(invalid,error);Status(out,ok,error);SettingsOut(out,settings);for(const auto w:out.words)Word(w);return std::cout?0:2;}
    Reader input;input.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=input.Word();Word(count);
    for(std::uint32_t index=0;index<count;++index)
    {
        auto world=ReadWorld(input);const auto commands=input.Word();OffboardAirSelector owner(settings);auto packet=OffboardAirLaunchPacket::Initialized(0);BipedAirTrajectoryResult sample;Writer out;Status(out,world.value.has_value(),world.error);OwnerOut(out,owner,packet,sample);out.Word(commands);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=input.Word();out.Word(op);error.clear();
            if(op==0||op==13){if(op==0)packet=Packet(input);const auto gravity=V(input);const auto context=Context(input);const auto ok=world.value&&owner.Launch(*world.value,packet,gravity,context,error);if(!world.value)error=world.error;Status(out,ok,error);}
            else if(op==1||op==9){const auto context=Context(input);const auto half=input.Scalar();std::optional<std::size_t> selected;const auto ok=world.value&&(op==1?owner.Consume(*world.value,context,half,selected,error):owner.ConsumeLaunch(*world.value,context,half,selected,error));if(!world.value)error=world.error;Status(out,ok,error);if(ok)Selected(out,selected);}
            else if(op==2){const auto frame=std::int32_t(input.Word());const auto animation=V(input);const auto axes=M(input);owner.AdjustAnimation(frame,animation,axes);}
            else if(op==3){const auto frame=std::int32_t(input.Word());const auto dt=input.Scalar();owner.Sample(frame,dt,sample);ResultOut(out,sample);}
            else if(op==4){const auto context=Context(input);const auto f=input.Word(),g=input.Word();bool executed=false;const auto ok=world.value&&owner.Requery(*world.value,context,f,g,executed,error);if(!world.value)error=world.error;Status(out,ok,error);if(ok)out.Word(executed);}
            else if(op==5){bool consumed=false;const auto ok=owner.ConsumeRequery(consumed,error);Status(out,ok,error);if(ok)out.Word(consumed);}
            else if(op==6)owner.Reset();else if(op==7)owner.Exit();else if(op==8){world=ReadWorld(input);Status(out,world.value.has_value(),world.error);}
            else if(op==10){const auto trajectory=T(input);const auto point=V(input),normal=V(input);const auto time=OffboardAirLedgePlaneTime(trajectory,point,normal);out.Word(time.has_value());if(time)out.Scalar(*time);}
            else if(op==11){const auto context=Context(input);const auto half=input.Scalar();const auto hit_count=input.Word();InspectLedge(out,owner,world,context,half,hit_count);}
            else if(op==12)
            {
                packet=Packet(input);const auto p=LaunchInput(input);BipedControllerState controller(std::array<std::optional<BipedClipMetric>,3>{});controller.frame_output.frame[1]=V(input);controller.motion.frame_0[1]=V(input);
                controller.motion.speed_704=input.Scalar();controller.intent.steering=input.Scalar();controller.motion.angular_velocity_688=input.Scalar();controller.contact.active=input.Word()!=0;
                PointGraph<8> turn;for(auto& x:turn.x)x=input.Scalar();for(auto& y:turn.y)y=input.Scalar();const OffboardAirLaunchSettings launch{input.Scalar(),input.Scalar()};const bool current=input.Word()!=0;
                out.Word(OffboardAirLaunchMode(p,current));const auto ok=ProduceOffboardAirLaunch(packet,controller,turn,launch,p,current,error);Status(out,ok,error);PacketOut(out,packet);
            }
            else if(op==14)owner.core.Reset();else if(op==15)sample.Reset();else if(op==16){const auto length=input.Word();auto results=owner.CompletedLaunch().value_or(std::vector<AirTrajectoryQueryResult>{});results.resize(std::min<std::size_t>(length,results.size()));Status(out,owner.core.ObserveLaunch(results,error),error);}
            else if(op==18){const OffboardAirQuerySettings s{input.Scalar(),input.Scalar(),std::int32_t(input.Word())};const auto p=Packet(input);const auto gravity=V(input);std::vector<AirTrajectoryQueryRequest> requests;const auto okay=owner.core.BeginLaunch(p,gravity,s,requests,error);Status(out,okay,error);if(okay){out.Word(std::uint32_t(requests.size()));for(const auto& q:requests)RequestOut(out,q);}}
            else Fail("Unknown offboard air selector operation");OwnerOut(out,owner,packet,sample);
        }
        Word(index);Word(std::uint32_t(out.words.size()));for(const auto w:out.words)Word(w);
    }
    return input.at==input.bytes.size()&&std::cout?0:2;
}
