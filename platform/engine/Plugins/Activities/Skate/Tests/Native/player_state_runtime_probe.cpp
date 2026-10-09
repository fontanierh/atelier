#include "PlayerStateRuntime.h"
#include "DataReader.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
// GENERATED_VERIFIED_FILTERED_WIRE
// GENERATED_DECLARATION_PROTOCOL

void Snapshot(Output& o,const PlayerStateRuntime& s)
{
    const auto active=s.lifecycle.Active();o.Word(std::uint32_t(s.Current()));
    o.Word(std::uint32_t(active.state));o.Word(active.owner_offset);
    o.Word(std::uint32_t(s.requested_state));Observe(o,s.selector);
    o.State(s.conditioning.filtered);o.Filtered(s.conditioning.filtered_output);
    o.Word(bool(s.ground_output));if(s.ground_output)Observe(o,*s.ground_output);
    for(auto w:s.post.jump_reference)o.Word(w);
    o.Word(s.post.jump_fix_frames);o.Word(s.post.latch_frames);o.Word(s.post.state_frames);
    o.Float(s.post.heading_adjust);o.Word(s.post.complete);o.Word(s.post.trajectory_pending);
    o.Word(s.post.trajectory_valid);o.Word(s.post.trajectory_available);o.Word(s.post.trajectory_new_candidate);
    for(auto v:s.state_flags){o.Word(v);}o.Word(s.state_count);o.Word(s.update_count);
    Observe(o,s.normal_off_ground);Observe(o,s.skitching_off_ground);
    o.Float(s.animated_board_threshold);o.Word(s.initialized);
    for(auto id:PhysicalStates){const auto c=s.registry.Capability(id);o.Word(std::uint32_t(c.id));o.Word(c.supported);o.Word(c.has_enter);o.Word(c.has_exit);}
}

void Seed(Input& i,PlayerStateRuntime& s)
{
    s.lifecycle=PhysicalPlayerStateLifecycle(PhysicalStateId(i.Word()));
    s.requested_state=PhysicalStateId(i.Word());s.selector=ReadStateSelector(i);
    const auto head=i.Words<9>();const auto grind=i.Grind();auto& f=s.conditioning.filtered;
    // Identical accepted core-fixture cache initialization, not a host Grind producer.
    f.Update({400,400,false,0,false,false,false,false,grind,0});
    f.category=FilteredCategory(head[0]);f.previous_category=FilteredCategory(head[1]);
    f.previous_physics_state=std::int32_t(head[2]);f.air_count=std::int32_t(head[3]);
    f.nonspecific_count=std::int32_t(head[4]);f.nonspecific_collision_free_count=std::int32_t(head[5]);
    f.nonspecific_collision_count=std::int32_t(head[6]);f.frames_since_ground_stairs=std::int32_t(head[7]);f.must_change=head[8]!=0;
    s.conditioning.filtered_output=i.Word()?std::optional<FilteredStateOutput>(ReadFilteredStateOutput(i)):std::nullopt;
    s.ground_output=i.Word()?std::optional<PhysicsGroundOutput>(ReadPhysicsGroundOutput(i)):std::nullopt;
    s.post.jump_reference=i.Words<4>();s.post.jump_fix_frames=i.Word();s.post.latch_frames=i.Word();s.post.state_frames=i.Word();
    s.post.heading_adjust=i.Float();s.post.complete=i.Word()!=0;s.post.trajectory_pending=i.Word()!=0;
    s.post.trajectory_valid=i.Word()!=0;s.post.trajectory_available=i.Word()!=0;s.post.trajectory_new_candidate=i.Word()!=0;
    for(auto& v:s.state_flags){v=i.Word()!=0;}s.state_count=i.Word();s.update_count=i.Word();
    s.normal_off_ground=ReadTwoStageThresholds(i);s.skitching_off_ground=ReadTwoStageThresholds(i);
    s.animated_board_threshold=i.Float();s.initialized=i.Word()!=0;
}

int main(int argc,char** argv)
{
    if(argc!=3)return 2;
    const auto database=[](const char* path,SettingsDatabase& d){std::ifstream f(path,std::ios::binary);const std::vector<std::uint8_t> b{std::istreambuf_iterator<char>(f),{}};std::string e;return d.Load(b,e);};
    SettingsDatabase stock,fixture;if(!database(argv[1],stock)||!database(argv[2],fixture))return 2;
    const std::vector<std::uint8_t> input{std::istreambuf_iterator<char>(std::cin),{}};
    Input i(input);Output out;const auto count=i.Word();out.Word(count);
    for(std::uint32_t c=0;c<count;++c)
    {
        std::string error;auto owner=PlayerStateRuntime::Load(stock,"initial",error);if(!owner)return 2;
        // Separate native-only invariant: no separate original landing stage is run.
        owner->conditioning.landing_settings.twist_spin.x={.137f,.317f,.517f,.731f};
        owner->conditioning.landing_settings.twist_spin.y={-.137f,-.317f,-.517f,-.731f};
        owner->conditioning.landing_settings.side_speed=owner->conditioning.landing_settings.twist_spin;
        owner->conditioning.landing_quality={.137f,-.317f,.731f,-.517f,0xdeadbeef,true};
        const auto landing_words=[&](){Output l;l.Settings(owner->conditioning.landing_settings);l.Landing(owner->conditioning.landing_quality);return l.bytes;};
        out.Word(c);Snapshot(out,*owner);const auto commands=i.Word();out.Word(commands);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=i.Word();error="old diagnostic";bool loaded=true;
            if(op==0||op==4)
            {
                const auto prior=landing_words();const auto mode=i.String();auto replacement=PlayerStateRuntime::Load(op==0?stock:fixture,mode,error);
                loaded=bool(replacement);if(replacement)owner=std::move(replacement);
                if(!loaded&&landing_words()!=prior)return 3;
            }
            else if(op==1)Seed(i,*owner);
            else if(op==2){const auto prior=landing_words();owner->ResetForTeleport();if(landing_words()!=prior)return 3;}
            else if(op==3){(void)owner->Current();}
            else return 2;
            if(op!=0&&op!=4)error.clear();
            out.Word(c);out.Word(n);out.Word(op);out.Word(loaded);out.String(error);Snapshot(out,*owner);
        }
    }
    if(!i.r.ok||i.r.at!=input.size())return 2;
    std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));
}
