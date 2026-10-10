// Inserted into the read-only copied Biped/Landing fixture before its main.
#include "PlayerStatePublication.h"
#include "PlayerGrindInput.h"
#include "PlayerGrindMaterials.h"
#include "SlidePhaseRuntime.h"
namespace common_publication
{
// GENERATED_GROUND_OBSERVERS
// GENERATED_GRIND_OBSERVERS
// GENERATED_WIPEOUT_OBSERVERS
void GrindFilteredOut(BipedOutput& o,const GrindFilteredOutput& g)
{
    o.Word(std::uint32_t(g.kind));o.Word(std::uint32_t(g.scorable_id));
    for(auto w:g.name)o.Word(w);for(auto w:g.scoring_name)o.Word(w);
    o.Word(g.on_front);o.Float(g.crouch);o.Wide(g.pathed_guid);o.Wide(g.local_guid);
}
void StateOut(BipedOutput& o,const PlayerStateRuntime& s)
{
    o.Word(std::uint32_t(s.Current()));o.Word(std::uint32_t(s.requested_state));
    o.Word(s.state_count);o.Word(s.update_count);for(bool b:s.state_flags)o.Word(b);
    const auto& c=s.conditioning;const auto& f=c.filtered;
    for(auto w:{std::uint32_t(f.category),std::uint32_t(f.previous_category),std::uint32_t(f.previous_physics_state),
        std::uint32_t(f.air_count),std::uint32_t(f.nonspecific_count),std::uint32_t(f.nonspecific_collision_free_count),
        std::uint32_t(f.nonspecific_collision_count),std::uint32_t(f.frames_since_ground_stairs),std::uint32_t(f.must_change)})o.Word(w);
    GrindFilteredOut(o,f.CachedGrind());o.Word(c.filtered_output.has_value());
    if(c.filtered_output){const auto& v=*c.filtered_output;o.Word(std::uint32_t(v.category));o.Word(std::uint32_t(v.previous_category));o.Word(v.grinding);GrindFilteredOut(o,v.grind);o.Float(v.last_grind_distance);}
    o.Word(s.ground_output.has_value());if(s.ground_output)GroundObserve(o,*s.ground_output);
    o.Floats(std::array<float,4>{c.landing_quality.landing_adjust_80,c.landing_quality.sideways_speed_84,c.landing_quality.forward_speed_88,c.landing_quality.spin_92});
    o.Word(c.landing_quality.landing_type_96);o.Word(c.landing_quality.landing_data_167);
}
void Snapshot(BipedOutput& o,PlayerStatePublicationOwners v)
{
    o.Word(5);Block(o,[&]{StateOut(o,v.shared.state);});
    Block(o,[&]{Observe(o,v.air_runtime.state);Observe(o,v.known_air.state);});
    Block(o,[&]{GrindOwnerOut(o,v.grind_runtime,v.shared.input.grind->jumper);});
    Block(o,[&]{ObserveWipeoutState(o,v.wipeout_runtime.state);ObserveWipeoutOutput(o,v.wipeout_runtime.Fill(v.wipeout));});
    Block(o,[&]{o.Word(v.slide.wall_riding);o.Word(v.revert.active);o.Word(v.ground_animation.launched);o.Floats(v.ground_animation.launch_velocity);
        const auto& t=v.teleport.State();o.Word(t.Ready());o.Word(t.Received());o.Word(t.OnBoard());for(const auto& row:t.Target())for(auto w:row)o.Word(w);});
}
bool GrindProducer(BipedInput& i,PlayerStatePublicationOwners v,const PlayerGrindMaterials& materials,std::string& error)
{
    const auto counter=std::int32_t(i.Word());const bool target=i.Word()!=0;
    auto& p=v.shared.physical;auto& input=v.shared.input;auto& x=input.processed;const auto& a=v.shared.animation_input.extra;
    PlayerGrindLiveHost live(p.board,p.settings.board,materials);std::optional<PlayerGrindPending> pending;
    const PlayerGrindPreContext pre{p.DeckFrame(),counter,x.state_2504,target,v.shared.animation_input.fields.balance,
        a.grind_translation,a.grind_stability_nudge,a.grind_up_down,a.grind_grab_min_height};
    if(!input.grind->PreUpdate(x,v.air.grind_world,p.world,pre,live,pending,error))return false;
    const PlayerGrindPostContext post{p.DeckFrame(),v.shared.animation_input.fields.balance,
        a.grind_translation,a.grind_stability_nudge,a.grind_up_down,a.grind_grab_min_height};
    std::optional<PlayerGrindPostResult> output;if(!input.grind->PostUpdate(x,p.world,std::move(*pending),post,live,output,error))return false;
    input.grind_observation=std::make_unique<PlayerGrindObservation>(output->observation);v.grind_runtime.Observe(output->observation);
    for(auto reason:output->wipeout_reasons)v.air.wipeout.state.Request(reason,0);return true;
}
}
