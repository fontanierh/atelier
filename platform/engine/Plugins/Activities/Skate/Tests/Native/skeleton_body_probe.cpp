// SPDX-License-Identifier: Apache-2.0
#include "SkeletonBody.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> output;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec3 Vector(){return {Float(),Float(),Float()};}
template<std::size_t N>std::array<float,N> Floats(){std::array<float,N> a;for(auto& v:a)v=Float();return a;}
Mat4 Matrix(){Mat4 a;for(auto& v:a)v=Floats<4>();return a;}
template<std::size_t N>std::array<Mat4,N> Matrices(){std::array<Mat4,N> a;for(auto& v:a)v=Matrix();return a;}
std::array<Vec3,24> Sizes(){std::array<Vec3,24> a;for(auto& v:a)v=Vector();return a;}
HatGeometry Hat(){HatGeometry h;h.radius=Float();h.half_length=Float();for(auto& c:h.basis.columns)c=Floats<3>();h.translation=Vector();return h;}
SimulationStep Simulation(){return {Float(),Float(),Word(),Float(),Vector()};}
void Out(std::uint32_t w){output.push_back(w);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
template<class T,std::size_t N>void Out(const std::array<T,N>& a){for(const auto& v:a)Out(v);}
void Out(Basis3 b){Out(b.columns);}
void Out(const std::string& s){Out(static_cast<std::uint32_t>(s.size()));for(unsigned char c:s)Out(std::uint32_t(c));}
void Out(HatGeometry h){Out(h.radius);Out(h.half_length);Out(h.basis);Out(h.translation);}
void Out(SkeletonAnimationMasses m){Out(m.part_weights);Out(m.total);Out(m.fractional);}
void Out(SkeletonAnimationRecord r){Out(r.pose);Out(r.centre_of_mass);Out(r.centre_of_mass_delta);Out(r.com_to_deck_world);Out(r.com_to_deck_world_delta);Out(r.reset_scalar);Out(r.ComToDeck());}
void Out(SkeletonPhysicalRecord r){Out(r.pose);Out(r.positions);Out(r.velocities);Out(r.velocity_changes);Out(r.centre_of_mass);Out(r.centre_of_mass_velocity);Out(r.timestep);}
void Out(BoneSettings b){Out(b.mass_factor);Out(b.ragdoll_mass_factor);Out(std::uint32_t(b.has_collision));Out(std::uint32_t(b.use_root_drive));Out(b.volume_type);Out(b.volume_scalar);Out(b.num_parents);}
void Out(BodyMassProperties m){Out(m.local_mass_frame.basis);Out(m.local_mass_frame.translation);const auto d=m.dynamics;Out(d.inverse_tensor);for(float f:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag})Out(f);}
void Out(SkeletonBodyDefinition d)
{
    for(const auto& p:d.parts)
    {
        Out(static_cast<std::uint32_t>(p.shape.kind));Out(p.shape.radius);Out(p.shape.half_length);Out(p.shape.padding);Out(p.shape.half_extents);
        Out(std::uint32_t(p.hat.has_value()));Out(p.hat.value_or(HatGeometry{}));Out(p.animated);Out(p.ragdoll);Out(p.inverse_mass_animated);Out(p.inverse_mass_ragdoll);
    }
    for(const auto b:d.bones)Out(b);Out(d.animation_masses);
}
void Out(BodySnapshot b)
{
    Out(b.state_flags);const auto& r=b.rates;Out(r.orientation);Out(r.basis);Out(r.world_inverse_inertia);Out(r.position);Out(r.linear_velocity);Out(r.angular_velocity);
    Out(r.force_acceleration);Out(r.torque_acceleration);Out(r.kinetic_energy);Out(r.cool_down);const auto d=b.inertia;Out(d.inverse_tensor);
    for(float f:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag})Out(f);
}
void Out(const SkeletonBody& b){Out(b.animation_to_world);for(const auto& body:b.Bodies())Out(body);Out(b.PartTransforms());Out(b.record);}
std::optional<SkeletonBodyDefinition> Definition(std::string& error)
{
    const auto sizes=Sizes();std::array<BoneSettings,24> bones;
    for(auto& b:bones){b.mass_factor=Float();b.ragdoll_mass_factor=Float();b.has_collision=Word()!=0;b.use_root_drive=Word()!=0;b.volume_type=Word();b.volume_scalar=Float();b.num_parents=Word();}
    const SkeletonBodySettings settings{Float(),Float(),Float(),Float(),Float(),Float(),Word(),Float()};
    const auto hat=Word()!=0 ? std::optional<HatGeometry>(Hat()):std::nullopt;
    return SkeletonBodyDefinition::Build(sizes,bones,settings,hat,error);
}
SkeletonAnimationRecord AnimationRecord()
{
    SkeletonAnimationRecord r;if(Word()){r.pose=Matrices<24>();r.centre_of_mass=Floats<4>();r.centre_of_mass_delta=Floats<4>();r.com_to_deck_world=Floats<4>();r.com_to_deck_world_delta=Floats<4>();r.reset_scalar=Float();}return r;
}
SkeletonPhysicalRecord PhysicalRecord()
{
    SkeletonPhysicalRecord r;if(Word()){r.pose=Matrices<26>();for(auto& v:r.positions)v=Floats<4>();for(auto& v:r.velocities)v=Floats<4>();for(auto& v:r.velocity_changes)v=Floats<4>();r.centre_of_mass=Floats<4>();r.centre_of_mass_velocity=Floats<4>();r.timestep=Float();}return r;
}
}
int main()
{
    const auto cases=Word();for(std::uint32_t index=0;index<cases;++index)
    {
        const auto op=Word();Out(index);Out(op);const auto size_at=output.size();Out(0u);const auto start=output.size();
        switch(op)
        {
        case 0:{const float radius=Float(),thickness=Float();const auto angles=Vector(),translation=Vector();Out(HatGeometry::FromOffsets(radius,thickness,angles,translation));break;}
        case 1:Out(SkeletonAnimationMasses::Normalize(Floats<24>()));break;
        case 2:{const auto sizes=Sizes();std::array<std::uint32_t,24> shapes;for(auto& v:shapes)v=Word();Out(SkeletonAnimationMasses::FromBoneData(sizes,shapes,Word()!=0));break;}
        case 3:{const auto q=Floats<4>(),translation=Floats<4>();const auto a=Matrix(),b=Matrix();const auto point=Floats<4>();Out(PhysicsBoneFrame(q,translation));Out(ComposeSkeletonAffine(a,b));Out(InverseSkeletonRigid(a));Out(TransformSkeletonPoint(a,point));break;}
        case 4:
        {
            std::vector<Mat4> bones;const auto count=Word();for(std::uint32_t n=0;n<count;++n)bones.push_back(Matrix());
            std::array<std::size_t,24> indices;for(auto& v:indices)v=Word();const auto frames=Matrices<24>();auto result=Matrices<24>();const auto initial=result;std::string error;
            const bool ok=MapAnimationParts(bones,indices,frames,result,error);Out(std::uint32_t(ok));if(ok)Out(result);else {Out(error);if(result!=initial)return 3;}break;
        }
        case 5:
        {
            auto r=AnimationRecord();const auto m=SkeletonAnimationMasses::Normalize(Floats<24>());Out(m);Out(r);const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n){if(Word()==0)r.ResetHistory();else {const auto pose=Matrices<24>();const auto board=Matrix();r.Update(pose,board,m);}Out(r);}break;
        }
        case 6:
        {
            auto r=PhysicalRecord();const auto fractional=Floats<24>();Out(r);const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n){const auto cmd=Word();const auto parts=Matrices<26>();if(cmd==0)r.Reset(parts);else r.Update(parts,Matrix(),fractional);Out(r);}break;
        }
        case 7:{std::string error;const auto d=Definition(error);Out(std::uint32_t(d.has_value()));if(d)Out(*d);else Out(error);break;}
        case 8:
        {
            std::string error;auto d=Definition(error);if(!d)return 4;const auto authored=Matrices<24>();const auto spawn=Matrix();const auto simulation=Simulation();
            SkeletonBody body(std::move(*d),authored,spawn,simulation);Out(body);const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n)
            {
                const auto cmd=Word();
                if(cmd==0){const auto part=Word();body.SetPartTransform(part,Matrix());}
                else if(cmd==1){const auto part=Word();body.ApplyPartDisplacement(part,Floats<4>());}
                else if(cmd==2)body.PublishPhysicalRecord(Matrix());
                else if(cmd==3){auto& b=body.BodiesMut().at(Word());b.state_flags=Word();b.rates.linear_velocity=Vector();b.rates.angular_velocity=Vector();b.rates.force_acceleration=Vector();b.rates.torque_acceleration=Vector();b.rates.kinetic_energy=Float();b.rates.cool_down=Word();}
                else if(cmd==4){const auto step=Simulation();for(auto& b:body.BodiesMut()){const ReactionCorrections reaction{Vector(),Vector(),Vector(),Vector()};if(b.state_flags&4u)b.rates=IntegrateBodyRates(b.rates,b.inertia,step,reaction).state;}}
                else if(cmd==5)body.record.Reset(body.PartTransforms());else return 2;
                Out(body);
            }
            break;
        }
        default:return 2;
        }
        output[size_at]=static_cast<std::uint32_t>(output.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(auto w:output){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
