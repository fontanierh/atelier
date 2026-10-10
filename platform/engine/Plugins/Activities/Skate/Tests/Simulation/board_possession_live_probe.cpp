// The checker prefixes the shared exact possession transport helpers.
#include "BoardPossessionSettings.h"
#include <fstream>
#include <iterator>
namespace
{
Vec3 V3(){return {Float(),Float(),Float()};}
Basis3 B3(){Basis3 b;for(auto& c:b.columns)for(auto& x:c)x=Float();return b;}
AffineTransform Aff(){const auto b=B3();return {b,V3()};}
SimulationStep Sim(){const auto dt=Float(),hz=Float();const auto cool=Word();const auto energy=Float();return {dt,hz,cool,energy,V3()};}
ContactMaterial Material(){return {Float(),Float(),Float()};}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(Basis3 b){for(auto c:b.columns)for(auto x:c)Out(x);}
void Out(AffineTransform t){Out(t.basis);Out(t.translation);}
void Out(ContactMaterial m){Out(m.static_friction);Out(m.dynamic_friction);Out(m.restitution);}
void Out(const BodySnapshot& b)
{
    const auto& r=b.rates;const auto& d=b.inertia;Out(b.state_flags);Out(r.orientation);Out(r.basis);Out(r.world_inverse_inertia);Out(r.position);Out(r.linear_velocity);Out(r.angular_velocity);Out(r.force_acceleration);Out(r.torque_acceleration);Out(r.kinetic_energy);Out(r.cool_down);
    Out(d.inverse_tensor);for(float x:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag})Out(x);
}
BodySnapshot ReadBody()
{
    BodySnapshot b;b.state_flags=Word();auto& r=b.rates;for(auto& x:r.orientation)x=Float();r.basis=B3();r.world_inverse_inertia=B3();r.position=V3();r.linear_velocity=V3();r.angular_velocity=V3();r.force_acceleration=V3();r.torque_acceleration=V3();r.kinetic_energy=Float();r.cool_down=Word();auto& d=b.inertia;d.inverse_tensor=V3();d.inverse_mass=Float();d.spherical=Float();d.maximum_linear_velocity=Float();d.maximum_angular_velocity=Float();d.linear_drag=Float();d.angular_drag=Float();return b;
}
void Out(BoardPossessionObservation o)
{
    const auto& p=o.processed;Out(p.board_frame_64);Out(p.player_frame_192);Out(p.position_592);Out(p.velocity_912);Out(p.direction_400);Out(p.hide_direction_464);Out(p.flags_2476);Out(p.flags_2480);Out(p.flags_2488);Out(o.board_collision_flags_872);Out(o.board_state_840);for(bool b:o.hand_contacts)Out(std::uint32_t(b));Out(o.physical_hand_positions);Out(o.animation_board_frame_12624);Out(o.animation_hand_frames);Out(o.attachment_frame_0);
}
void Out(const BoardPossessionSettings& s)
{
    for(float x:{s.hide_distance,s.hide_offset,s.return_distance,s.mounted_return_distance,s.mounting_time})Out(x);Out(s.retrieval_time.x);Out(s.retrieval_time.y);Out(s.retrieval_weight.x);Out(s.retrieval_weight.y);Out(s.throw_pitch);Out(s.throw_velocity.x);Out(s.throw_velocity.y);for(float x:{s.throw_target_pitch,s.throw_pitch_scalar,s.throw_roll_scalar,s.throw_yaw_scalar})Out(x);
}
void OutError(const std::string& error){Out(static_cast<std::uint32_t>(error.size()));for(unsigned char c:error)Out(std::uint32_t(c));}
struct ObserveTransport
{
    BoardPossessionProcessed processed{};
    std::optional<Mat4> toolkit;
    BoardGroundState ground;
    WheelLineState lines;
    SkeletonPhysicalRecord record;
    SkeletonCollisionFeedback feedback;
    std::array<Mat4,24> frames;
    Mat4 root=SkeletonIdentity;
    ObserveTransport():feedback(SkeletonFeedbackSettings{}){frames.fill(SkeletonIdentity);}
    void Read()
    {
        const auto o=Observation();processed=o.processed;ground.collision_flags=o.board_collision_flags_872;record.pose[3][3]=o.physical_hand_positions[0];record.pose[7][3]=o.physical_hand_positions[1];feedback.bones[3].groups[3]=o.hand_contacts[0];feedback.bones[7].groups[3]=o.hand_contacts[1];frames[0]=o.animation_board_frame_12624;frames[3]=o.animation_hand_frames[0];frames[7]=o.animation_hand_frames[1];root=Matrix();frames[11]=Matrix();toolkit=Word()?std::optional<Mat4>(Matrix()):std::nullopt;
        for(auto& surface:lines.physics_surfaces)surface=Word();for(auto& part:ground.parts){part.in_contact=Word()!=0;part.normal=V3();}
    }
    BoardPossessionObserveInput Input() const{return {processed,toolkit,ground,lines,record,feedback,frames,root};}
};
void Out(const BoardPossessionLiveState& live)
{
    Out(std::uint32_t(live.volumes.deck));Out(std::uint32_t(live.volumes.trucks));Out(std::uint32_t(live.volumes.wheels));Out(static_cast<std::uint32_t>(live.volumes.deck_children.size()));for(bool b:live.volumes.deck_children)Out(std::uint32_t(b));Out(live.alignment.first_1008);Out(live.alignment.second_1024);Out(live.alignment.factor_1040);Out(std::uint32_t(live.alignment.flag_1044));Out(std::uint32_t(live.alignment_active));for(auto m:live.standard_materials)Out(m);Out(live.released_material);Out(live.standard_drag);Out(std::uint32_t(live.output.has_value()));if(live.output)Out(*live.output);
}
void Snapshot(const BoardPossessionOwner& owner,const BoardPossessionLiveState& live,const BoardRuntime& board,const BoardCollisionSettings& collision,
    const std::array<BodySnapshot,26>& skeleton,const SkateboardControllerFields& fields,std::uint8_t animated,bool wiping,const ObserveTransport& observation,BoardPossessionFill physical)
{
    Out(fields);Out(owner.state);Out(std::uint32_t(animated));Out(std::uint32_t(wiping));for(const auto& b:board.Bodies())Out(b);Out(board.Hook().body);Out(board.Hook().drive.frames);Out(board.Hook().drive.dynamics);for(auto t:board.PartTransforms())Out(t);Out(board.HookTransform());Out(board.CollisionGroup());
    Out(collision.wheel_material);Out(collision.truck_material);Out(collision.deck_material);Out(std::uint32_t(collision.truck_collisions));Out(static_cast<std::uint32_t>(collision.deck_geometry.children.size()));for(const auto& c:collision.deck_geometry.children)Out(std::uint32_t(c.collision_enabled));Out(live);Out(physical);Out(observation.ground.collision_flags);Out(ObserveBoardPossession(board,observation.Input()));for(const auto& b:skeleton)Out(b);
}
void Effect(LiveBoardPossessionEffects& e,std::uint32_t op)
{
    switch(op){case 0:e.EnableAnimationSoft();break;case 1:e.EnableAnimationAngularOnly();break;case 2:e.DisableAnimation();break;case 3:e.DisableLinearDrive();break;case 4:e.StandardBoard();break;case 5:e.ReleasedBoard();break;case 6:e.CollisionVolumes(Word()!=0);break;case 7:e.ClearAlignment();break;case 8:{const auto a=Vector(),b=Vector();const float factor=Float();e.Alignment({a,b,factor,Word()!=0});break;}case 9:e.Velocity(Vector());break;case 10:e.Position(Vector());break;case 11:e.HookFrame(Matrix());break;case 12:e.TargetPositionVelocity(Vector());break;case 13:e.Torque(Vector());break;default:std::exit(2);}
}
}
int main(int argc,char** argv)
{
    if(argc!=2)return 2;std::ifstream input(argv[1],std::ios::binary);std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(input)),{});SettingsDatabase database;std::string error;if(!database.Load(bytes,error))return 2;
    const auto count=Word();for(std::uint32_t index=0;index<count;++index)
    {
        const auto operation=Word();Out(index);Out(operation);const auto mark=out.size();Out(0u);const auto start=out.size();
        if(operation==1)
        {
            const auto settings=LoadBoardPossessionSettings(database,error);Out(std::uint32_t(settings.has_value()));if(settings)Out(*settings);else OutError(error);
            const auto drag=BoardPossessionStandardAngularDrag(database,error);Out(std::uint32_t(drag.has_value()));if(drag)Out(*drag);else OutError(error);
            BoardPhysicsSettings physics;const auto live=LoadBoardPossessionLiveState(database,physics,error);Out(std::uint32_t(live.has_value()));if(live)Out(*live);else OutError(error);
        }
        else if(operation==0)
        {
            const auto spawn=Aff();const auto simulation=Sim();auto masses=DefaultSkateboardMassProperties();if(Word())for(auto& mass:masses){const auto frame=Aff();mass.local_mass_frame={frame.basis,frame.translation};}
            const auto authored=AuthoredBodyTransforms(AuthoredTransformInputs::Stock());BoardRuntime board(masses,authored,spawn,simulation,BoardMotion::Active);BoardPhysicsSettings physics;
            physics.standard_wheel_material=Material();physics.collision.truck_material=Material();physics.collision.deck_material=Material();physics.collision.wheel_material=Material();physics.collision.truck_collisions=Word()!=0;const auto child_count=Word();physics.collision.deck_geometry.children.resize(child_count);for(auto& child:physics.collision.deck_geometry.children)child.collision_enabled=Word()!=0;
            const auto settings=LoadBoardPossessionSettings(database,error);if(!settings)return 2;BoardPossessionOwner owner(*settings);auto live=LoadBoardPossessionLiveState(database,physics,error);if(!live)return 2;
            auto fields=Fields();if(Word())owner.state=State();const float dt=Float();std::uint8_t animated=static_cast<std::uint8_t>(Word());bool wiping=Word()!=0;ObserveTransport observation;observation.Read();std::array<BodySnapshot,26> skeleton;skeleton.fill(board.Bodies()[6]);BoardPossessionFill physical{};
            const auto commands=Word();Out(commands);Snapshot(owner,*live,board,physics.collision,skeleton,fields,animated,wiping,observation,physical);
            for(std::uint32_t n=0;n<commands;++n)
            {
                const auto op=Word();Out(op);const auto command_mark=out.size();Out(0u);const auto command_start=out.size();LiveBoardPossessionEffects effects(board,animated,wiping,*live,physics.collision,dt);
                switch(op)
                {
                case 0:observation.Read();break;case 1:fields=Fields();break;case 2:UpdateBoardPossession(owner,*live,board,physics.collision,wiping,animated,fields,observation.Input(),dt);break;
                case 3:owner.Hold(fields,ObserveBoardPossession(board,observation.Input()),effects);break;case 4:owner.LetGo(fields,ObserveBoardPossession(board,observation.Input()),effects);break;case 5:owner.Stop(fields,ObserveBoardPossession(board,observation.Input()),effects);break;
                case 6:ResetBoardPossessionForTeleport(owner,*live,board,physics.collision,wiping,animated,fields,observation.Input(),dt);break;case 7:FinishBoardPossessionTeleport(*live,board,physics.collision,wiping,animated,dt);break;
                case 8:physical=PublishBoardPossession(owner,*live,board,observation.ground,fields,observation.Input());Out(physical);break;
                case 9:{const float timestep=Float();const auto deck_reaction=Word(),first=Word(),second=Word();std::vector<DriveRows> rows;owner.AppendDrives(board.Bodies()[6],{skeleton[3],skeleton[7]},deck_reaction,{first,second},timestep,rows);Out(static_cast<std::uint32_t>(rows.size()));for(const auto& row:rows){const auto packed=PackDrive(row);Out(packed.words);Out(static_cast<std::uint32_t>(packed.reaction_a));Out(static_cast<std::uint32_t>(packed.reaction_b));}break;}
                case 10:live->PublishVolumes(physics.collision);break;
                case 11:{const auto id=Word();const auto b=ReadBody();if(id<7)board.BodiesMut()[id]=b;else if(id==7)board.HookMut().body=b;else skeleton.at(id-8)=b;break;}
                case 12:{const auto o=ObserveBoardPossession(board,observation.Input());BoardPossessionTransition transition(owner,o,effects,fields);const auto count=Word();for(std::uint32_t i=0;i<count;++i){if(Word())transition.LetGo();else transition.Hold();}fields=Fields();transition.Finish(fields);break;}
                case 13:owner.state=State();break;
                case 14:{live->volumes.deck=Word()!=0;live->volumes.trucks=Word()!=0;live->volumes.wheels=Word()!=0;const auto n=Word();live->volumes.deck_children.resize(n);for(std::uint32_t i=0;i<n;++i)live->volumes.deck_children[i]=Word()!=0;live->alignment.first_1008=Vector();live->alignment.second_1024=Vector();live->alignment.factor_1040=Float();live->alignment.flag_1044=Word()!=0;live->alignment_active=Word()!=0;break;}
                case 15:Out(ObserveBoardPossession(board,observation.Input()));break;
                case 17:{const auto n=Word();physics.collision.deck_geometry.children.resize(n);for(auto& c:physics.collision.deck_geometry.children)c.collision_enabled=Word()!=0;break;}
                case 18:{const auto hand=Word();if(hand>=2)return 2;for(auto& d:owner.state.hands[hand].dynamics)for(auto& w:d)w=Word();break;}
                case 19:Effect(effects,Word());break;
                case 20:Out(std::uint32_t(live->VolumeEnabled(CollisionBody::FromContactId(Word()))));break;
                default:return 2;
                }
                Snapshot(owner,*live,board,physics.collision,skeleton,fields,animated,wiping,observation,physical);out[command_mark]=static_cast<std::uint32_t>(out.size()-command_start);
            }
        }else return 2;
        out[mark]=static_cast<std::uint32_t>(out.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:out){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
