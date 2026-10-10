#include "BoardContactFeedback.h"
#include <cstring>

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
Vec3 Vector(const std::array<std::uint32_t,64>& words,std::size_t offset)
{return {Float(words[offset]),Float(words[offset+1]),Float(words[offset+2])};}
Vec3 Add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
Vec3 Multiply(Vec3 v,float scalar){return {v.x*scalar,v.y*scalar,v.z*scalar};}
Vec3 Combine(Vec3 a,float weight,Vec3 b){return {std::fma(a.x,weight,b.x),std::fma(a.y,weight,b.y),std::fma(a.z,weight,b.z)};}
Vec3 Center(CollisionBody id,const std::array<BodySnapshot,BoardBodyCount>& bodies)
{return id.kind==CollisionBody::Kind::Board?bodies[id.index].rates.position:Vec3{};}
Vec3 Velocity(CollisionBody id,const std::array<BodySnapshot,BoardBodyCount>& bodies)
{return id.kind==CollisionBody::Kind::Board?bodies[id.index].rates.linear_velocity:Vec3{};}
}
void CollectBoardContactReports(std::vector<BoardContactReport>& output,const std::vector<ContactConstraint>& contacts,
    const std::array<BodySnapshot,BoardBodyCount>& bodies,float frequency)
{
    output.clear();const float frequency_squared=frequency*frequency;
    for(const auto& contact:contacts)
    {
        const auto& w=contact.words;const auto impulse=Vector(w,20);
        if((w[11]&8u)==0 || !(impulse.x>0.0f))continue;
        if(!((w[31]<BoardBodyCount && w[43]==0xffffffffu)||(w[43]<BoardBodyCount && w[31]==0xffffffffu)))continue;
        const auto a=CollisionBody::FromContactId(w[31]),b=CollisionBody::FromContactId(w[43]);
        const bool is_body_a=a.kind==CollisionBody::Kind::Board;
        const auto part=static_cast<BoardBodyId>((is_body_a?a:b).index);
        const auto other=is_body_a?b:a;
        if(output.size()==16)break;
        const auto normal=Vector(w,28);const std::array<Vec3,2> tangents{{Vector(w,40),Vector(w,52)}};
        const auto a_position=Add(Center(a,bodies),Vector(w,0)),b_position=Add(Center(b,bodies),Vector(w,4));
        const float a_weight=Float(w[35]),b_weight=Float(w[39]),inverse_weight=1.0f/(b_weight+a_weight);
        const auto position=Combine(a_position,a_weight,Multiply(b_position,b_weight));
        const auto friction=Combine(tangents[0],impulse.y,Multiply(tangents[1],impulse.z));
        const float sign=is_body_a?1.0f:-1.0f;
        output.push_back({part,other,is_body_a,Multiply(normal,sign),Multiply(position,inverse_weight),
            Subtract(Velocity(CollisionBody::Board(part),bodies),Velocity(other,bodies)),
            static_cast<std::uint16_t>(is_body_a?w[55]:w[55]>>16),
            Multiply(Multiply(normal,impulse.x),frequency_squared),Multiply(friction,frequency_squared),tangents});
    }
}
}
