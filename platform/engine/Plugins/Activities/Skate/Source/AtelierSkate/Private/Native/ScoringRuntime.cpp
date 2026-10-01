// SPDX-License-Identifier: Apache-2.0
#include "ScoringRuntime.h"
#include "NativeMath.h"
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool ScoringRuntime::Load(const SettingsDatabase& settings,std::string& error)
{
    ScoringRuntime next;if(!next.data.Load(settings,error))return false;
    *this=std::move(next);error.clear();return true;
}
float ScoringRuntime::Penalty(std::size_t id) const
{
    const auto* d=data.ById(id);if(!d)return 1;
    return d->metadata.RepetitionApplies()?data.repetition.Evaluate(float(session.holder.RepetitionCount(d->metadata).value_or(0))):1;
}
void ScoringRuntime::Finish(std::size_t slot,bool complete,bool keep_metric)
{
    auto& s=state_;auto carrier=s.carriers[slot];s.carriers[slot].reset();
    if(carrier&&complete)
    {
        carrier->Complete(data.unannounced_factor);
        if(s.collector==ScoringCollector::Air)session.holder.EndTrick(carrier->scorable,carrier->reward);
        else
        {
            const bool metric=s.collector==ScoringCollector::Grind||(s.collector==ScoringCollector::Ground&&slot<3);
            if(!(keep_metric&&s.collector==ScoringCollector::Ground))
            {
                const float reward=keep_metric?0:metric?(carrier->scorable.score_type==9?VectorMax(carrier->reward,s.metric_rewards[slot]):VectorMax(s.metric_rewards[slot],0)):carrier->reward;
                session.holder.CreditTrick(carrier->scorable,reward);
            }
        }
    }
    if(!keep_metric){s.metric_started[slot]=false;s.held[slot]=0;s.distance[slot]=0;s.metric_rewards[slot]=0;}
}
bool ScoringRuntime::Carrier(std::size_t slot,std::optional<std::size_t> id,const ScoringFrame& f,std::string& error)
{
    auto& s=state_;auto& current=s.carriers[slot];
    const auto current_id=current?std::optional<std::size_t>{current->scorable.id}:std::nullopt;
    if(current_id!=id)
    {
        const bool conversion=id&&s.collector==ScoringCollector::Air&&current&&ScoringConversionLinks[*id].first>=0;
        const auto* next_definition=id?data.ById(*id):nullptr;
        const bool chained_grab=s.collector==ScoringCollector::Air&&next_definition&&next_definition->metadata.category==2&&current&&current->scorable.category==2&&!current->announced;
        const auto previous_tick=current?std::optional<std::uint32_t>{current->start_tick}:std::nullopt;
        const bool keep_metric=id&&(s.collector==ScoringCollector::Grind||(s.collector==ScoringCollector::Ground&&slot==0));
        if(!conversion)
        {
            if(chained_grab){current.reset();++s.grab_chain;}
            else{Finish(slot,true,keep_metric);s.grab_chain=0;}
        }
        if(id)
        {
            const auto* d=data.ById(*id);if(!d){error="Missing native scorable "+std::to_string(*id);return false;}
            const float factor=Penalty(*id)*(s.collector==ScoringCollector::Air?s.air_factor:1);
            auto carrier=ScoringCarrier::Create(d->metadata,d->points,factor,data.announcement.Evaluate(float(d->points)),chained_grab?previous_tick.value_or(f.tick):f.tick,
                ScoringDelayTicks(d->completion_delay,s.grab_chain>1?data.collector.Scalar(0x698):0),f.switch_stance,f.fakie);
            if(current){current->ConvertTo(carrier,data.unannounced_factor);s.modified_trick=true;}
            if(conversion)s.trick_name=d->label;
            current=carrier;s.sequence_active=true;s.idle_ticks=0;
        }
    }
    const float penalty=current?Penalty(current->scorable.id):1;
    if(current)
    {
        auto& c=*current;
        if(c.Announce(f.tick,data.unannounced_factor))
        {
            const auto* d=data.ById(c.scorable.id);if(!d){error="Missing announced scorable";return false;}
            s.trick_name=d->label;s.stance={f.switch_stance,f.fakie,f.nollie,false};s.new_trick=true;
            if(s.collector==ScoringCollector::Air&&!s.air_repetition_set){s.air_repetition=penalty;s.air_repetition_set=true;}
        }
        const bool distance_metric=s.collector==ScoringCollector::Grind||(s.collector==ScoringCollector::Ground&&slot<3);
        const bool was_active=s.metric_started[slot];s.metric_started[slot]=true;
        if(c.announced&&!(s.collector==ScoringCollector::Air&&f.suspend_air))
        {
            if(!distance_metric||was_active)s.held[slot]+=f.dt;
            const float previous_distance=s.distance[slot];std::array<float,3> displacement{};
            for(std::size_t i=0;i<3;++i)displacement[i]=f.position[i]-s.previous[i];
            float delta=-0.0f;
            if(s.collector==ScoringCollector::Ground&&slot==1){for(std::size_t i=0;i<3;++i)delta+=displacement[i]*f.forward[i];}
            else{for(float x:displacement)delta+=x*x;delta=std::sqrt(delta);}
            if(was_active&&delta>0.005f)s.distance[slot]+=delta;
            std::optional<std::uint16_t> reward_curve;
            if(s.collector==ScoringCollector::Air&&c.scorable.category==2)reward_curve=0x460;
            else if(s.collector==ScoringCollector::Offboard)reward_curve=0x140;
            if(reward_curve)c.reward+=(data.collector.Curve(*reward_curve,s.held[slot])*f.dt)*c.announcement_threshold;
            std::optional<std::pair<std::uint16_t,std::uint16_t>> metric;
            if(s.collector==ScoringCollector::Ground)
            {
                if(c.scorable.score_type==9)metric={{0x000,0x050}};
                else if(c.scorable.score_type==8)metric={{0x0f0,0x0a0}};
                else if(slot==2)metric={{0x230,0x1e0}};
            }
            else if(s.collector==ScoringCollector::Grind)metric={{0x2d0,0x280}};
            if(metric)
            {
                const float amount=VectorMax(data.collector.Curve(metric->first,s.distance[slot])-data.collector.Curve(metric->first,previous_distance),0);
                s.metric_rewards[slot]=std::fma(std::fma(data.collector.Curve(metric->second,s.held[slot]),f.dt,amount),c.announcement_threshold,s.metric_rewards[slot]);
            }
        }
    }
    error.clear();return true;
}
}
