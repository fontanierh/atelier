// SPDX-License-Identifier: Apache-2.0
#include "AggregateMass.h"
#include <cstring>
#include <limits>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
using Matrix3=std::array<std::array<float,3>,3>;
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
float Select(float selector,float positive,float negative){return selector>=0.0f?positive:negative;}
Vec4 Product(const Mat4& matrix,const Vec4& vector)
{
    Vec4 result{};
    for(std::size_t i=0;i<4;++i)
        result[i]=std::fma(matrix[3][i],vector[3],std::fma(matrix[2][i],vector[2],
            std::fma(matrix[1][i],vector[1],matrix[0][i]*vector[0])));
    return result;
}
std::pair<float,float> Rotation(const Matrix3& matrix,std::size_t row,std::size_t column)
{
    const float off_diagonal=matrix[row][column];
    if(off_diagonal==0.0f)return {0.0f,1.0f};
    const float difference=matrix[column][column]-matrix[row][row];
    const float theta=RefinedReciprocal(off_diagonal)*(difference*0.5f);
    const float length=std::sqrt(std::fma(theta,theta,1.0f));
    const float tangent=theta>0.0f?1.0f/(length+theta):-1.0f/(length-theta);
    const float cosine=1.0f/std::sqrt(std::fma(tangent,tangent,1.0f));
    return {cosine*tangent,cosine};
}
void RotateColumns(Matrix3& matrix,std::size_t a,std::size_t b,float sine,float cosine)
{
    for(auto& row:matrix)
    {
        const float left=row[a],right=row[b];
        row[a]=left*cosine-right*sine;
        row[b]=std::fma(left,sine,right*cosine);
    }
}
void RotateRows(Matrix3& matrix,std::size_t a,std::size_t b,float sine,float cosine)
{
    const auto left=matrix[a],right=matrix[b];
    for(std::size_t i=0;i<3;++i)
    {
        matrix[a][i]=left[i]*cosine-right[i]*sine;
        matrix[b][i]=std::fma(left[i],sine,right[i]*cosine);
    }
}
Matrix3 Diagonalize(Matrix3& inertia)
{
    Matrix3 axes{{{1,0,0},{0,1,0},{0,0,1}}};unsigned remaining=10;
    for(;;)
    {
        const std::array<float,3> diagonal{inertia[0][0]*inertia[0][0],inertia[1][1]*inertia[1][1],inertia[2][2]*inertia[2][2]};
        const float smallest=diagonal[1]>diagonal[0]?(diagonal[2]>diagonal[0]?diagonal[0]:diagonal[2])
            :(diagonal[2]>diagonal[1]?diagonal[1]:diagonal[2]);
        const float residual=std::fma(inertia[2][1],inertia[2][1],std::fma(inertia[1][0],inertia[1][0],inertia[2][0]*inertia[2][0]));
        if(!(residual>smallest*1.0e-24f)||remaining==0)break;
        for(std::size_t row=1;row<3;++row)for(std::size_t column=0;column<row;++column)
        {
            const auto sc=Rotation(inertia,row,column);
            RotateColumns(axes,row,column,sc.first,sc.second);
            RotateColumns(inertia,row,column,sc.first,sc.second);
            RotateRows(inertia,row,column,sc.first,sc.second);
        }
        --remaining;
    }
    return axes;
}
LocalMassFrame InverseMassFrame(const LocalMassFrame& forward,Vec3 inertia)
{
    const auto center=forward.translation;
    const float squared=Dot3(center,center);
    const float threshold=((inertia.y+inertia.z)+inertia.x)*Float(0x358637be);
    const bool translated=!(squared<threshold);
    bool rotated=false;
    for(std::size_t column=0;column<3;++column)for(std::size_t row=0;row<3;++row)
        rotated=rotated || std::fabs(forward.basis.columns[column][row]-(column==row?1.0f:0.0f))>Float(0x3a83126f);
    if(!translated&&!rotated)return {};
    LocalMassFrame inverse;
    for(std::size_t column=0;column<3;++column)for(std::size_t row=0;row<3;++row)
        inverse.basis.columns[column][row]=forward.basis.columns[row][column];
    const std::array<float,3> negative{0.0f-center.x,0.0f-center.y,0.0f-center.z};
    std::array<float,3> translation{};
    for(std::size_t row=0;row<3;++row)
        translation[row]=std::fma(negative[0],inverse.basis.columns[0][row],
            std::fma(negative[1],inverse.basis.columns[1][row],negative[2]*inverse.basis.columns[2][row]));
    inverse.translation={translation[0],translation[1],translation[2]};return inverse;
}
BodyMassProperties Finalize(LocalMassFrame frame,float mass,Vec3 principal,float maximum_angular_velocity,float angular_drag)
{
    const Vec3 inverse{RefinedReciprocal(principal.x),RefinedReciprocal(principal.y),RefinedReciprocal(principal.z)};
    const float xy=inverse.x<inverse.y?inverse.x:inverse.y;
    const float smallest=xy<inverse.z?xy:inverse.z;
    return {frame,{inverse,1.0f/mass,1.0f/smallest,Float(0x7f7fffff),maximum_angular_velocity,0.0f,angular_drag}};
}
}
MassMoments MassMoments::FromPrimitive(PrimitiveMass primitive)
{
    const auto i=primitive.moments_per_unit_mass;const float volume=primitive.volume;
    const float x=(((i.z+i.y)-i.x)*volume)*0.5f;
    const float y=(((i.z+i.x)-i.y)*volume)*0.5f;
    const float z=(((i.y+i.x)-i.z)*volume)*0.5f;
    MassMoments result;result.columns={{{x,0,0,0},{0,y,0,0},{0,0,z,0},{0,0,0,volume}}};return result;
}
void MassMoments::Transform(Basis3 basis,Vec3 translation)
{
    Mat4 affine{};
    for(std::size_t column=0;column<3;++column)for(std::size_t row=0;row<3;++row)affine[column][row]=basis.columns[column][row];
    affine[3]={translation.x,translation.y,translation.z,1.0f};Mat4 left{};
    for(std::size_t column=0;column<4;++column)left[column]=Product(affine,columns[column]);
    for(std::size_t column=0;column<4;++column)
        columns[column]=Product(left,{affine[0][column],affine[1][column],affine[2][column],affine[3][column]});
}
void MassMoments::Add(const MassMoments& child)
{for(std::size_t c=0;c<4;++c)for(std::size_t r=0;r<4;++r)columns[c][r]+=child.columns[c][r];}
AggregateMassProperties MassMoments::PrincipalProperties()
{
    const float volume=columns[3][3],inverse_volume=RefinedReciprocal(volume);
    const Vec3 center{columns[3][0]*inverse_volume,columns[3][1]*inverse_volume,columns[3][2]*inverse_volume};
    Transform(LocalMassFrame{}.basis,{-center.x,-center.y,-center.z});const auto& m=columns;
    const float xy=(m[1][0]+m[0][1])*-0.5f,xz=(m[2][0]+m[0][2])*-0.5f,yz=(m[2][1]+m[1][2])*-0.5f;
    Matrix3 inertia{{{m[1][1]+m[2][2],xy,xz},{xy,m[0][0]+m[2][2],yz},{xz,yz,m[0][0]+m[1][1]}}};
    const auto axes=Diagonalize(inertia);
    const float maximum_yz=Select(inertia[1][1]-inertia[2][2],inertia[1][1],inertia[2][2]);
    const float maximum=Select(inertia[0][0]-maximum_yz,inertia[0][0],maximum_yz),floor=maximum*0.0050000004f;
    std::array<float,3> moments{};for(std::size_t i=0;i<3;++i)moments[i]=Select(inertia[i][i]-floor,inertia[i][i],floor)*inverse_volume;
    LocalMassFrame frame;frame.translation=center;
    for(std::size_t i=0;i<3;++i)for(std::size_t j=0;j<3;++j)frame.basis.columns[i][j]=axes[j][i];
    return {volume,frame,{moments[0],moments[1],moments[2]}};
}
WheelMassSettings WheelMassSettings::Stock(){return {Float(0x3cfdf3b6),Float(0x3da9fbe7),Float(0x40a00000)};}
TruckMassSettings TruckMassSettings::Stock(){return {Float(0x3cfdf3b6),Float(0x3dc28f5c),Float(0x3f09999a),Float(0x3faccccd),Float(0x3ec7ae14),Float(0x40a00000)};}
PartMassInput WheelMassInput(WheelMassSettings s)
{
    MassShape shape;shape.kind=MassShapeKind::Sphere;shape.radius=s.radius;return {shape,s.mass*s.mass_factor};
}
PartMassInput TruckMassInput(TruckMassSettings s)
{
    MassShape shape;shape.kind=MassShapeKind::Capsule;shape.radius=(s.wheel_radius*s.radius_scalar)*0.5f;
    shape.half_length=(s.wheel_x_distance*s.half_height_scalar)*0.5f;return {shape,s.mass*s.mass_factor};
}
std::optional<ForwardMassProperties> ComputeForwardMassProperties(PartMassInput input)
{
    const auto primitive=ComputePrimitiveMass(input.shape);if(!primitive)return std::nullopt;
    const float mass=input.requested_mass<std::numeric_limits<float>::min()?primitive->volume:input.requested_mass;
    const auto i=primitive->moments_per_unit_mass;
    return ForwardMassProperties{*primitive,mass,{i.x*mass,i.y*mass,i.z*mass}};
}
std::optional<BodyMassProperties> ComputePrimitiveMassProperties(PartMassInput input,float maximum_angular_velocity,float angular_drag)
{
    const auto forward=ComputeForwardMassProperties(input);if(!forward)return std::nullopt;
    return Finalize({},forward->mass,forward->principal_moments,maximum_angular_velocity,angular_drag);
}
BodyMassProperties ComputeAggregateMassProperties(MassMoments moments,float requested_mass,float maximum_angular_velocity,float angular_drag)
{
    const auto properties=moments.PrincipalProperties();
    const float mass=requested_mass<std::numeric_limits<float>::min()?properties.volume:requested_mass;
    const auto i=properties.moments_per_unit_mass;
    return Finalize(InverseMassFrame(properties.local_mass_frame,i),mass,{i.x*mass,i.y*mass,i.z*mass},maximum_angular_velocity,angular_drag);
}
BodyMassProperties WheelMassProperties(WheelMassSettings settings)
{
    const auto forward=*ComputeForwardMassProperties(WheelMassInput(settings));
    return Finalize({},forward.mass,forward.principal_moments,Float(0x476a5fff),0.0f);
}
BodyMassProperties TruckMassProperties(TruckMassSettings settings)
{
    const auto forward=*ComputeForwardMassProperties(TruckMassInput(settings));
    return Finalize({},forward.mass,forward.principal_moments,Float(0x7f7fffff),0.0f);
}
}
