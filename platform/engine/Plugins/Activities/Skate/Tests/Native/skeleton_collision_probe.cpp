// SPDX-License-Identifier: Apache-2.0
// The checker prepends the skeleton-body probe's public record adapters.
#include "BoardGroundAngle.h"
#include "SkeletonPoseErrors.h"
namespace
{
ContactMaterial Material(){return {Float(),Float(),Float()};}
SkeletonCollisionSettings CollisionSettings()
{
    SkeletonCollisionSettings s;s.enabled=Word()!=0;s.normal_material=Material();for(auto& c:s.compliant)c=Word()!=0;s.priority=Floats<24>();s.effect_time=Float();return s;
}
SkeletonFeedbackSettings FeedbackSettings()
{const auto body=CollisionSettings();return {body,Float(),Float(),Float(),Float(),Float(),Floats<4>(),Floats<4>(),Float(),Float()};}
void OutSettings(SkeletonCollisionSettings s){Out(std::uint32_t(s.enabled));Out(s.normal_material.static_friction);Out(s.normal_material.dynamic_friction);Out(s.normal_material.restitution);for(bool c:s.compliant)Out(std::uint32_t(c));Out(s.priority);Out(s.effect_time);}
void OutFlags(SkeletonContactFlags a)
{for(bool c:{a.material_6,a.noncompliant,a.compliant,a.recovering,a.group_8,a.nonboard,a.ragdoll,a.conflicting,a.impaled,a.has_impulse,a.foot_board,a.material_10,a.material_11,a.material_12,a.any})Out(std::uint32_t(c));}
void ReadFlags(SkeletonContactFlags& a)
{for(bool* c:{&a.material_6,&a.noncompliant,&a.compliant,&a.recovering,&a.group_8,&a.nonboard,&a.ragdoll,&a.conflicting,&a.impaled,&a.has_impulse,&a.foot_board,&a.material_10,&a.material_11,&a.material_12,&a.any})*c=Word()!=0;}
SkeletonSpecificContact Specific(){return {Word(),Floats<4>(),Floats<4>(),Float(),Word()!=0,Word()!=0};}
void OutFeedback(const SkeletonCollisionFeedback& a)
{
    Out(a.contact_age);Out(a.priority);for(bool v:a.compliant)Out(std::uint32_t(v));for(bool v:a.current)Out(std::uint32_t(v));
    for(const auto& b:a.bones){Out(b.normal);Out(b.specific_normal);Out(b.tangent);Out(b.specific_tangent);Out(b.point);Out(b.force);Out(b.specific_force);Out(b.tag);Out(b.specific_tag);for(bool v:b.groups)Out(std::uint32_t(v));}
    for(const auto& r:a.regions){Out(r.force);Out(r.weighted_force);Out(r.tangent_speed);Out(r.material_flags);Out(r.normal);Out(r.part ? static_cast<std::uint32_t>(*r.part):0xffffffffu);}
    Out(static_cast<std::uint32_t>(a.planes.size()));for(const auto& p:a.planes){Out(p.normal);Out(static_cast<std::uint32_t>(p.part));}
    for(const auto& p:a.specific){Out(static_cast<std::uint32_t>(p.part));Out(p.local_point);Out(p.world_point);Out(p.radius_squared);Out(std::uint32_t(p.current));Out(std::uint32_t(p.recent));}
    Out(a.highest_normal);Out(a.foot_normal);Out(a.material_normals);Out(a.timer);Out(a.drive_weight);Out(a.maximum_priority);Out(a.wipeout_times);Out(a.maximum_skater_force);Out(static_cast<std::uint32_t>(a.other_skater));Out(a.maximum_group_8_force);Out(a.maximum_group_11_force);Out(a.material_12_height);OutFlags(a.flags);
}
void SeedFeedback(SkeletonCollisionFeedback& a)
{
    if(!Word())return;
    a.contact_age=Floats<24>();a.priority=Floats<24>();for(auto& v:a.compliant)v=Word()!=0;for(auto& v:a.current)v=Word()!=0;
    for(auto& b:a.bones){b.normal=Floats<4>();b.specific_normal=Floats<4>();b.tangent=Floats<4>();b.specific_tangent=Floats<4>();b.point=Floats<4>();b.force=Float();b.specific_force=Float();b.tag=Word();b.specific_tag=Word();for(auto& v:b.groups)v=Word()!=0;}
    for(auto& r:a.regions){r.force=Float();r.weighted_force=Float();r.tangent_speed=Float();r.material_flags=Word();r.normal=Floats<4>();const auto p=Word();if(p!=0xffffffffu)r.part=p;}
    a.planes.clear();const auto count=Word();for(std::uint32_t n=0;n<count;++n){const auto normal=Floats<4>();a.planes.push_back({normal,Word()});}
    for(auto& p:a.specific)p=Specific();a.highest_normal=Floats<4>();a.foot_normal=Floats<4>();for(auto& v:a.material_normals)v=Floats<4>();
    a.timer=Float();a.drive_weight=Float();a.maximum_priority=Float();a.wipeout_times=Floats<3>();a.maximum_skater_force=Float();a.other_skater=static_cast<std::int32_t>(Word());a.maximum_group_8_force=Float();a.maximum_group_11_force=Float();a.material_12_height=Float();ReadFlags(a.flags);
}
SkeletonContactBody ContactBody(){return {Word(),Float(),Floats<4>()};}
SkeletonContactReport Report()
{
    SkeletonContactReport r;r.part=Word();r.normal=Floats<4>();r.point=Floats<4>();r.tag=Word();r.other_group=Word();const bool entity=Word()!=0;const auto id=Word();if(entity)r.other_entity=static_cast<std::int32_t>(id);r.body_a=ContactBody();r.body_b=ContactBody();r.side_a=Word()!=0;r.solved_vector=Floats<4>();return r;
}
void UpdateFeedback(SkeletonCollisionFeedback& a)
{
    const float dt=Float();const auto point=Floats<4>(),normal=Floats<4>(),reference=Floats<4>(),com=Floats<4>();
    const bool ragdoll=Word()!=0,disable=Word()!=0,ai=Word()!=0,offboard=Word()!=0,entering=Word()!=0,category=Word()!=0,partial=Word()!=0;
    const auto physical=PhysicalRecord();const auto weights=Floats<24>();const auto frames=Matrices<26>();const auto count=Word();std::vector<SkeletonContactReport> reports;for(std::uint32_t n=0;n<count;++n)reports.push_back(Report());
    const SkeletonCollisionInput input{dt,point,normal,reference,com,ragdoll,disable,ai,offboard,entering,category,partial,physical,weights,frames};a.Update(input,reports);
}
SkeletonPoseErrors PoseErrors()
{SkeletonPoseErrors e;for(auto& p:e.parts)p=Floats<4>();for(auto& p:e.extra)p=Floats<4>();for(auto& p:e.targets)p=Floats<4>();return e;}
void OutErrors(SkeletonPoseErrors e){Out(e.parts);Out(e.extra);Out(e.targets);}
void OutResponse(SkeletonNormalError e){Out(e.impulse);Out(e.extra);Out(e.maximum_error);}
void OutMode(const SkeletonCollisionMode& m)
{
    for(const auto& p:m.parts){Out(std::uint32_t(p.enabled));Out(p.volume_group);Out(p.part_group);Out(p.material.static_friction);Out(p.material.dynamic_friction);Out(p.material.restitution);}
    Out(m.disable_count);Out(std::uint32_t(m.pending_reenable));Out(m.assembly_group);Out(std::uint32_t(m.partial_ragdoll));Out(std::uint32_t(m.is_ragdoll));for(const auto& row:m.self_culling)for(bool c:row)Out(std::uint32_t(c));OutSettings(m.settings);
}
void OutPolicy(const SkeletonBody& body,const SkeletonCollisionMode& mode,const SkeletonCollisionFeedback& feedback){Out(body);OutMode(mode);OutFeedback(feedback);}
}
int main()
{
    const auto cases=Word();for(std::uint32_t index=0;index<cases;++index)
    {
        const auto op=Word();Out(index);Out(op);const auto size_at=output.size();Out(0u);const auto start=output.size();
        switch(op)
        {
        case 0:{const auto a=Vector(),b=Vector();Out(BoardGroundAngleBetween(a,b));break;}
        case 1:
        {
            SkeletonCollisionFeedback feedback(FeedbackSettings());SeedFeedback(feedback);auto errors=PoseErrors();const auto error=Floats<4>(),axis=Floats<4>();Out(feedback.FilterError(error,axis));OutResponse(errors.NormalResponse(feedback,axis));OutResponse(errors.PartialResponse());OutFeedback(feedback);break;
        }
        case 2:
        {
            SkeletonCollisionFeedback feedback(FeedbackSettings());SeedFeedback(feedback);auto errors=PoseErrors();OutFeedback(feedback);OutErrors(errors);const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n)
            {
                const auto cmd=Word();Out(cmd);
                switch(cmd)
                {
                case 0:feedback.Reset();break;
                case 1:feedback.SetUpNormal();break;
                case 2:UpdateFeedback(feedback);break;
                case 3:{const auto error=Floats<4>(),axis=Floats<4>();Out(feedback.FilterError(error,axis));break;}
                case 4:feedback.contact_age=Floats<24>();feedback.priority=Floats<24>();for(auto& v:feedback.compliant)v=Word()!=0;break;
                case 5:for(auto& point:feedback.specific)point=Specific();break;
                case 6:feedback.flags.any=Word()!=0;break;
                case 7:errors.ResetHistory();break;
                case 8:errors.SetTargets({Floats<4>(),Floats<4>(),Floats<4>()});break;
                case 9:{const auto physical=PhysicalRecord();const auto alignment=Matrix();errors.Update(physical,alignment,Matrices<24>());break;}
                case 10:{const auto axis=Floats<4>();OutResponse(errors.NormalResponse(feedback,axis));OutResponse(errors.PartialResponse());break;}
                default:return 2;
                }
                OutFeedback(feedback);OutErrors(errors);
            }
            break;
        }
        case 3:
        {
            std::string error;auto definition=Definition(error);if(!definition)return 4;const auto authored=Matrices<24>();const auto spawn=Matrix();const auto simulation=Simulation();SkeletonBody body(std::move(*definition),authored,spawn,simulation);
            const auto settings=CollisionSettings();const bool all=Word()!=0;SkeletonCollisionMode mode(settings,all);SkeletonCollisionFeedback feedback(FeedbackSettings());SeedFeedback(feedback);OutPolicy(body,mode,feedback);const auto count=Word();Out(count);
            for(std::uint32_t n=0;n<count;++n)
            {
                const auto cmd=Word();Out(cmd);
                switch(cmd)
                {
                case 0:mode.DisableHandplantContacts(Word());break;
                case 1:mode.FinishContactFrame();break;
                case 2:{const auto part=Word();mode.NormalBone(part,Word()!=0);break;}
                case 3:mode.EnableBone(Word());break;
                case 4:mode.NormalCollision();break;
                case 5:mode.DisableAll(Word()!=0);break;
                case 6:{const auto selected=Word();const bool ok=mode.SelectDriven(selected,error);Out(std::uint32_t(ok));if(!ok)Out(error);break;}
                case 7:{const bool mass=Word()!=0,inertia=Word()!=0;const auto drag=Floats<2>();const std::array<ContactMaterial,2> materials{{Material(),Material()}};mode.ApplyRagdollProperties(body,mass,inertia,drag,materials);break;}
                case 8:mode.FinishRagdollRequest(Word());break;
                case 9:mode.RestoreNormalProperties(body);break;
                case 10:mode.ResetBodyState(feedback);break;
                case 11:{const auto part=Word();mode.disable_count.at(part)=Word();mode.pending_reenable=Word()!=0;auto& p=mode.parts.at(part);p.enabled=Word()!=0;p.volume_group=Word();p.part_group=Word();p.material=Material();break;}
                case 12:mode.settings.enabled=Word()!=0;break;
                case 13:UpdateFeedback(feedback);break;
                case 14:{auto& b=body.BodiesMut().at(Word());b.state_flags=Word();b.rates.linear_velocity=Vector();b.rates.angular_velocity=Vector();b.rates.force_acceleration=Vector();b.rates.torque_acceleration=Vector();b.rates.kinetic_energy=Float();b.rates.cool_down=Word();break;}
                default:return 2;
                }
                OutPolicy(body,mode,feedback);
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
