#include "PlayerGrindContact.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
namespace
{
std::optional<PlayerGrindTruckContact> Rectangle(Vec4 a,Vec4 b,Vec4 c,Vec4 d,Vec4 reference,const std::vector<PlayerGrindPrimitive>& edges)
{
    std::optional<PlayerGrindTruckContact> best;float distance=1000000;
    for(std::size_t i=0;i<edges.size();++i)
    {
        const auto& edge=edges[i];auto position=PlayerGrindSegmentTriangle(edge.start,edge.end,{a,b,c});if(!position)position=PlayerGrindSegmentTriangle(edge.start,edge.end,{d,a,c});
        if(position){const auto delta=Sub(*position,reference);const float square=Dot3(delta,delta);if(square<distance){distance=square;best=PlayerGrindTruckContact{*position,i};}}
    }
    return best;
}
PlayerGrindCandidate Geometry(PlayerGrindTruckContact hit,PlayerGrindPrimitive edge)
{
    const auto delta=Sub(edge.end,edge.start);return {Scale4(delta,InverseLengthSquared(Dot3(delta,delta),2)),hit.position,edge.end,edge.start,hit.primitive};
}
}
std::optional<PlayerGrindTruckContact> PlayerGrindInvertedContact(Mat4 board,std::uint32_t flags,float epsilon,float depth,const std::vector<PlayerGrindPrimitive>& edges)
{
    if((flags&0x200000)==0)return std::nullopt;board[1]=Scale4(board[1],-1);return PlayerGrindDeckContact(board,0,epsilon,depth,.3f,edges);
}
std::array<std::optional<PlayerGrindTruckContact>,2> PlayerGrindTipContacts(Mat4 board,std::uint32_t flags,std::uint32_t state,std::uint32_t flags_2468,float truck_distance,const std::vector<PlayerGrindPrimitive>& edges)
{
    std::array<std::optional<PlayerGrindTruckContact>,2> out;if((flags&0x200000)!=0)return out;
    for(std::size_t i=0;i<2;++i)
    {
        if((state==402||state==404)&&(((flags_2468&0x200)!=0)!=(i==0)))continue;const float sign=i==0 ? 1.0f : -1.0f;
        const auto center=Add(board[3],Scale4(board[1],.02f)),a=Add(center,Scale4(board[2],sign*truck_distance)),b=Add(Add(center,Scale4(board[2],sign*(truck_distance+.215f))),Scale4(board[1],.03f));
        const auto c=Add(b,Scale4(board[1],-.2f)),d=Add(a,Scale4(board[1],-.2f));out[i]=Rectangle(a,b,c,d,Scale4(Add(a,b),.5f),edges);
    }
    return out;
}
bool PlayerGrindIsBackslash(Vec4 board_position,Vec4 point,std::array<Vec4,2> far_points,Vec4 support,float truck_distance,std::uint32_t state)
{
    if(state==402)return false;const std::array<Vec4,2> offsets{Sub(far_points[0],point),Sub(far_points[1],point)};const std::array<float,2> heights{Dot3(offsets[0],support),Dot3(offsets[1],support)};
    if(std::abs(heights[0]-heights[1])<=truck_distance*.1f)return false;const auto higher=heights[0]>heights[1] ? offsets[0] : offsets[1];return Dot3(Sub(board_position,point),higher)>0;
}
std::optional<PlayerGrindFamilyContact> PlayerGrindDarkslide(Mat4 board,PlayerGrindTruckContact hit,PlayerGrindPrimitive edge,Vec4 velocity,std::uint32_t category,std::uint32_t low_frames,const PlayerGrindAdmission& admission)
{
    auto g=Geometry(hit,edge);const auto delta=Sub(edge.end,edge.start);g.direction=Scale4(delta,Reciprocal(SquareRoot(Dot3(delta,delta))));
    if(Dot3(PlayerGrindUprightNormal(g.direction),Scale4(board[1],-1))<=.45f)return std::nullopt;const auto decision=admission.Test(400,g.direction,false);if(!decision.allowed)return std::nullopt;
    const float depth=Dot3(Sub(board[3],hit.position),board[1]);const auto projected=Scale4(board[1],depth);if(Dot3(projected,projected)>=.005625f)return std::nullopt;
    if(category==100&&std::abs(Dot3(velocity,g.direction))<=.75f&&low_frames<=10)return std::nullopt;return PlayerGrindFamilyContact{g,false,5,decision.kind};
}
std::optional<PlayerGrindFamilyContact> PlayerGrindFiveO(Mat4 board,const std::array<std::optional<PlayerGrindTruckContact>,2>& hits,const std::vector<PlayerGrindPrimitive>& edges,Vec4 velocity,std::uint32_t flags_2476,std::uint32_t flags_2472,std::uint32_t ground_frames,float translation,const PlayerGrindAdmission& admission)
{
    if((flags_2476&0x40000000)!=0)return std::nullopt;std::array<std::optional<std::pair<PlayerGrindCandidate,PlayerGrindEntryKind>>,2> valid;
    for(std::size_t i=0;i<2;++i)if(hits[i])
    {
        const auto hit=*hits[i];const auto g=Geometry(hit,edges[hit.primitive]);const float depth=Dot3(Sub(board[3],hit.position),board[1]);const auto projected=Scale4(board[1],depth);if(Dot3(projected,projected)>=F(0x3c8a71de))continue;
        const auto decision=admission.Test(403,g.direction,true);if(!decision.allowed||std::abs(Dot3(board[0],g.direction))>=.906f||std::abs(Dot3(board[1],g.direction))>=.46f)continue;
        valid[i]=std::pair<PlayerGrindCandidate,PlayerGrindEntryKind>{g,decision.kind};
    }
    const bool forwards=Dot3(board[2],velocity)>0;const std::size_t leading=forwards ? 0 : 1,trailing=1-leading;bool take_leading=false,take_trailing=false;
    if(valid[leading]&&valid[trailing]){take_leading=ground_frames>30 ? (flags_2472&0x1000)!=0 : translation>.68f;take_trailing=!take_leading;}
    else if(!valid[leading]&&valid[trailing])take_trailing=true;
    else if(valid[leading]&&!valid[trailing])take_leading=ground_frames<=30||(flags_2472&0x1000)!=0;
    std::size_t index;if(take_trailing)index=trailing;else if(take_leading)index=leading;else return std::nullopt;
    return PlayerGrindFamilyContact{valid[index]->first,index==0,3,valid[index]->second};
}
std::optional<PlayerGrindFamilyContact> PlayerGrindTipslide(Mat4 board,const std::array<std::optional<PlayerGrindTruckContact>,2>& hits,const std::vector<PlayerGrindPrimitive>& edges,Vec4 velocity,std::uint32_t category,std::uint32_t flags_2476,std::uint32_t flags_2472,std::uint32_t ground_frames,float balance,Vec4 right,const PlayerGrindAdmission& admission)
{
    if((flags_2476&0x40000000)!=0)return std::nullopt;const bool front=bool(hits[0]);const auto selected=front ? hits[0] : hits[1];if(!selected)return std::nullopt;const auto hit=*selected;
    const auto g=Geometry(hit,edges[hit.primitive]);const auto decision=admission.Test(402,g.direction,true);if(!decision.allowed)return std::nullopt;
    if((decision.kind==PlayerGrindEntryKind::DropIn||(velocity[1]<0&&category!=400))&&board[3][1]<=hit.position[1])return std::nullopt;
    const auto delta=Sub(board[3],hit.position);const float depth=Dot3(delta,board[1]);const auto projected=Scale4(board[1],depth);if(Dot3(projected,projected)>=F(0x3b6bedfa))return std::nullopt;
    const auto perpendicular=Sub(velocity,Scale4(g.direction,Dot3(g.direction,velocity)));
    if(Dot3(perpendicular,perpendicular)<9)
    {
        if(std::abs(balance)>0){if(Dot3(Sub(hit.position,board[3]),right)>=0)return std::nullopt;}
        else if(ground_frames>30){const bool toward=Dot3(Sub(hit.position,board[3]),velocity)>0;if(((flags_2472&0x1000)!=0)!=toward)return std::nullopt;}
    }
    return PlayerGrindFamilyContact{g,front,2,decision.kind};
}
PlayerGrindContactInvestigation InvestigatePlayerGrindContact(const PlayerGrindContactQuery& q,const std::vector<PlayerGrindPrimitive>& edges)
{
    if(edges.empty())return {};const auto& a=q.admission;
    const auto trucks=PlayerGrindTruckContacts(q.board,q.flags_2484,q.truck_to_wheel,q.deck_to_truck,edges),tips=PlayerGrindTipContacts(q.board,q.flags_2484,q.tip_state,q.flags_2468,q.deck_to_truck,edges);
    const auto deck=PlayerGrindDeckContact(q.board,q.flags_2484,q.test_above,q.test_below,q.deck_to_truck,edges),inverted=PlayerGrindInvertedContact(q.board,q.flags_2484,q.test_above,q.test_below,edges);
    if(!q.forbidden)
    {
        const auto fifty=[&]()->std::optional<PlayerGrindFamilyContact>{const auto g=PlayerGrindFiftyFiftyCandidate(q.board,{q.translation,q.stability_nudge},trucks,edges);if(!g)return std::nullopt;const auto decision=a.Test(401,g->direction,false);return decision.allowed ? std::optional<PlayerGrindFamilyContact>(PlayerGrindFamilyContact{*g,false,0,decision.kind}) : std::nullopt;};
        const auto five=[&]{return PlayerGrindFiveO(q.board,trucks,edges,a.velocity,q.flags_2476,q.flags_2472,q.ground_frames,q.translation,a);};
        const auto tip=[&]{return PlayerGrindTipslide(q.board,tips,edges,a.velocity,a.category,q.flags_2476,q.flags_2472,q.ground_frames,q.balance,q.reference_right,a);};
        const auto slide=[&]()->std::optional<PlayerGrindFamilyContact>{if(!deck)return std::nullopt;const auto g=PlayerGrindBoardslideCandidate(q.board,*deck,edges[deck->primitive],a.velocity,a.category,std::int32_t(q.low_wheel_frames),q.flags_2476,q.deck_to_truck,q.truck_to_wheel,a);return g ? std::optional<PlayerGrindFamilyContact>(PlayerGrindFamilyContact{*g,false,1,a.Test(400,g->direction,false).kind}) : std::nullopt;};
        const auto dark=[&]()->std::optional<PlayerGrindFamilyContact>{if(!inverted)return std::nullopt;return PlayerGrindDarkslide(q.board,*inverted,edges[inverted->primitive],a.velocity,a.category,q.low_wheel_frames,a);};
        std::optional<PlayerGrindFamilyContact> candidate;
        if(a.state==401||a.state==403){candidate=fifty();if(!candidate)candidate=five();}else if(a.state==402||a.state==404)candidate=tip();else if(a.state==400)candidate=slide();else if(a.state==405)candidate=dark();
        if(!candidate)candidate=fifty();if(!candidate)candidate=five();if(!candidate)candidate=tip();if(!candidate)candidate=slide();if(!candidate)candidate=dark();if(candidate)return {candidate,std::nullopt};
    }
    auto fallback=trucks[0] ? trucks[0] : trucks[1];if(fallback)return {std::nullopt,PlayerGrindProximity{*fallback,false}};if(deck)return {std::nullopt,PlayerGrindProximity{*deck,true}};
    fallback=inverted ? inverted : tips[0] ? tips[0] : tips[1];return fallback ? PlayerGrindContactInvestigation{std::nullopt,PlayerGrindProximity{*fallback,false}} : PlayerGrindContactInvestigation{};
}
}
