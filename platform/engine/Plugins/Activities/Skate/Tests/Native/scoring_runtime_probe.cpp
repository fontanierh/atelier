#include "ScoringRuntime.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace {
struct Input:detail::DataReader {
    explicit Input(const std::vector<std::uint8_t>& b):DataReader{b}{at=0;}
    ScoringFrame Frame() {
        ScoringFrame f;f.tick=Word();f.dt=Float();f.category=Word();f.state=Word();
        const bool present=Word()!=0;AttributeName name;for(auto& x:name)x=Word();if(present)f.descriptor=name;
        f.grind_id=std::int32_t(Word());f.flags=Word();
        for(auto* v:{&f.position,&f.velocity,&f.forward})for(auto& x:*v)x=Float();
        f.switch_stance=Word()!=0;f.fakie=Word()!=0;f.nollie=Word()!=0;f.body_flip=Word()!=0;
        f.suspend_air=Word()!=0;f.teleported=Word()!=0;f.reverting=Word()!=0;
        f.landing_data_167=Word()!=0;f.landing_type_96=Word();f.sideways_speed_84=Float();f.spin_92=Float();return f;
    }
};
struct Output {
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w){words.push_back(w);}
    void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void String(std::string_view s){Word(std::uint32_t(s.size()));for(auto c:s)Word(std::uint8_t(c));}
    void Status(bool okay,std::string_view error){Word(okay);if(!okay)String(error);}
    template<class T,std::size_t N> void Floats(const std::array<T,N>& a){for(auto x:a)Float(x);}
    void Carrier(const ScoringCarrier& c) {
        Word(std::uint32_t(c.scorable.id));Word(c.scorable.category);Word(std::uint32_t(c.scorable.score_type));
        Word(std::uint32_t(c.points));Float(c.factor);Float(c.reward);Float(c.announcement_threshold);
        Word(c.start_tick);Word(c.delay_ticks);Word(c.announced);Word(c.completed);Word(c.unannounced);Word(c.switch_stance);Word(c.fakie);
    }
    void State(const ScoringRuntime& owner) {
        const auto start=words.size();Word(0);const auto& s=owner.State();Word(std::uint32_t(s.collector));
        for(const auto& c:s.carriers){Word(bool(c));if(c)Carrier(*c);}
        Floats(s.held);Floats(s.distance);Floats(s.metric_rewards);for(auto v:s.metric_started)Word(v);
        Floats(s.start);Floats(s.previous);
        for(auto v:{s.previous_heading,s.spin,s.peak,s.air_factor,s.air_repetition})Float(v);
        Word(s.air_repetition_set);Word(s.grab_chain);Floats(s.air_metrics);
        Word(s.landing_countdown);Word(s.idle_ticks);Word(s.collector_ticks);Word(s.manual_revert_ticks);
        Word(bool(s.revert_id));if(s.revert_id)Word(std::uint32_t(*s.revert_id));
        Word(s.sequence_active);Float(s.sequence_score);String(s.trick_name);for(auto v:s.stance)Word(v);
        for(auto v:{s.clean,s.sketchy,s.new_trick,s.modified_trick,s.close_tricks})Word(v);
        const auto& h=owner.session.holder.State();const auto& p=h.snapshot;
        for(auto v:{p.completed_lines,p.line,p.accumulated,p.last_reward,p.general_pending,p.fingerflip_pending,p.grind_reward})Float(v);
        for(const auto* a:{&h.repetitions,&h.sequence_history})for(auto x:*a)Word(std::uint32_t(std::int32_t(x)));
        for(auto x:h.type_history)Word(std::uint32_t(std::int32_t(x)));Word(h.pending_sequence);Word(h.suppressed);
        Float(owner.session.combo.timer.points);Word(owner.session.combo.timer.expired);Float(owner.session.combo.multiplier);
        Float(owner.session.line.points);Word(owner.session.line.expired);
        words[start]=std::uint32_t(words.size()-start-1);
    }
};
std::vector<std::uint8_t> File(const char* path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
}
int main(int argc,char** argv) {
    if(argc!=2)return 2;SettingsDatabase settings;std::string error;
    if(!settings.Load(File(argv[1]),error)){std::cerr<<error;return 2;}
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(bytes);Output o;
    const auto cases=i.Word();o.Word(cases);
    for(std::uint32_t c=0;c<cases;++c){ScoringRuntime r;if(!r.Load(settings,error)){std::cerr<<error;return 2;}
        const auto count=i.Word();o.Word(count);o.State(r);
        for(std::uint32_t n=0;n<count;++n){const auto op=i.Word();o.Word(op);bool okay=true;error.clear();
            if(op==0)okay=r.Advance(i.Frame(),error);
            else if(op==1)okay=r.Load(settings,error);
            else if(op==2)r.session.holder.SetSuppressed(i.Word()!=0);
            else return 2;o.Status(okay,error);o.State(r);
        }
    }
    if(!i.ok||i.Remaining())return 2;for(auto w:o.words)for(unsigned b=0;b<4;++b)std::cout.put(char(w>>(8*b)));return std::cout?0:2;
}
