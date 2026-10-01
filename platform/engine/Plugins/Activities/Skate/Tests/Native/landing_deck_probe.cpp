// SPDX-License-Identifier: Apache-2.0
#include "LandingDeck.h"
#include "LandingOnDeckSettings.h"
#include "LandingDeckMath.h"
// WORLD_PROTOCOL
#include <fstream>
namespace
{
Vec4 V(Reader& r){return {r.Scalar(),r.Scalar(),r.Scalar(),r.Scalar()};}
Mat4 M(Reader& r){Mat4 v{};for(auto& axis:v)axis=V(r);return v;}
AirTrajectory T(Reader& r){return {V(r),V(r),V(r),r.Scalar()};}
AirTrajectoryQueryRequest Request(Reader& r){return {T(r),r.Scalar(),r.Scalar(),r.Scalar()};}
void VO(Writer& o,Vec4 v){for(const auto x:v)o.Scalar(x);}void MO(Writer& o,const Mat4& m){for(const auto& v:m)VO(o,v);}
void TO(Writer& o,AirTrajectory t){VO(o,t.position);VO(o,t.velocity);VO(o,t.acceleration);o.Scalar(t.scalar_48);}
void RequestOut(Writer& o,AirTrajectoryQueryRequest q){TO(o,q.trajectory);o.Scalar(q.radius);o.Scalar(q.start_error);o.Scalar(q.end_error);}
void QO(Writer& o,AirTrajectoryQueryResult q){VO(o,q.contact_position);VO(o,q.contact_normal);VO(o,q.landing_normal);o.Scalar(q.contact_time);MO(o,q.contact_transform);o.Word(std::uint32_t(q.contact_frame));o.Word(q.surface);o.Word(q.geometry);}
void Status(Writer& o,bool okay,const std::string& error){o.Word(okay);o.Error(error.empty()?nullptr:error.c_str());}
struct WorldState{std::optional<WorldGeometry> value;std::string error;};
WorldState ReadWorld(Reader& r){const auto count=r.Word();std::vector<WorldTriangle> triangles;for(std::uint32_t n=0;n<count;++n)triangles.push_back(Cached(ReadTriangle(r)));const bool enabled=r.Word()!=0;auto metadata=Metadata(r);const char* error=nullptr;auto world=enabled?WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error):std::optional<WorldGeometry>(WorldGeometry(std::move(triangles)));return {std::move(world),error?error:""};}
void Raw(RawVector& out,Vec4 v){for(unsigned n=0;n<4;++n)std::memcpy(&out[n],&v[n],4);}
struct PlayerTransport
{
    ProcessedPhysicsInput processed;std::optional<BoardToolkit> toolkit;
    LandingDeckPlayerView View() const{return {processed,toolkit};}
    void Read(Reader& r)
    {
        const bool present=r.Word()!=0;const auto deck=M(r);if(present){toolkit=BoardToolkit{};toolkit->deck=deck;}else toolkit.reset();
        Raw(processed.vectors_400_416[0],V(r));Raw(processed.vectors_544_560_592_608[0],V(r));Raw(processed.vectors_544_560_592_608[2],V(r));Raw(processed.vectors_544_560_592_608[3],V(r));
        processed.vectors_880_896_912_928_944[3][1]=r.Word();processed.external_physics_1616.flags=r.Word();processed.flags_2480=r.Word();processed.surface_mode_2540=r.Word();processed.wheel_count_2556=r.Word();processed.actor_query_2952=r.Word();processed.flags_2488=r.Word();
    }
};
void Output(Writer& o,const LandingDeckUpdateOutput& p)
{
    o.Word(p.can_land);o.Word(p.trajectory_valid);o.Scalar(p.time_to_land);o.Scalar(p.elapsed);o.Scalar(p.landing_time);o.Scalar(p.apex_time);
    for(const auto& v:{p.position,p.landing_velocity,p.launch_position,p.landing_position,p.normal,p.apex_position,p.direction,p.up})VO(o,v);o.Word(p.query.has_value());if(p.query)RequestOut(o,*p.query);
}
void RootOut(Writer& o,const SkeletonRootFrames& r)
{MO(o,r.board);MO(o,r.inverse_board);VO(o,r.previous_board_position);VO(o,r.predicted_board_position);o.Word(r.supplied_prediction.has_value());if(r.supplied_prediction)VO(o,*r.supplied_prediction);MO(o,r.animation_to_board);MO(o,r.animation_to_world);MO(o,r.world_to_animation);MO(o,r.heading_alignment);o.Word(r.initialize_heading);}
void SettingsOut(Writer& o,const LandingDeck& owner,const LandingOnDeckConfiguration& config)
{o.Scalar(owner.settings.deck_min_uprightness);o.Scalar(owner.settings.approximate_com_height);const auto& s=config.state;for(const auto x:{s.minimum_auto_angle,s.automatic_speed,s.input_speed,s.input_delta,s.automatic_delta,s.maximum_landing_speed,config.root.root_y_offset,config.root.capsule_radius,config.root.capsule_length})o.Scalar(x);}
void OwnerOut(Writer& o,const LandingDeck& owner,const LandingOnDeckState& state,const SkeletonRootFrames& roots,const OffBoardOutputFields& pub,RawVector skeleton,std::uint8_t flag)
{
    const auto start=o.words.size();o.Word(0);const auto& m=owner.manager;TO(o,m.trajectory_32);TO(o,m.proposed_96);o.Scalar(m.elapsed_160);o.Word(m.trajectory_valid_164);for(const auto& v:{m.ik_offset_176,m.vector_192,m.moving_contact_208,m.vector_224})VO(o,v);
    o.Scalar(m.obstruction_height_240);o.Scalar(m.time_to_land_244);o.Scalar(m.proposed_time_248);o.Word(m.completed_queries_252);for(const auto v:{m.can_land_256,m.force_257,m.blocked_258,m.tested_259,m.hippy_hurdling_260,m.publish_moving_contact_261,m.pending_262})o.Word(v);
    o.Word(owner.Completion().has_value());if(owner.Completion())QO(o,*owner.Completion());const auto f=owner.Fill();o.Word(f.can_land_316);o.Word(f.hippy_hurdling_317);o.Word(f.moving_contact.has_value());if(f.moving_contact)VO(o,*f.moving_contact);
    o.Word(state.output.has_value());if(state.output)Output(o,*state.output);o.Scalar(state.time_to_land);for(const auto v:{state.dangerous,state.near_deck,state.turning,state.hippy})o.Word(v);o.Word(std::uint32_t(state.takeoff_frames));for(const auto v:{state.spin_rate,state.applied_spin,state.transition_angle,state.accumulated_spin})o.Scalar(v);o.Word(std::uint32_t(state.half_turns));o.Word(std::uint32_t(state.next_half_turns));o.Word(std::uint32_t(state.LandingHalfTurns()));o.Word(state.RequestsBoardFlip());
    RootOut(o,roots);o.Word(pub.flag_316);o.Word(pub.hippy_hurdling_317);for(const auto x:skeleton)o.Word(x);o.Word(flag);o.words[start]=std::uint32_t(o.words.size()-start-1);
}
std::vector<std::uint8_t> File(const char* p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
}
int main(int argc,char** argv)
{
    if(argc<2)return 2;SettingsDatabase data;std::string error;if(!data.Load(File(argv[1]),error))return 2;LandingDeck loaded;LandingOnDeckConfiguration config;Writer header;const auto valid=loaded.Load(data,error)&&config.Load(data,error);Status(header,valid,error);if(valid)SettingsOut(header,loaded,config);for(const auto w:header.words)Word(w);if(!valid)return std::cout?0:2;
    if(argc>2){SettingsDatabase invalid;if(!invalid.Load(File(argv[2]),error))return 2;auto next_owner=loaded;auto next_config=config;const auto okay=next_owner.Load(invalid,error)&&next_config.Load(invalid,error);if(okay){loaded=next_owner;config=next_config;}Writer o;Status(o,okay,error);SettingsOut(o,loaded,config);for(const auto w:o.words)Word(w);return std::cout?0:2;}
    Reader input;input.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=input.Word();Word(count);
    for(std::uint32_t index=0;index<count;++index)
    {
        auto world=ReadWorld(input);const auto commands=input.Word();LandingDeck owner=loaded;LandingOnDeckState state;SkeletonRootFrames roots;PlayerTransport player;std::optional<LandingDeckUpdateOutput> last;OffBoardOutputFields publication;RawVector skeleton{{0x11112222,0x33334444,0x55556666,0x77778888}};std::uint8_t flag=7;Writer o;
        Status(o,world.value.has_value(),world.error);OwnerOut(o,owner,state,roots,publication,skeleton,flag);o.Word(commands);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=input.Word();o.Word(op);error.clear();
            if(op==0)player.Read(input);
            else if(op==1){LandingOnDeckEntry e;e.previous_category=input.Word();e.hippy=input.Word()!=0;e.strength=input.Scalar();e.board_position=player.toolkit?player.toolkit->deck[3]:Vec4{};e.com_position=landing_deck_math::Position(player.View());e.com_velocity=landing_deck_math::Velocity(player.View());e.board_velocity=landing_deck_math::FromRaw(player.processed.vectors_400_416[0]);e.up=landing_deck_math::FromRaw(player.processed.vectors_544_560_592_608[0]);e.hips_up=V(input);e.animation_right=V(input);e.reversed=input.Word()!=0;state.Enter(owner.manager,e);}
            else if(op==2||op==3||op==13)
            {
                const auto maximum=op==2?input.Scalar():0;AirTrajectoryQueryRequest request;if(op==13)request=Request(input);auto scene=world.value?OffboardStaticScene::Create(*world.value,error):std::nullopt;if(!world.value)error=world.error;bool okay=false;
                if(scene){if(op==2)okay=owner.Assist(*scene,player.View(),maximum,error);else if(op==13)okay=owner.Submit(*scene,request,player.View(),error);else{LandingDeckUpdateOutput out;okay=owner.Update(*scene,player.View(),out,error);if(okay)last=out;}}
                Status(o,okay,error);if(op==3&&okay)Output(o,*last);
            }
            else if(op==4){const auto a=V(input),b=V(input);const auto time=input.Scalar(),velocity=input.Scalar(),spin=input.Scalar();state.Align(config.state,a,b,time,velocity,spin);}
            else if(op==5){if(last){state.AdvanceSpin(*last);Status(o,true,error);}else{error="No completed Landing Update";Status(o,false,error);}}
            else if(op==6){const auto y=input.Scalar(),bv=input.Scalar(),cv=input.Scalar(),toe0=input.Scalar(),toe1=input.Scalar();const auto wheels=input.Word();o.Scalar(LandingOnDeckState::AccurateTime(y,bv,cv,{toe0,toe1},wheels));}
            else if(op==7)state.Finish(config.state,input.Scalar());
            else if(op==8)owner.manager.CorrectTrajectory(V(input));
            else if(op==9){const auto root=M(input);const auto com=V(input),mapped=V(input);const auto time=input.Scalar();Vec4 result{};const auto okay=owner.CalculateAccurateIkOffset(player.View(),root,com,mapped,time,result,error);Status(o,okay,error);if(okay)VO(o,result);}
            else if(op==10)Status(o,owner.PostPhysics(player.View(),error),error);
            else if(op==11)owner.Reset();
            else if(op==12){world=ReadWorld(input);Status(o,world.value.has_value(),world.error);}
            else if(op==14){const auto old=M(input);const auto com=V(input);const auto flags=input.Word();const auto y=input.Scalar();MO(o,LandingOnBoardSkateRoot(old,com,flags,y,config.root));}
            else if(op==15){const auto com=V(input),local=V(input);const auto spin=input.Scalar();std::optional<std::uint32_t> revert;if(input.Word())revert=input.Word();const auto reverse=input.Word()!=0;UpdateLandingOnBoardRoot(roots,com,local,spin,revert,reverse);}
            else if(op==16){const auto inverse=M(input),actual=M(input),mapped=M(input);const auto ik=V(input);const auto velocity=input.Scalar();const auto flags=input.Word();const auto time=input.Scalar();PointGraph<8> blend;for(auto& x:blend.x)x=input.Scalar();for(auto& y:blend.y)y=input.Scalar();const auto offset=LandingOnBoardPoseAdjustment(inverse,actual,mapped,ik,velocity,flags,time,blend);o.Word(offset.has_value());if(offset)MO(o,*offset);}
            else if(op==17)owner.Publish(publication,skeleton,flag);
            else return 2;
            OwnerOut(o,owner,state,roots,publication,skeleton,flag);
        }
        Word(index);Word(std::uint32_t(o.words.size()));for(const auto w:o.words)Word(w);
    }
    return input.at==input.bytes.size()&&std::cout?0:2;
}
