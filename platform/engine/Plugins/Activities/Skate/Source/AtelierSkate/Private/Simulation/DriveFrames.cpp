#include "DriveFrames.h"
#include "DeckGeometry.h"
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::uint32_t Word(float value){std::uint32_t word;std::memcpy(&word,&value,4);return word;}
Vec3 Multiply(Basis3 basis,Vec3 vector)
{
    std::array<float,3> output{};
    for(std::size_t i=0;i<3;++i)output[i]=std::fma(vector.z,basis.columns[2][i],
        std::fma(vector.y,basis.columns[1][i],vector.x*basis.columns[0][i]));
    return {output[0],output[1],output[2]};
}
Basis3 Multiply(Basis3 left,Basis3 right)
{
    Basis3 output;
    for(std::size_t c=0;c<3;++c)for(std::size_t r=0;r<3;++r)
        output.columns[c][r]=std::fma(right.columns[c][2],left.columns[2][r],
            std::fma(right.columns[c][1],left.columns[1][r],right.columns[c][0]*left.columns[0][r]));
    return output;
}
Basis3 RotationX(float angle)
{
    const auto sc=SinCos(angle);return {{{{1,0,0},{0,sc.second,sc.first},{0,-sc.first,sc.second}}}};
}
Basis3 RotationY(float angle)
{
    const auto sc=SinCos(angle);return {{{{sc.second,0,-sc.first},{0,1,0},{sc.first,0,sc.second}}}};
}
Quat Candidate(float sum,Quat companion,std::size_t dominant)
{
    const float inverse=InverseLengthSquared(sum),half_inverse=inverse*0.5f,half_root=(sum*inverse)*0.5f;
    for(auto& value:companion)value*=half_inverse;
    companion[dominant]=half_root;return companion;
}
AffineTransform Inverse(AffineTransform transform)
{
    AffineTransform result;
    for(std::size_t c=0;c<3;++c)for(std::size_t r=0;r<3;++r)result.basis.columns[c][r]=transform.basis.columns[r][c];
    const auto t=Multiply(result.basis,transform.translation);
    result.translation={0.0f-t.x,0.0f-t.y,0.0f-t.z};return result;
}
AffineTransform Compose(AffineTransform parent,AffineTransform local)
{
    const auto t=Multiply(parent.basis,local.translation);
    return {Multiply(parent.basis,local.basis),{t.x+parent.translation.x,t.y+parent.translation.y,t.z+parent.translation.z}};
}
DriveFrames WheelFrame(float offset){DriveFrames result;result.body_b.translation={0,0,offset};return result;}
DriveFrameRaw Pack(DriveFrame frame)
{
    return {{Word(frame.orientation[0]),Word(frame.orientation[1]),Word(frame.orientation[2]),Word(frame.orientation[3])},
        {Word(frame.translation.x),Word(frame.translation.y),Word(frame.translation.z),0}};
}
}
AuthoredTransformInputs AuthoredTransformInputs::Stock()
{
    return {Float(0x3f170a3d),Float(0x3dc28f5c),Float(0xbd54fdf4),Float(0xbd54fdf4),Float(0xbd676c8b)};
}
TruckTransformInputs TruckTransformInputs::Stock()
{
    return {Float(0x3f170a3d),Float(0xbd54fdf4),Float(0xbd54fdf4),Float(0xbd676c8b),Float(0x41f80000)};
}
std::array<AffineTransform,7> AuthoredBodyTransforms(AuthoredTransformInputs input)
{
    const float front=std::fma(input.deck_mid_length,0.5f,input.truck_z_position_front);
    const float back=-std::fma(input.deck_mid_length,0.5f,input.truck_z_position_back),x=input.wheel_x_distance,y=input.truck_y_position;
    const std::array<Vec3,6> translations{{{-x,y,front},{x,y,front},{-x,y,back},{x,y,back},{0,y,front},{0,y,back}}};
    std::array<AffineTransform,7> result{};
    for(std::size_t i=0;i<6;++i)result[i].translation=translations[i];
    result[5].basis=RotationY(Float(0x3fc90fdb));return result;
}
std::array<std::array<std::uint32_t,16>,7> AuthoredBodyPoseRecords(AuthoredTransformInputs input)
{
    const auto frames=AuthoredBodyTransforms(input);std::array<std::array<std::uint32_t,16>,7> result{};
    for(std::size_t i=0;i<7;++i)
    {
        const auto& frame=frames[i];auto& words=result[i];
        for(std::size_t c=0;c<3;++c)for(std::size_t r=0;r<3;++r)words[c*4+r]=Word(frame.basis.columns[c][r]);
        words[12]=Word(frame.translation.x);words[13]=Word(frame.translation.y);words[14]=Word(frame.translation.z);
    }
    return result;
}
std::array<AffineTransform,2> CalculateTruckTransforms(TruckTransformInputs input)
{
    const float alpha=input.truck_rotation_axis_angle_degrees*Float(0x3c8efa35);
    const float front=std::fma(input.deck_mid_length,0.5f,input.truck_z_position_front);
    const float back=-std::fma(input.deck_mid_length,0.5f,input.truck_z_position_back);
    return {{AffineTransform{Multiply(RotationX(alpha),RotationY(Float(0x3fc90fdb))),{0,input.truck_y_position,back}},
        AffineTransform{Multiply(RotationX(-alpha),RotationY(Float(0xbfc90fdb))),{0,input.truck_y_position,front}}}};
}
Quat QuaternionFromBasis(Basis3 basis)
{
    const auto& m=basis.columns;
    const float m00=m[0][0],m01=m[1][0],m02=m[2][0],m10=m[0][1],m11=m[1][1],m12=m[2][1],m20=m[0][2],m21=m[1][2],m22=m[2][2];
    const float trace=(m00+m11)+m22;
    if(trace>0.0f)return Candidate((m00+m11)+(m22+1.0f),{m21-m12,m02-m20,m10-m01,0},3);
    if(m00>m11&&m00>m22)return Candidate((m00-m11)+((0.0f-m22)+1.0f),{0,m01+m10,m02+m20,m21-m12},0);
    if(m11>m22)return Candidate(((0.0f-m00)+m11)+((0.0f-m22)+1.0f),{m01+m10,0,m12+m21,m02-m20},1);
    return Candidate(((0.0f-m00)-m11)+(m22+1.0f),{m02+m20,m12+m21,0,m10-m01},2);
}
DriveFrames SetDriveFrames2(AffineTransform parent,AffineTransform child)
{
    Basis3 basis;
    for(std::size_t c=0;c<3;++c)for(std::size_t r=0;r<3;++r)
        basis.columns[c][r]=std::fma(child.basis.columns[c][2],parent.basis.columns[r][2],
            std::fma(child.basis.columns[c][1],parent.basis.columns[r][1],child.basis.columns[c][0]*parent.basis.columns[r][0]));
    const Vec3 negative{0.0f-parent.translation.x,0.0f-parent.translation.y,0.0f-parent.translation.z};
    std::array<float,3> translation{};
    for(std::size_t i=0;i<3;++i)
    {
        const auto& axis=parent.basis.columns[i];
        float value=negative.z*axis[2];value=std::fma(negative.y,axis[1],value);value=std::fma(negative.x,axis[0],value);
        value=std::fma(child.translation.x,axis[0],value);value=std::fma(child.translation.y,axis[1],value);
        translation[i]=std::fma(child.translation.z,axis[2],value);
    }
    return {{},{QuaternionFromBasis(basis),{translation[0],translation[1],translation[2]}}};
}
DriveFramesRaw PackDriveFrames(DriveFrames frames){return {Pack(frames.body_a),Pack(frames.body_b)};}
std::array<AffineTransform,7> DefaultLiveBodyTransforms()
{
    auto frames=AuthoredBodyTransforms(AuthoredTransformInputs::Stock());const auto mass=StockDeckMassProperties().local_mass_frame;
    frames[6]=Compose(frames[6],Inverse({mass.basis,mass.translation}));return frames;
}
std::array<Quat,7> DefaultLiveBodyOrientations()
{
    const auto frames=DefaultLiveBodyTransforms();std::array<Quat,7> result{};
    for(std::size_t i=0;i<7;++i)result[i]=QuaternionFromBasis(frames[i].basis);
    return result;
}
std::array<DriveFrames,2> DefaultTruckDriveFrames()
{
    const auto base=CalculateTruckTransforms(TruckTransformInputs::Stock());return {SetDriveFrames2({},base[1]),SetDriveFrames2({},base[0])};
}
std::array<DriveFrames,4> DefaultWheelDriveFrames()
{
    const float x=AuthoredTransformInputs::Stock().wheel_x_distance;const auto positive=WheelFrame(x),negative=WheelFrame(-x);
    return {positive,negative,positive,negative};
}
}
