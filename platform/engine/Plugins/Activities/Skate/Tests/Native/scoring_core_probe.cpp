#include "ScoringSession.h"
#include "ScoringCarrier.h"
#include "DataReader.h"
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes}{at=0;}
    ScoringScorable Scorable(){const auto id=Word(),category=Word(),type=Word();return {id,category,type};}
    ScoringSessionRules Rules()
    {
        ScoringSessionRules r;r.combo_capacity=Float();
        for(auto& level:r.combo_levels){level.first=Float();level.second=Float();}
        r.combo_refresh_threshold=Float();r.line_capacity=Float();r.bail_factor=Float();return r;
    }
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w){words.push_back(w);}
    void Float(float value){std::uint32_t w;std::memcpy(&w,&value,4);Word(w);}
    void Holder(const ScoringHolder& owner)
    {
        const auto& s=owner.State();const auto& p=s.snapshot;
        for(auto v:{p.completed_lines,p.line,p.accumulated,p.last_reward,p.general_pending,p.fingerflip_pending,p.grind_reward})Float(v);
        for(auto v:s.repetitions)Word(static_cast<std::uint32_t>(static_cast<std::int32_t>(v)));
        for(auto v:s.sequence_history)Word(static_cast<std::uint32_t>(static_cast<std::int32_t>(v)));
        for(auto v:s.type_history)Word(static_cast<std::uint32_t>(static_cast<std::int32_t>(v)));
        Word(s.pending_sequence);Word(s.suppressed);
    }
    void Carrier(const ScoringCarrier& c)
    {
        Word(std::uint32_t(c.scorable.id));Word(c.scorable.category);Word(std::uint32_t(c.scorable.score_type));
        Word(static_cast<std::uint32_t>(c.points));Float(c.factor);Float(c.reward);Float(c.announcement_threshold);
        Word(c.start_tick);Word(c.delay_ticks);Word(c.announced);Word(c.completed);Word(c.unannounced);Word(c.switch_stance);Word(c.fakie);
    }
    void Snapshot(const ScoringSession& s,const std::array<ScoringCarrier,2>& carriers)
    {
        Holder(s.holder);Float(s.combo.timer.points);Word(s.combo.timer.expired);Float(s.combo.multiplier);
        Float(s.line.points);Word(s.line.expired);for(const auto& c:carriers)Carrier(c);
    }
};
}
int main()
{
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(bytes);Output o;
    const auto count=i.Word();o.Word(count);
    for(std::uint32_t c=0;c<count;++c)
    {
        ScoringSession s;std::array<ScoringCarrier,2> carriers{};const auto commands=i.Word();o.Word(c);o.Word(commands);o.Snapshot(s,carriers);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=i.Word();o.Word(op);std::uint32_t result=0;
            switch(op)
            {
            case 0:{const auto d=i.Scorable();const auto reward=i.Float();s.holder.EndTrick(d,reward);break;}
            case 1:{const auto d=i.Scorable();const auto reward=i.Float();s.holder.CreditTrick(d,reward);break;}
            case 2:s.holder.FinishCollector();break;
            case 3:s.holder.CancelPending();break;
            case 4:s.holder.RewardSequence(i.Float());break;
            case 5:{const auto reward=i.Float();const auto line=i.Word();s.holder.Publish(reward,line!=0);break;}
            case 6:s.holder.ClearSequenceHistory();break;
            case 7:s.holder.BankLine(i.Word()!=0);break;
            case 8:s.holder.Reset();break;
            case 9:s.holder.SetSuppressed(i.Word()!=0);break;
            case 10:{const auto value=s.holder.RepetitionCount(i.Scorable());result=value?std::uint32_t(std::int32_t(*value)):0xffffffff;break;}
            case 11:{const auto dt=i.Float(),drain=i.Float(),scale=i.Float();result=s.line.Advance(dt,drain,scale,i.Word()!=0);break;}
            case 12:{const auto reward=i.Float();const auto r=i.Rules();s.combo.Credit(reward,r.combo_capacity,r.combo_levels,r.combo_refresh_threshold);break;}
            case 13:{const auto reward=i.Float(),capacity=i.Float();s.line.Credit(reward,capacity);break;}
            case 14:{const auto r=i.Rules();const auto landing=i.Float();const auto penalized=i.Word(),enabled=i.Word();const auto f=s.PublishSequence(r,landing,penalized!=0,enabled!=0);std::memcpy(&result,&f,4);break;}
            case 15:{const auto reset=i.Word(),active=i.Word();s.SettleLine(reset!=0,active!=0);break;}
            case 16:
            {
                const auto slot=i.Word();const auto d=i.Scorable();const auto raw=i.Word();std::int32_t points;std::memcpy(&points,&raw,4);
                const auto factor=i.Float(),threshold=i.Float();const auto start=i.Word(),delay=i.Word(),stance=i.Word(),fakie=i.Word();
                carriers.at(slot)=ScoringCarrier::Create(d,points,factor,threshold,start,delay,stance!=0,fakie!=0);break;
            }
            case 17:{const auto slot=i.Word(),tick=i.Word();result=carriers.at(slot).Announce(tick,i.Float());break;}
            case 18:{const auto slot=i.Word();result=carriers.at(slot).Complete(i.Float());break;}
            case 19:{const auto slot=i.Word(),replacement=i.Word();const auto factor=i.Float();if(slot==replacement)return 2;carriers.at(slot).ConvertTo(carriers.at(replacement),factor);break;}
            case 20:{const auto authored=i.Float(),extra=i.Float();result=ScoringDelayTicks(authored,extra);break;}
            case 21:{const auto value=s.line.Seconds(i.Float());std::memcpy(&result,&value,4);break;}
            case 22:{const auto d=i.Scorable();result=std::uint32_t(d.Valid())|(std::uint32_t(d.RepetitionApplies())<<1);break;}
            default:return 2;
            }
            o.Word(result);o.Snapshot(s,carriers);
        }
    }
    if(!i.ok||i.Remaining())return 2;
    for(auto w:o.words)for(unsigned b=0;b<4;++b)std::cout.put(char(w>>(b*8)));
    return std::cout?0:2;
}
