#include "ScoringRuntime.h"
#include "NativeMath.h"
#include <cmath>
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
void ScoringIncrement(std::uint32_t& value){if(value!=0xffffffff)++value;}
std::int32_t ScoringInteger(float value)
{
    if(std::isnan(value))return 0;
    if(value>=2147483648.0f)return std::numeric_limits<std::int32_t>::max();
    if(value<=-2147483648.0f)return std::numeric_limits<std::int32_t>::min();
    return std::int32_t(value);
}
float ScoringWrappedDegrees(std::int32_t turns)
{const auto word=std::uint32_t(turns)*180;std::int32_t value;std::memcpy(&value,&word,4);return float(value);}
}
bool ScoringRuntime::Advance(const ScoringFrame& f,std::string& error)
{
    auto& s=state_;s.new_trick=false;s.modified_trick=false;s.close_tricks=false;
    const auto* descriptor=f.descriptor?data.ByName(*f.descriptor):nullptr;
    if(descriptor&&(f.flags&0x02000000)!=0&&(descriptor->metadata.id==67||descriptor->metadata.id==68||descriptor->metadata.id==69))descriptor=nullptr;
    ScoringCollector next=ScoringCollector::None;
    switch(f.category)
    {
        case 1:next=ScoringCollector::Ground;break;case 2:next=ScoringCollector::Air;break;
        case 3:next=ScoringCollector::Grind;break;case 6:case 7:next=ScoringCollector::Offboard;break;
        default:break;
    }
    if(f.state==600&&(next==ScoringCollector::Ground||next==ScoringCollector::Air))next=ScoringCollector::Special;
    if(next==ScoringCollector::Air&&s.collector==ScoringCollector::Ground&&descriptor&&descriptor->metadata.category==0)next=ScoringCollector::Ground;
    if(next==ScoringCollector::Ground&&s.collector==ScoringCollector::Air&&descriptor&&descriptor->metadata.category==3)next=ScoringCollector::Air;
    if(f.teleported)next=ScoringCollector::None;
    if(next!=s.collector)
    {
        const bool complete=next!=ScoringCollector::None;std::optional<std::size_t> previous_type;
        for(const auto& carrier:s.carriers)if(carrier)previous_type=carrier->scorable.score_type;
        for(std::size_t slot=0;slot<4;++slot)Finish(slot,complete,false);
        if(s.collector==ScoringCollector::Air)
        {
            if(complete)for(std::size_t i=0;i<s.air_metrics.size();++i)if(const auto* d=data.ById(129+i))session.holder.EndTrick(d->metadata,s.air_metrics[i]);
            session.holder.FinishCollector();s.landing_countdown=2;
        }
        s.collector=next;s.start=f.position;s.peak=f.position[1];s.spin=0;
        s.previous_heading=std::atan2(f.forward[0],f.forward[2]);s.air_metrics={};s.air_repetition=1;
        s.air_repetition_set=false;s.air_factor=1;s.grab_chain=0;s.collector_ticks=0;s.manual_revert_ticks=0;s.revert_id.reset();
        if(next==ScoringCollector::Air)
        {
            session.holder.RewardSequence(1);s.landing_countdown=0;
            if(previous_type==8)s.air_factor*=data.collector.Scalar(0x68c);
            if(previous_type==5)s.air_factor*=data.collector.Scalar(0x690);
            const auto threshold=data.collector.Scalar(0x66c);
            if(f.velocity[0]*f.velocity[0]+f.velocity[2]*f.velocity[2]<threshold*threshold)s.air_factor*=data.collector.Scalar(0x688);
            if(f.switch_stance&&!f.fakie)s.air_factor*=data.collector.Scalar(0x684);
            if(f.fakie&&!f.switch_stance)s.air_factor*=data.collector.Scalar(0x694);
        }
    }
    std::array<std::optional<std::size_t>,4> ids{};
    if(!(s.collector==ScoringCollector::Air&&f.suspend_air))ScoringIncrement(s.collector_ticks);
    switch(s.collector)
    {
        case ScoringCollector::Ground:
            if(f.flags&0x80000000)ids[0]=0;else if(f.flags&0x40000000)ids[0]=1;
            if(f.flags&0x08000000)ids[1]=2;else if(f.flags&0x04000000)ids[1]=3;
            if(ids[1]&&f.reverting){++s.manual_revert_ticks;ids[1].reset();}else s.manual_revert_ticks=0;
            if(s.manual_revert_ticks>6)ids[1].reset();
            if(ids[1]&&s.carriers[1])ids[1]=s.carriers[1]->scorable.id;
            if(descriptor&&descriptor->metadata.id==60&&(f.flags&0x02000000)!=0)ids[2]=descriptor->metadata.id;
            if(f.flags&0x20000000)s.revert_id=4;else if(f.flags&0x10000000)s.revert_id=5;
            if(f.reverting)ids[3]=s.revert_id;
            break;
        case ScoringCollector::Air:if(descriptor&&descriptor->metadata.score_type!=5)ids[0]=descriptor->metadata.id;break;
        case ScoringCollector::Grind:if(f.grind_id>=0)ids[0]=std::size_t(f.grind_id);break;
        case ScoringCollector::Offboard:if(descriptor&&descriptor->metadata.score_type==6)ids[0]=descriptor->metadata.id;break;
        case ScoringCollector::Special:if(descriptor&&descriptor->metadata.id==234)ids[0]=descriptor->metadata.id;break;
        case ScoringCollector::None:break;
    }
    for(std::size_t slot=0;slot<4;++slot)if(!Carrier(slot,ids[slot],f,error))return false;
    if(s.collector==ScoringCollector::Air&&!f.suspend_air)
    {
        if(s.collector_ticks>5||(f.flags&0x01000000)!=0)s.sequence_active=true;
        constexpr float pi=3.14159265358979323846f,tau=6.28318530717958647692f;
        const float heading=std::atan2(f.forward[0],f.forward[2]);float delta=std::fmod(heading-s.previous_heading+pi,tau);
        if(delta<0)delta+=std::abs(tau);delta-=pi;s.spin+=delta;s.previous_heading=heading;s.peak=VectorMax(s.peak,f.position[1]);
        const float dx=f.position[0]-s.start[0],dz=f.position[2]-s.start[2],scale=s.air_factor*s.air_repetition;
        s.air_metrics[0]=data.collector.Curve(0x3c0,std::sqrt(dx*dx+dz*dz))*scale;
        s.air_metrics[1]=data.collector.Curve(0x410,s.peak-s.start[1])*scale;
        s.air_metrics[2]=data.collector.Curve(0x320,f.position[1]-s.start[1])*scale;
        const auto turns=ScoringInteger((std::abs(s.spin*(180.0f/pi))+data.collector.Scalar(0x63c))/180.0f);
        s.air_metrics[3]=data.collector.Curve(0x370,ScoringWrappedDegrees(turns))*scale;
        if(f.body_flip&&s.carriers[0]&&s.carriers[0]->announced&&s.carriers[0]->scorable.category==2)s.air_metrics[4]=data.collector.Scalar(0x640)*scale;
    }
    bool active=s.collector==ScoringCollector::Air;for(const auto& c:s.carriers)active|=bool(c);
    if(active)s.idle_ticks=0;else ScoringIncrement(s.idle_ticks);
    if(session.holder.HasPendingSequence())
    {
        if(f.landing_data_167){s.clean=f.landing_type_96==0;s.sketchy=f.landing_type_96==1&&f.sideways_speed_84>data.sketchy_side_speed&&std::abs(f.spin_92)>0.5f;}
        if(s.landing_countdown==0)
        {
            float factor=1;
            if(f.switch_stance&&!f.fakie)factor*=data.collector.Scalar(0x61c);
            if(f.fakie&&!f.switch_stance)factor*=data.collector.Scalar(0x62c);
            if(s.collector==ScoringCollector::Grind)factor*=data.collector.Scalar(0x628);
            if(s.clean)factor*=data.collector.Scalar(0x630);
            if(s.sketchy)factor*=data.collector.Scalar(0x620);
            session.holder.RewardSequence(factor);
        }
        else --s.landing_countdown;
    }
    std::pair<std::uint16_t,std::uint16_t> scales{0x610,0x60c};
    if(s.collector==ScoringCollector::Air)scales={0x668,0x664};
    else if(s.collector==ScoringCollector::Grind)scales={0x618,0x614};
    else if(s.collector==ScoringCollector::Offboard)scales={0x608,0x604};
    const float line_scale=active?data.collector.Scalar(scales.first):1,combo_scale=active?data.collector.Scalar(scales.second):1;
    session.line.Advance(f.dt,data.line_drain,line_scale,active);session.combo.timer.Advance(f.dt,data.combo_drain,combo_scale,active);
    const bool bailout=s.collector==ScoringCollector::None&&s.sequence_active;
    if(s.sequence_active&&(bailout||(s.idle_ticks>=3&&s.landing_countdown==0)))
    {
        if(bailout)session.holder.CancelPending();
        s.sequence_score=session.PublishSequence(data.SessionRules(),1,bailout,true);s.sequence_active=false;s.close_tricks=bailout;
    }
    else if(s.sequence_active)
    {
        const auto& snapshot=session.holder.State().snapshot;float carriers=-0.0f;
        for(std::size_t i=0;i<s.carriers.size();++i)if(const auto& c=s.carriers[i])
        {
            const bool metric=s.collector==ScoringCollector::Grind||(s.collector==ScoringCollector::Ground&&i<3);
            carriers+=metric?(c->scorable.score_type==9?VectorMax(c->reward,s.metric_rewards[i]):s.metric_rewards[i]):c->reward;
        }
        float metrics=-0.0f;for(float value:s.air_metrics)metrics+=value;
        s.sequence_score=(snapshot.accumulated+snapshot.general_pending+snapshot.fingerflip_pending+carriers+metrics)*session.combo.multiplier;
    }
    if(session.line.expired||f.teleported||bailout)s.sequence_score=0;
    session.SettleLine(f.teleported||bailout,active);s.previous=f.position;error.clear();return true;
}
}
