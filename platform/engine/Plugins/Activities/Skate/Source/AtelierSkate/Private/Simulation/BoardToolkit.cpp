#include "BoardToolkit.h"
#include <cstring>
namespace atelier::skate
{
namespace {float Float(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}}
BoardToolkit BoardToolkit::FromBoard(const BoardRuntime& board,std::uint32_t flags,float speed,Vec4 normal,Vec4 retained)
{
    const auto part=board.PartTransforms()[static_cast<std::size_t>(BoardBodyId::Deck)];Mat4 deck{};
    for(std::size_t i=0;i<3;++i){const auto c=part.basis.columns[i];deck[i]={c[0],c[1],c[2],0};}
    deck[3]={part.translation.x,part.translation.y,part.translation.z,1};std::vector<float> masses;
    for(const auto& body:board.Bodies())masses.push_back(body.inertia.inverse_mass);
    return Calculate(deck,masses,flags,speed,normal,retained);
}
BoardToolkit BoardToolkit::Calculate(Mat4 deck,const std::vector<float>& masses,
    std::uint32_t flags,float speed,Vec4 normal,Vec4 retained)
{
    const float sign=flags&0x00100000u?-1.0f:1.0f;auto effective=deck;
    for(const std::size_t axis:{0,2})for(std::size_t i=0;i<4;++i)effective[axis][i]=deck[axis][i]*sign;
    Mat4 inverse{};
    for(std::size_t axis=0;axis<3;++axis)for(std::size_t lane=0;lane<3;++lane)inverse[axis][lane]=effective[lane][axis];
    for(std::size_t lane=0;lane<4;++lane)
    {
        const float z=(0.0f-effective[3][2])*inverse[2][lane];
        const float yz=std::fma(0.0f-effective[3][1],inverse[1][lane],z);
        inverse[3][lane]=std::fma(0.0f-effective[3][0],inverse[0][lane],yz);
    }
    const auto side=effective[0],up=deck[1],forward=effective[2];auto horizontal=forward;horizontal[1]=0;
    const float horizontal_squared=Dot3(horizontal,horizontal);
    if(horizontal_squared>Float(0x3727c5ac))
    {const float inverse=InverseLengthSquared(horizontal_squared,2);for(auto& v:horizontal)v*=inverse;}
    const float parallel=Dot3(up,horizontal);Vec4 rejected,transverse;
    for(std::size_t i=0;i<4;++i)rejected[i]=up[i]-horizontal[i]*parallel;
    const float inverse_length=InverseLengthSquared(Dot3(rejected,rejected),2);
    for(std::size_t i=0;i<4;++i)transverse[i]=rejected[i]*inverse_length;
    const float travel=speed>0.0f?1.0f:-1.0f;Vec4 filtered;
    if(!(Dot3(retained,normal)<=Float(0x3f6f5c29)))filtered=normal;
    else
    {
        Vec4 blended;for(std::size_t i=0;i<4;++i)blended[i]=std::fma(retained[i],Float(0x3f666666),normal[i]*Float(0x3dcccccd));
        const float squared=Dot3(blended,blended),inverse=InverseLengthSquared(squared,2);
        const float length=squared==0.0f?0.0f:squared*inverse;
        if(length>Float(0x358637bd))for(std::size_t i=0;i<4;++i)filtered[i]=blended[i]*inverse;
        else filtered={};
    }
    Vec4 velocity,direction;for(std::size_t i=0;i<4;++i){velocity[i]=forward[i]*speed;direction[i]=forward[i]*travel;}
    return {deck,effective,inverse,side,up,forward,horizontal,transverse,velocity,direction,filtered,speed*travel,sign,TotalBodyMass(masses)};
}
}
