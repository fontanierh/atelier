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
float SlopeSine(Vec4 tangent,Vec4 velocity,float dead_zone)
{
    const auto transverse=Sub(velocity,Scale4(tangent,Dot3(velocity,tangent)));const float length=SquareRoot(Dot3(transverse,transverse));return length<=dead_zone ? 0.0f : Reciprocal(length)*transverse[1];
}
}
float PlayerGrindApproachSlope(Vec4 tangent,Vec4 velocity){return SlopeSine(tangent,velocity,.01f);}
float PlayerGrindEngagementSlope(Vec4 tangent,Vec4 velocity){return SlopeSine(tangent,velocity,.001f);}
PlayerGrindAdmissionDecision PlayerGrindAdmission::Test(std::uint32_t requested,Vec4 tangent,bool allows_drop_in) const
{
    using K=PlayerGrindEntryKind;K kind;
    if(category==400||state==701)kind=state==requested||(requested==402&&state==404) ? K::StayInGrind : K::ChangeGrind;
    else if(category==100)
    {
        if(allows_drop_in&&speed<1.45f)kind=K::DropIn;
        else {const float slope=PlayerGrindApproachSlope(tangent,velocity);kind=slope>.96f ? K::RideIntoCoping : slope>.25f ? K::RideFromBelow : K::RideFromAbove;}
    }
    else kind=K::AirToGrind;
    bool allowed=false;
    switch(kind)
    {
    case K::RideFromAbove:allowed=PlayerGrindWithinApproach(tangent,velocity,17);break;
    case K::StayInGrind:allowed=PlayerGrindWithinApproach(tangent,velocity,90);break;
    case K::ChangeGrind:allowed=PlayerGrindWithinApproach(tangent,velocity,24);break;
    case K::AirToGrind:case K::DropIn:allowed=true;break;
    case K::RideFromBelow:case K::RideIntoCoping:
    {
        const float square_speed=Dot3(velocity,velocity);const auto transverse=Sub(Scale4(tangent,Dot3(velocity,tangent)),velocity);const float square_transverse=Dot3(transverse,transverse);
        const float ratio=square_speed<=.002f ? 1.0f : SquareRoot(square_transverse/square_speed);
        const float slope=PlayerGrindApproachSlope(tangent,velocity),multiplier=threshold_vs_slope.Evaluate(slope),limit=std::fma(1.0f-ratio,2.4f,2.8f)*multiplier;allowed=square_transverse<limit*limit;break;
    }
    }
    return {kind,allowed};
}
std::optional<Vec4> PlayerGrindSegmentTriangle(Vec4 start,Vec4 end,const std::array<Vec4,3>& triangle)
{
    const auto a=triangle[0],b=triangle[1],c=triangle[2],ac=Sub(c,a),ab=Sub(b,a),direction=Sub(end,start),normal=Cross3(ab,ac);
    const float denominator=-Dot3(direction,normal);if(denominator==0)return std::nullopt;const auto from=Sub(start,a);
    const float inverse=1.0f/denominator,t=inverse*Dot3(from,normal);if(t<0||t>1)return std::nullopt;
    const auto side=Cross3(from,direction);const float u=inverse*Dot3(ac,side),v=(1.0f/-denominator)*Dot3(ab,side);if(u+v>1||u<0||v<0)return std::nullopt;
    return Madd4(direction,t,start);
}
std::optional<PlayerGrindTruckContact> PlayerGrindDeckContact(Mat4 board,std::uint32_t flags,float above,float below,float truck_distance,const std::vector<PlayerGrindPrimitive>& primitives)
{
    if((flags&0x200000)!=0)return std::nullopt;const auto center=Add(board[3],Scale4(board[1],above)),along=Scale4(board[2],truck_distance),down=Scale4(board[1],-(above+below));
    const auto a=Add(center,along),b=Sub(center,along),c=Add(a,down),d=Add(b,down);std::optional<PlayerGrindTruckContact> best;float distance=1000000;
    for(std::size_t i=0;i<primitives.size();++i)
    {
        const auto edge=primitives[i];const auto first=PlayerGrindSegmentTriangle(edge.start,edge.end,{a,b,c}),second=PlayerGrindSegmentTriangle(edge.start,edge.end,{d,b,c});const auto position=first ? first : second;
        if(position){const auto delta=Sub(*position,board[3]);const float square=Dot3(delta,delta);if(square<distance){distance=square;best=PlayerGrindTruckContact{*position,i};}}
    }
    return best;
}
std::optional<PlayerGrindCandidate> PlayerGrindBoardslideCandidate(Mat4 board,PlayerGrindTruckContact contact,PlayerGrindPrimitive edge,Vec4 velocity,std::uint32_t category,std::int32_t frames,std::uint32_t flags,float deck_to_truck,float truck_to_wheel,const PlayerGrindAdmission& admission)
{
    if((flags&0x40000000)!=0)return std::nullopt;const auto delta=Sub(edge.end,edge.start),direction=Scale4(delta,Reciprocal(SquareRoot(Dot3(delta,delta))));
    if(Dot3(PlayerGrindUprightNormal(direction),board[1])<=.65f)return std::nullopt;if(!admission.Test(400,direction,false).allowed)return std::nullopt;
    const float depth=Dot3(Sub(board[3],contact.position),board[1]);const auto projected=Scale4(board[1],depth);if(Dot3(projected,projected)>=F(0x3b6bedfa))return std::nullopt;
    if(category==100&&std::abs(Dot3(velocity,direction))<=.75f&&frames<=10)return std::nullopt;
    auto horizontal=Sub(delta,Scale4(board[1],Dot3(delta,board[1])));const float length=SquareRoot(Dot3(horizontal,horizontal));if(!(length>0))return std::nullopt;horizontal=Scale4(horizontal,Reciprocal(length));
    const float alignment=std::abs(Dot3(horizontal,board[2]));const auto from=Sub(contact.position,board[3]),across=Sub(from,Scale4(board[1],Dot3(from,board[1])));
    const float remaining=deck_to_truck-SquareRoot(Dot3(across,across)),clearance=alignment>0 ? remaining/alignment*SquareRoot(1.0f-alignment*alignment) : 999.0f;if(!(clearance>truck_to_wheel))return std::nullopt;
    return PlayerGrindCandidate{direction,contact.position,edge.end,edge.start,contact.primitive};
}
std::optional<PlayerGrindCandidate> PlayerGrindFiftyFiftyCandidate(Mat4 board,std::array<float,2> balance,const std::array<std::optional<PlayerGrindTruckContact>,2>& contacts,const std::vector<PlayerGrindPrimitive>& primitives)
{
    if(!contacts[0]||!contacts[1])return std::nullopt;const auto front=*contacts[0],rear=*contacts[1];if(VectorMax(std::abs(balance[0]),std::abs(balance[1]))>=.9f)return std::nullopt;
    if(front.primitive!=rear.primitive)
    {
        if(front.primitive>=primitives.size())return std::nullopt;const auto edge=primitives[front.primitive];const auto delta=Sub(edge.end,edge.start),direction=Scale4(delta,InverseLengthSquared(Dot3(delta,delta),2));const auto across=Cross3(PlayerGrindUprightNormal(direction),direction);
        if(Dot3(Sub(front.position,rear.position),across)>.1f)return std::nullopt;
    }
    const float front_depth=Dot3(Sub(board[3],front.position),board[1]),rear_depth=Dot3(Sub(board[3],rear.position),board[1]);if(VectorMax(front_depth,rear_depth)>=.13f)return std::nullopt;
    const auto difference=Sub(front.position,rear.position);return PlayerGrindCandidate{Scale4(difference,InverseLengthSquared(Dot3(difference,difference),2)),Scale4(Add(front.position,rear.position),.5f),front.position,rear.position,front.primitive};
}
Vec4 PlayerGrindUprightNormal(Vec4 direction)
{
    const auto cross_up=Cross3(Vec4{0,1,0,0},direction),normal=Cross3(cross_up,direction);float length=SquareRoot(Dot3(normal,normal));if(length<=0)return {1,0,0,0};if(normal[1]<0)length=-length;return Scale4(normal,Reciprocal(length));
}
bool PlayerGrindWithinApproach(Vec4 direction,Vec4 velocity,float degrees)
{
    const auto normal=PlayerGrindUprightNormal(direction),projected=Sub(velocity,Scale4(normal,Dot3(velocity,normal)));const float length=SquareRoot(Dot3(projected,projected));if(length<=.001f)return true;
    const float alignment=std::abs(Dot3(Scale4(projected,Reciprocal(length)),direction));return alignment>Cos(degrees*F(0x3c8efa35));
}
std::array<std::optional<PlayerGrindTruckContact>,2> PlayerGrindTruckContacts(Mat4 board,std::uint32_t flags,float truck_to_wheel,float deck_to_truck,const std::vector<PlayerGrindPrimitive>& primitives)
{
    std::array<std::optional<PlayerGrindTruckContact>,2> result;if((flags&0x200000)!=0)return result;
    const auto center=Madd4(board[1],-.02f,board[3]),side=Scale4(board[0],truck_to_wheel),along=Scale4(board[2],deck_to_truck),down=Scale4(board[1],-.2f);
    const std::array<Vec4,2> centers{Add(center,along),Sub(center,along)};std::array<float,2> distance{1000000,1000000};
    for(std::size_t i=0;i<primitives.size();++i)for(std::size_t truck=0;truck<2;++truck)
    {
        const auto edge=primitives[i];const auto a=Add(centers[truck],side),b=Sub(centers[truck],side),c=Add(b,down),d=Add(a,down);
        const auto first=PlayerGrindSegmentTriangle(edge.start,edge.end,{a,b,c}),second=PlayerGrindSegmentTriangle(edge.start,edge.end,{a,d,c});const auto position=first ? first : second;
        if(position){const auto delta=Sub(*position,centers[truck]);const float square=Dot3(delta,delta);if(distance[truck]>square){distance[truck]=square;result[truck]=PlayerGrindTruckContact{*position,i};}}
    }
    return result;
}
}
