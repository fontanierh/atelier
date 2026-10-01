// SPDX-License-Identifier: Apache-2.0
// The checker prepends the record readers/encoders from skeleton_body_probe.cpp.
#include "SkeletonJoints.h"
#include "SkeletonDrives.h"
namespace
{
BodySnapshot ReadBody()
{
    BodySnapshot b;b.state_flags=Word();auto& r=b.rates;r.orientation=Floats<4>();for(auto& c:r.basis.columns)c=Floats<3>();for(auto& c:r.world_inverse_inertia.columns)c=Floats<3>();
    r.position=Vector();r.linear_velocity=Vector();r.angular_velocity=Vector();r.force_acceleration=Vector();r.torque_acceleration=Vector();r.kinetic_energy=Float();r.cool_down=Word();
    auto& d=b.inertia;d.inverse_tensor=Vector();d.inverse_mass=Float();d.spherical=Float();d.maximum_linear_velocity=Float();d.maximum_angular_velocity=Float();d.linear_drag=Float();d.angular_drag=Float();return b;
}
std::array<std::optional<std::size_t>,24> Parents()
{std::array<std::optional<std::size_t>,24> a;for(auto& p:a){const auto w=Word();if(w!=0xffffffffu)p=w;}return a;}
BoneDriveSettings DriveSettings()
{
    BoneDriveSettings s;for(auto& a:s.animation)a={Float(),Float(),Float(),Float()};s.collision_soft_displacement=Float();s.collision_soft_strength=Float();s.ragdoll_soft_displacement=Float();s.ragdoll_soft_strength=Float();
    for(auto* t:{&s.transition_linear,&s.transition_angular}){t->spring=Floats<2>();t->strength=Floats<2>();t->damping=Floats<2>();}s.transition_calls=Float();return s;
}
void OutParams(DriveParams p){Out(p.spring_or_max_velocity);Out(p.damping);Out(p.max_strength);Out(static_cast<std::uint32_t>(p.type));}
void OutDynamics(DriveDynamics d){OutParams(d.linear);OutParams(d.angular);}
void OutBoneDynamics(BoneDriveDynamics d){for(const auto c:d.channels)OutDynamics(c);Out(d.mode);Out(d.strengths);Out(d.transition_counter);Out(std::uint32_t(d.transition_active));}
void OutFrames(DriveFrames f){Out(f.body_a.orientation);Out(f.body_a.translation);Out(f.body_b.orientation);Out(f.body_b.translation);}
void OutDriveSettings(BoneDriveSettings s)
{for(const auto a:s.animation){Out(a.linear_strength);Out(a.linear_displacement);Out(a.angular_strength);Out(a.angular_displacement);}Out(s.collision_soft_displacement);Out(s.collision_soft_strength);Out(s.ragdoll_soft_displacement);Out(s.ragdoll_soft_strength);for(const auto t:{s.transition_linear,s.transition_angular}){Out(t.spring);Out(t.strength);Out(t.damping);}Out(s.transition_calls);}
void OutDrives(const SkeletonDrives& d)
{
    for(const auto& b:d.targets.bodies)Out(b);for(const auto f:d.targets.frames)OutFrames(f);for(const auto p:d.targets.dynamics)OutDynamics(p);
    for(std::size_t i=0;i<4;++i)Out(d.targets.Transform(i));
    for(const auto& p:d.bones)
    {
        Out(std::uint32_t(p.has_value()));if(!p)continue;
        for(const auto parent:p->parent)Out(static_cast<std::uint32_t>(parent));for(const auto active:p->active)Out(std::uint32_t(active));
        for(const auto f:p->frames)OutFrames(f);OutBoneDynamics(p->dynamics);
    }
    OutDriveSettings(d.settings.bone);Out(std::uint32_t(d.settings.enabled));Out(d.settings.strength);Out(d.settings.collision_strength);
}
void MutateBody(BodySnapshot& b)
{b.state_flags=Word();b.rates.linear_velocity=Vector();b.rates.angular_velocity=Vector();b.rates.force_acceleration=Vector();b.rates.torque_acceleration=Vector();b.rates.kinetic_energy=Float();b.rates.cool_down=Word();}
void OutSnapshot(const SkeletonBody& b,const SkeletonDrives& d){Out(b);OutDrives(d);}
}
int main()
{
    const auto cases=Word();for(std::uint32_t index=0;index<cases;++index)
    {
        const auto op=Word();Out(index);Out(op);const auto size_at=output.size();Out(0u);const auto start=output.size();
        switch(op)
        {
        case 0:
        {
            const auto initial=Matrices<24>();const auto parents=Parents();std::array<SkeletonJointBone,24> bones;
            for(auto& b:bones){b.parent_orientation=Floats<4>();b.joint_orientation=Floats<4>();b.volume_frame=Matrix();b.swing_limit=Float();b.twist_limit=Float();}
            std::array<SkeletonJointBoneSettings,22> settings;for(auto& s:settings)s={Word()!=0,Float(),Float(),Float(),Float()};
            const SkeletonJointSettings global{Floats<4>(),Float(),Float(),Word()!=0,Word()!=0};std::string error;
            const auto joints=SkeletonJoints::FromDefinition(initial,parents,bones,settings,global,error);Out(std::uint32_t(joints.has_value()));
            if(!joints){Out(error);break;}
            for(const auto& r:joints->records){Out(static_cast<std::uint32_t>(r.parent));Out(static_cast<std::uint32_t>(r.child));Out(r.parameters);Out(r.frames);}
            std::array<BodySnapshot,26> bodies;for(auto& b:bodies)b=ReadBody();const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n){for(auto& b:bodies)b.state_flags=Word();const auto base=Word();const float dt=Float();const auto rows=joints->Build(bodies,base,dt);Out(static_cast<std::uint32_t>(rows.size()));for(const auto& row:rows){Out(row.words);Out(static_cast<std::uint32_t>(row.reaction_a));Out(static_cast<std::uint32_t>(row.reaction_b));}}break;
        }
        case 1:
        {
            const auto settings=DriveSettings();BoneDriveDynamics d;
            for(auto& c:d.channels){c.linear={Float(),Float(),Float(),static_cast<DriveType>(Word())};c.angular={Float(),Float(),Float(),static_cast<DriveType>(Word())};}
            d.mode=Word();d.strengths=Floats<2>();d.transition_counter=Float();d.transition_active=Word()!=0;OutBoneDynamics(d);const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n){d.mode=Word();const auto channel=Word();const float strength=Float();d.Enable(channel,strength,settings);OutBoneDynamics(d);}break;
        }
        case 2:
        {
            const auto child=Matrix(),inverse_child=Matrix(),inverse_parent=Matrix();auto frames=BoneDriveFrames(child,inverse_child,inverse_parent);OutFrames(frames);
            const auto count=Word();Out(count);for(std::uint32_t n=0;n<count;++n){frames=PrepareBoneDriveFrames(frames);OutFrames(frames);}break;
        }
        case 3:
        {
            std::string error;auto definition=Definition(error);if(!definition)return 4;const auto authored=Matrices<24>();const auto spawn=Matrix();const auto simulation=Simulation();SkeletonBody body(std::move(*definition),authored,spawn,simulation);
            const auto initial=Matrices<24>(),mapped=Matrices<24>();const auto parents=Parents();const auto alignment=Matrix();SkeletonDriveSettings settings;settings.bone=DriveSettings();settings.enabled=Word()!=0;settings.strength=Floats<2>();for(auto& s:settings.collision_strength)s=Floats<2>();
            auto drives=SkeletonDrives::FromDefinition(initial,mapped,parents,alignment,spawn,simulation,settings,error);Out(std::uint32_t(drives.has_value()));if(!drives){Out(error);break;}OutSnapshot(body,*drives);const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n)
            {
                const auto cmd=Word();Out(cmd);
                switch(cmd)
                {
                case 0:{const bool partial=Word()!=0;const float weight=Float();drives->Update(Matrices<24>(),partial,weight);break;}
                case 1:{const auto part=Word(),channel=Word();const bool active=Word()!=0;drives->bones.at(part).value().active.at(channel)=active;break;}
                case 2:drives->settings.enabled=Word()!=0;drives->settings.strength=Floats<2>();break;
                case 3:{const auto target=Word();drives->targets.SetTransform(target,Matrix());break;}
                case 4:{const auto hips=Matrix(),root=Matrix();drives->targets.Reset(hips,root);break;}
                case 5:drives->targets.ApplyFutureDeckDisplacement(Vector());break;
                case 6:
                {
                    const auto frames=Matrices<7>();const bool teleporting=Word()!=0;
                    const SkeletonTargetInput input{frames[0],frames[1],frames[2],frames[3],frames[4],frames[5],frames[6],teleporting};
                    const auto update=drives->targets.UpdatePositions(input,body);Out(update.animation_board_to_physics);Out(update.positions.com);Out(update.positions.lifted_com);Out(update.positions.following_com);Out(std::uint32_t(update.continuous));break;
                }
                case 7:
                {
                    const auto base=Word(),target_base=Word();const float dt=Float();const auto batch=drives->Build(body.Bodies(),base,target_base,dt);Out(static_cast<std::uint32_t>(batch.rows.size()));
                    for(std::size_t i=0;i<batch.rows.size();++i){const auto row=PackDrive(batch.rows[i]);Out(row.words);Out(static_cast<std::uint32_t>(row.reaction_a));Out(static_cast<std::uint32_t>(row.reaction_b));const auto id=batch.identities[i];Out(static_cast<std::uint32_t>(id.kind));Out(static_cast<std::uint32_t>(id.index));Out(static_cast<std::uint32_t>(id.channel));Out(std::uint32_t(batch.spy[i]));}break;
                }
                case 8:MutateBody(body.BodiesMut().at(Word()));break;
                case 9:MutateBody(drives->targets.bodies.at(Word()));break;
                case 10:{const auto part=Word();drives->bones.at(part).reset();break;}
                default:return 2;
                }
                OutSnapshot(body,*drives);
            }
            break;
        }
        default:return 2;
        }
        output[size_at]=static_cast<std::uint32_t>(output.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(const auto w:output){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
