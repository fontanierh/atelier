// Checker prepends the tested skeleton body/collision record adapters.
#include "SkeletonColliders.h"
#include "AssemblyContacts.h"
#include "SkeletonContactReports.h"
namespace
{
BodySnapshot ReadBody()
{
    BodySnapshot b;b.state_flags=Word();b.rates.orientation=Floats<4>();
    for(auto& c:b.rates.basis.columns)c=Floats<3>();for(auto& c:b.rates.world_inverse_inertia.columns)c=Floats<3>();
    b.rates.position=Vector();b.rates.linear_velocity=Vector();b.rates.angular_velocity=Vector();b.rates.force_acceleration=Vector();b.rates.torque_acceleration=Vector();b.rates.kinetic_energy=Float();b.rates.cool_down=Word();
    b.inertia.inverse_tensor=Vector();b.inertia.inverse_mass=Float();b.inertia.spherical=Float();b.inertia.maximum_linear_velocity=Float();b.inertia.maximum_angular_velocity=Float();b.inertia.linear_drag=Float();b.inertia.angular_drag=Float();return b;
}
AffineTransform ReadTransform(){AffineTransform t;for(auto& c:t.basis.columns)c=Floats<3>();t.translation=Vector();return t;}
ContactPrimitive ReadPrimitive()
{
    switch(Word())
    {
    case 0:return Sphere{Vector(),Float()};
    case 1:return Capsule{Vector(),Vector(),Float(),Float()};
    case 2:{const std::array<Vec3,3> v{{Vector(),Vector(),Vector()}};const float fat=Float();const auto cosines=Floats<3>();const auto flags=Word();return TransformTriangleVolume(v,fat,cosines,flags,ReadTransform());}
    case 3:{const auto center=Vector();Basis3 b;for(auto& c:b.columns)c=Floats<3>();const auto half=Vector();return RoundedBox{center,b,half,Float()};}
    default:std::abort();
    }
}
BoardWorldVolume ReadVolume(){const auto id=Word();const auto p=ReadPrimitive();const auto v=Vector();return {id,p,v,Material()};}
std::vector<BoardWorldVolume> ReadVolumes(){std::vector<BoardWorldVolume> v;const auto n=Word();for(std::uint32_t i=0;i<n;++i)v.push_back(ReadVolume());return v;}
void OutPrimitive(const ContactPrimitive& p)
{
    if(const auto* s=std::get_if<Sphere>(&p)){Out(0u);Out(s->center);Out(s->radius);}
    else if(const auto* s=std::get_if<Capsule>(&p)){Out(1u);Out(s->center);Out(s->axis);Out(s->half_length);Out(s->radius);}
    else if(const auto* t=std::get_if<Triangle>(&p)){Out(2u);Out(t->vertices);Out(t->feature.normal);Out(t->feature.edges);Out(t->feature.flags);Out(t->feature.edge_cosines);Out(t->edge_lengths);Out(t->fatness);}
    else{const auto& b=std::get<RoundedBox>(p);Out(3u);Out(b.center);Out(b.basis);Out(b.half_extents);Out(b.radius);}
}
void OutVolumes(const std::vector<BoardWorldVolume>& v){Out(static_cast<std::uint32_t>(v.size()));for(const auto& volume:v){Out(volume.body_contact_id);OutPrimitive(volume.primitive);Out(volume.linear_velocity);Out(volume.material.static_friction);Out(volume.material.dynamic_friction);Out(volume.material.restitution);}}
BoardCollision ReadCollision(){const auto a=Word(),b=Word();const auto pa=Vector(),pb=Vector(),normal=Vector();const float restitution=Float(),stat=Float(),dynamic=Float();return {CollisionBody::FromContactId(a),CollisionBody::FromContactId(b),{pa,pb,normal,restitution,stat,dynamic,Word()}};}
void OutCollisions(const std::vector<BoardCollision>& v){Out(static_cast<std::uint32_t>(v.size()));for(const auto& c:v){Out(c.body_a.ContactId());Out(c.body_b.ContactId());Out(c.contact.position_on_a);Out(c.contact.position_on_b);Out(c.contact.normal);Out(c.contact.restitution);Out(c.contact.static_friction);Out(c.contact.dynamic_friction);Out(c.contact.tag);}}
void OutReports(const std::vector<SkeletonContactReport>& v){Out(static_cast<std::uint32_t>(v.size()));for(const auto& r:v){Out(static_cast<std::uint32_t>(r.part));Out(r.normal);Out(r.point);Out(r.tag);Out(r.other_group);Out(std::uint32_t(r.other_entity.has_value()));Out(static_cast<std::uint32_t>(r.other_entity.value_or(0)));for(const auto b:{r.body_a,r.body_b}){Out(b.state_flags);Out(b.inverse_mass);Out(b.linear_velocity);}Out(std::uint32_t(r.side_a));Out(r.solved_vector);}}
SkeletonBody ReadSkeleton(){std::string error;auto d=Definition(error);if(!d)std::abort();const auto authored=Matrices<24>();const auto spawn=Matrix();return SkeletonBody(std::move(*d),authored,spawn,Simulation());}
}
int main()
{
    const auto count=Word();for(std::uint32_t index=0;index<count;++index)
    {
        const auto op=Word();Out(index);Out(op);const auto mark=output.size();Out(0u);const auto start=output.size();
        if(op==0)
        {
            auto body=ReadSkeleton();const auto settings=CollisionSettings();SkeletonCollisionMode mode(settings,Word()!=0);const auto n=Word();Out(n);
            for(std::uint32_t j=0;j<n;++j)
            {
                const auto cmd=Word();Out(cmd);
                switch(cmd)
                {
                case 0:{auto& p=mode.parts.at(Word());p.enabled=Word()!=0;p.volume_group=Word();p.part_group=Word();p.material=Material();break;}
                case 1:{auto& p=body.definition.parts.at(Word());p.shape.kind=static_cast<MassShapeKind>(Word());p.shape.radius=Float();p.shape.half_length=Float();p.shape.padding=Float();p.shape.half_extents=Vector();break;}
                case 2:{auto& p=body.definition.parts.at(Word());if(Word()!=0)p.hat=Hat();else p.hat.reset();break;}
                case 3:{const auto p=Word();body.SetPartTransform(p,Matrix());break;}
                case 4:{const auto part=Word();body.BodiesMut().at(part)=ReadBody();break;}
                default:return 2;
                }
                std::string error;auto enabled=SkeletonEnabledVolumes(body,mode,error);Out(std::uint32_t(enabled.has_value()));if(enabled)OutVolumes(*enabled);else Out(error);
                auto world=SkeletonWorldVolumes(body,mode,error);Out(std::uint32_t(world.has_value()));if(world)OutVolumes(*world);else Out(error);
                Out(body);OutMode(mode);
            }
        }
        else if(op==1)
        {
            const auto settings=CollisionSettings();SkeletonCollisionMode mode(settings,Word()!=0);mode.assembly_group=Word();for(auto& p:mode.parts)p.part_group=Word();for(auto& row:mode.self_culling)for(auto& b:row)b=Word()!=0;
            const auto board_group=Word();const auto board=ReadVolumes(),rider=ReadVolumes();std::vector<BoardCollision> contacts;const auto initial=Word();for(std::uint32_t j=0;j<initial;++j)contacts.push_back(ReadCollision());
            std::string error;const bool ok=AppendAssemblyContacts(contacts,board,rider,board_group,mode,error);Out(std::uint32_t(ok));if(!ok)Out(error);OutCollisions(contacts);
        }
        else if(op==2)
        {
            std::array<BodySnapshot,7> board;for(auto& b:board)b=ReadBody();std::vector<BodySnapshot> attached;const auto n=Word();for(std::uint32_t j=0;j<n;++j)attached.push_back(ReadBody());std::vector<const BodySnapshot*> owners;for(const auto& b:attached)owners.push_back(&b);
            const auto local=Word(),board_group=Word(),rider_group=Word();const float frequency=Float();const auto nr=Word();std::vector<ContactConstraint> rows;for(std::uint32_t j=0;j<nr;++j){ContactConstraint c;for(auto& w:c.words)w=Word();rows.push_back(c);}
            std::vector<SkeletonContactReport> reports;CollectSkeletonContactReports(reports,rows,{board,owners,local,board_group,rider_group},frequency);OutReports(reports);
        }
        else return 2;
        output[mark]=static_cast<std::uint32_t>(output.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(const auto w:output){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
