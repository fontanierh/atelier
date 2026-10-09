#include "ContactBuild.h"
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
std::array<float,3> Components(Vec3 v){return {v.x,v.y,v.z};}
Vec3 Vector(const std::array<std::uint32_t,64>& words,std::size_t row)
{return {Float(words[row*4]),Float(words[row*4+1]),Float(words[row*4+2])};}
Vec3 Difference(Vec3 a,Vec3 b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
std::array<float,3> Cross(Vec3 arm,Vec3 axis)
{
    return {std::fma(-arm.z,axis.y,std::fma(arm.y,axis.z,0.0f)),
        std::fma(-arm.x,axis.z,std::fma(arm.z,axis.x,0.0f)),
        std::fma(-arm.y,axis.x,std::fma(arm.x,axis.y,0.0f))};
}
Vec4 InertiaResponse(Vec3 full,Vec3 split,float mass,const std::array<float,3>& jacobian)
{
    const std::array<Vec4,3> columns{{{full.x,full.y,full.z,mass},{full.y,split.y,split.z,mass},{full.z,split.z,split.x,mass}}};
    Vec4 result{};
    for(std::size_t i=0;i<4;++i)
    {
        const float first=std::fma(columns[0][i],jacobian[0],0.0f);
        const float second=std::fma(columns[1][i],jacobian[1],first);
        result[i]=std::fma(columns[2][i],jacobian[2],second);
    }
    return result;
}
std::array<float,3> Project(const std::array<Vec3,3>& axes,Vec3 value)
{
    std::array<float,3> result{};
    for(std::size_t i=0;i<3;++i)
    {
        const float x=std::fma(axes[i].x,value.x,0.0f);
        const float xy=std::fma(axes[i].y,value.y,x);
        result[i]=std::fma(axes[i].z,value.z,xy);
    }
    return result;
}
void VectorRow(std::array<std::uint32_t,64>& words,std::size_t row,Vec3 xyz,std::uint32_t carry)
{
    words[row*4]=Word(xyz.x);words[row*4+1]=Word(xyz.y);words[row*4+2]=Word(xyz.z);words[row*4+3]=carry;
}
void FloatRow(std::array<std::uint32_t,64>& words,std::size_t row,const Vec4& values)
{for(std::size_t i=0;i<4;++i)words[row*4+i]=Word(values[i]);}
std::array<std::uint32_t,64> Compile(const ContactPreparation& p,const std::array<float,3>& inverse)
{
    std::array<std::uint32_t,64> words{};
    for(std::size_t body=0;body<2;++body)VectorRow(words,body,p.arms[body],p.reaction_ids[body]);
    const std::array<std::array<float,3>,3> axes{Components(p.axes[0]),Components(p.axes[1]),Components(p.axes[2])};
    const std::array<std::uint32_t,3> carry{p.combined_state_bit_8,p.static_friction_bits,p.dynamic_friction_bits};
    for(std::size_t component=0;component<3;++component)
    {
        const Vec3 column{std::fma(axes[0][component],inverse[0],0.0f),
            std::fma(axes[1][component],inverse[1],0.0f),std::fma(axes[2][component],inverse[2],0.0f)};
        VectorRow(words,2+component,column,carry[component]);
    }
    // The accumulator row is initially all zero, including its carry.
    const float separation=std::fma(p.separation_projection[0],inverse[0],0.0f);
    const float restitution=std::fma(p.restitution_projection[0],inverse[0],0.0f);
    std::array<float,3> predicted{};
    for(std::size_t i=0;i<3;++i)predicted[i]=std::fma(p.predicted_separation_projection[i],inverse[i],0.0f);
    float normal_adjustment=restitution>=0.0f?0.0f:separation+restitution;
    if(separation>=0.0f)normal_adjustment=restitution;
    if(0.0f>=predicted[0])normal_adjustment=0.0f;
    FloatRow(words,6,{predicted[0]-normal_adjustment,predicted[1]-0.0f,predicted[2]-0.0f,separation});
    const std::array<std::uint32_t,3> identifiers{p.body_ids[0],p.body_ids[1],p.contact_tag};
    for(std::size_t axis=0;axis<3;++axis)
    {
        VectorRow(words,7+axis*3,p.axes[axis],identifiers[axis]);
        auto a=p.angular_response_a[axis],b=p.angular_response_b[axis];
        if(axis==0){a[3]=p.inverse_mass[0];b[3]=p.inverse_mass[1];}
        FloatRow(words,8+axis*3,a);FloatRow(words,9+axis*3,b);
    }
    return words;
}
}
ContactPreparation PrepareContact(const std::array<std::uint32_t,64>& words,float time_step)
{
    ContactPreparation p;
    const std::array<Vec3,2> positions{Vector(words,0),Vector(words,1)};
    for(std::size_t i=0;i<3;++i)p.axes[i]=Vector(words,2+i);
    std::array<std::array<std::array<float,3>,3>,2> jacobians{};
    std::array<std::array<Vec4,3>,2> responses{};
    for(std::size_t body=0;body<2;++body)
    {
        p.arms[body]=Difference(positions[body],Vector(words,6+body));
        p.active[body]=(words[(10+body)*4+3]&4)==4;
        p.inverse_mass[body]=p.active[body]?Float(words[(8+body)*4+3]):0.0f;
        const auto full=p.active[body]?Vector(words,8+body):Vec3{};
        const auto split=p.active[body]?Vector(words,10+body):Vec3{};
        for(std::size_t axis=0;axis<3;++axis)
        {
            jacobians[body][axis]=Cross(p.arms[body],p.axes[axis]);
            responses[body][axis]=InertiaResponse(full,split,p.inverse_mass[body],jacobians[body][axis]);
        }
        if(p.active[body])
        {
            const auto arm=p.arms[body],force=Vector(words,12+body),torque=Vector(words,14+body);
            p.point_acceleration[body]={std::fma(arm.z,torque.y,std::fma(-arm.y,torque.z,force.x)),
                std::fma(arm.x,torque.z,std::fma(-arm.z,torque.x,force.y)),
                std::fma(arm.y,torque.x,std::fma(-arm.x,torque.y,force.z))};
        }
        p.reaction_ids[body]=words[(6+body)*4+3];p.body_ids[body]=words[body*4+3];
    }
    p.angular_response_a=responses[0];p.angular_response_b=responses[1];
    for(std::size_t axis=0;axis<3;++axis)
    {
        std::array<float,3> products{};
        for(std::size_t c=0;c<3;++c)
        {
            const float a=std::fma(jacobians[0][axis][c],responses[0][axis][c],0.0f);
            products[c]=std::fma(jacobians[1][axis][c],responses[1][axis][c],a);
        }
        p.effective_mass[axis]=(products[2]+(products[0]+p.inverse_mass[0]))+(products[1]+p.inverse_mass[1]);
    }
    const auto separation=Difference(positions[1],positions[0]);
    const auto relative_acceleration=Components(Difference(p.point_acceleration[1],p.point_acceleration[0]));
    const auto velocity=Components(Vector(words,5)),separation_components=Components(separation);
    const float restitution=Float(words[11]);
    std::array<float,3> predicted{},bounced{};
    for(std::size_t i=0;i<3;++i)
    {
        const float scaled=std::fma(time_step,velocity[i],0.0f);
        const float acceleration=std::fma(relative_acceleration[i],time_step*time_step,0.0f);
        predicted[i]=scaled+(separation_components[i]+acceleration);
        bounced[i]=std::fma(-scaled,restitution,0.0f);
    }
    p.separation_projection=Project(p.axes,separation);
    p.restitution_projection=Project(p.axes,{bounced[0],bounced[1],bounced[2]});
    p.predicted_separation_projection=Project(p.axes,{predicted[0],predicted[1],predicted[2]});
    p.static_friction_bits=words[15];p.dynamic_friction_bits=words[19];p.contact_tag=words[23];
    p.combined_state_bit_8=(words[43]|words[47])&8;
    return p;
}
bool BuildContactWithResponse(std::array<std::uint32_t,64>& record,float time_step,const ContactMassResponse& response)
{
    const auto prepared=PrepareContact(record,time_step);std::array<float,3> inverse{};
    if(!response(prepared.effective_mass,inverse))return false;
    record=Compile(prepared,inverse);return true;
}
void BuildContact(std::array<std::uint32_t,64>& record,float time_step)
{
    const auto prepared=PrepareContact(record,time_step);std::array<float,3> inverse{};
    for(std::size_t i=0;i<3;++i)inverse[i]=1.0f/prepared.effective_mass[i];
    record=Compile(prepared,inverse);
}
}
