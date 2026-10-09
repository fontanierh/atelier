#include "FilteredState.h"
#include "LandingQuality.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <cstring>
using namespace atelier::skate;
struct Input
{
    detail::DataReader r;
    explicit Input(const std::vector<std::uint8_t>& b):r{b}{r.at=0;}
    std::uint32_t Word(){return r.Word();}float Float(){return r.Float();}
    Vec4 Vector(){Vec4 a;for(auto& x:a)x=Float();return a;}
    AttributeName Name(){AttributeName a;for(auto& x:a)x=Word();return a;}
    std::uint64_t Guid(){const auto low=Word();return std::uint64_t(low)|(std::uint64_t(Word())<<32);}
    FilteredGrindState Grind(){FilteredGrindState g;g.kind=std::int32_t(Word());g.scorable_id=std::int32_t(Word());g.name=Name();g.scoring_name=Name();g.on_front=Word()!=0;g.crouch=Float();g.pathed_guid=Guid();g.local_guid=Guid();return g;}
    LandingQualitySettings Settings(){LandingQualitySettings s;for(auto* g:{&s.twist_spin,&s.side_speed}){for(auto& x:g->x)x=Float();for(auto& y:g->y)y=Float();}return s;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t w){for(unsigned n=0;n<4;++n)bytes.push_back(std::uint8_t(w>>(n*8)));}
    void Float(float f){std::uint32_t b;std::memcpy(&b,&f,4);Word(b);}
    void String(std::string_view v){Word(std::uint32_t(v.size()));bytes.insert(bytes.end(),v.begin(),v.end());while(bytes.size()%4)bytes.push_back(0);}
    void Grind(const FilteredGrindState& g){Word(std::uint32_t(g.kind));Word(std::uint32_t(g.scorable_id));for(auto x:g.name)Word(x);for(auto x:g.scoring_name)Word(x);Word(g.on_front);Float(g.crouch);Word(std::uint32_t(g.pathed_guid));Word(std::uint32_t(g.pathed_guid>>32));Word(std::uint32_t(g.local_guid));Word(std::uint32_t(g.local_guid>>32));}
    void Settings(const LandingQualitySettings& s){for(const auto* g:{&s.twist_spin,&s.side_speed}){for(auto x:g->x)Float(x);for(auto y:g->y)Float(y);}}
    void Landing(const LandingQualityOutput& l){Float(l.landing_adjust_80);Float(l.sideways_speed_84);Float(l.forward_speed_88);Float(l.spin_92);Word(l.landing_type_96);Word(l.landing_data_167);}
    void State(const FilteredState& s){Word(std::uint32_t(s.category));Word(std::uint32_t(s.previous_category));Word(std::uint32_t(s.previous_physics_state));Word(std::uint32_t(s.air_count));Word(std::uint32_t(s.nonspecific_count));Word(std::uint32_t(s.nonspecific_collision_free_count));Word(std::uint32_t(s.nonspecific_collision_count));Word(std::uint32_t(s.frames_since_ground_stairs));Word(s.must_change);Grind(s.CachedGrind());}
    void Filtered(const std::optional<FilteredStateOutput>& s){Word(bool(s));if(s){Word(std::uint32_t(s->category));Word(std::uint32_t(s->previous_category));Word(s->grinding);Grind(s->grind);Float(s->last_grind_distance);}}
};
int main(int argc,char** argv)
{
    if(argc!=2)return 2;
    std::ifstream f(argv[1],std::ios::binary);const std::vector<std::uint8_t> settings_bytes{std::istreambuf_iterator<char>(f),{}};
    SettingsDatabase database;std::string error;if(!database.Load(settings_bytes,error))return 2;
    LandingQualitySettings settings;for(auto* g:{&settings.twist_spin,&settings.side_speed}){g->x={-.731f,-.317f,.137f,.731f};g->y={.517f,.113f,-.137f,.317f};}
    Output out;const bool loaded=settings.Load(database,error);out.Word(loaded);out.String(error);out.Settings(settings);
    const std::vector<std::uint8_t> input_bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(input_bytes);const auto programs=i.Word();out.Word(programs);
    for(std::uint32_t p=0;p<programs;++p)
    {
        FilteredState state;std::optional<FilteredStateOutput> filtered;LandingQualityOutput landing;auto current_settings=settings;const auto count=i.Word();
        for(std::uint32_t n=0;n<count;++n)
        {
            const auto op=i.Word();
            if(op==0){state.Reset();filtered.reset();}
            else if(op==1)
            {
                const auto cat=FilteredCategory(i.Word()),prev=FilteredCategory(i.Word());const auto prior=std::int32_t(i.Word()),air=std::int32_t(i.Word()),non=std::int32_t(i.Word()),free=std::int32_t(i.Word()),contact=std::int32_t(i.Word()),stairs=std::int32_t(i.Word());const bool must=i.Word()!=0;const auto grind=i.Grind();
                state.Update({400,400,false,0,false,false,false,false,grind,0});state.category=cat;state.previous_category=prev;state.previous_physics_state=prior;state.air_count=air;state.nonspecific_count=non;state.nonspecific_collision_free_count=free;state.nonspecific_collision_count=contact;state.frames_since_ground_stairs=stairs;state.must_change=must;
            }
            else if(op==2)
            {
                FilteredStateInput v;v.physics_category=std::int32_t(i.Word());v.physics_state=std::int32_t(i.Word());v.anything_in_contact=i.Word()!=0;v.physics_surface_type=std::int32_t(i.Word());v.wall_ride_exit=i.Word()!=0;v.targeting_grind=i.Word()!=0;v.offboard_has_landed=i.Word()!=0;v.offboard_on_deck=i.Word()!=0;v.grind=i.Grind();v.last_grind_distance=i.Float();filtered=state.Update(v);
            }
            else if(op==3){landing={i.Float(),i.Float(),i.Float(),i.Float(),i.Word(),i.Word()!=0};}
            else if(op==4)
            {
                LandingQualityInput v;v.previous_filtered_state=i.Word();v.filtered_state=i.Word();v.ground_normal=i.Vector();v.deck_velocity=i.Vector();v.flipped=i.Word()!=0;v.reckoning_forward=i.Vector();v.air_spin=i.Float();landing.Update(v,current_settings);
            }
            else if(op==5)current_settings=i.Settings();
            else if(op==6)landing={};else return 2;
            out.Word(p);out.Word(n);out.Word(op);out.State(state);out.Filtered(filtered);out.Landing(landing);out.Settings(current_settings);
        }
    }
    if(!i.r.ok||i.r.at!=input_bytes.size())return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));
}
