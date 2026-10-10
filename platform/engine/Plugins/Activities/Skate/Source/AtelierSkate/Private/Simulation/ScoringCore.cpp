#include "ScoringCore.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
void Increment(std::int8_t& value)
{if(value<127)value=static_cast<std::int8_t>(value+1);}
}
std::optional<std::int8_t> ScoringHolder::RepetitionCount(ScoringScorable scorable) const
{return scorable.Valid()?std::optional<std::int8_t>{state_.repetitions[scorable.id]}:std::nullopt;}
void ScoringHolder::CountTrick(ScoringScorable scorable)
{
    Increment(state_.repetitions[scorable.id]);
    if(scorable.score_type!=0)
    {
        Increment(state_.sequence_history[scorable.id]);
        Increment(state_.type_history[scorable.score_type]);
    }
}
void ScoringHolder::CreditTrick(ScoringScorable scorable,float reward)
{
    if(!scorable.Valid()||state_.suppressed)return;
    CountTrick(scorable);state_.snapshot.accumulated+=reward;
}
void ScoringHolder::EndTrick(ScoringScorable scorable,float reward)
{
    if(!scorable.Valid()||state_.suppressed)return;
    CountTrick(scorable);auto& s=state_.snapshot;
    if(scorable.category!=5){s.general_pending+=s.fingerflip_pending;s.fingerflip_pending=0;}
    if(scorable.category==3)s.fingerflip_pending+=reward;
    else s.general_pending+=reward;
}
void ScoringHolder::CancelPending()
{
    if(state_.pending_sequence)
    {state_.snapshot.general_pending=0;state_.snapshot.fingerflip_pending=0;}
}
void ScoringHolder::RewardSequence(float multiplier)
{
    if(!state_.pending_sequence)return;
    auto& s=state_.snapshot;s.accumulated+=(s.general_pending+s.fingerflip_pending)*multiplier;
    s.general_pending=0;s.fingerflip_pending=0;state_.pending_sequence=false;
}
void ScoringHolder::Publish(float reward,bool add_to_line)
{
    auto& s=state_.snapshot;if(add_to_line)s.line+=reward;
    s.last_reward=reward;s.accumulated=0;s.general_pending=0;s.fingerflip_pending=0;
    ClearSequenceHistory();
}
void ScoringHolder::ClearSequenceHistory()
{state_.sequence_history.fill(0);state_.type_history.fill(0);state_.snapshot.grind_reward=0;}
void ScoringHolder::BankLine(bool clear_repetition)
{
    state_.snapshot.completed_lines+=state_.snapshot.line;state_.snapshot.line=0;
    if(clear_repetition)state_.repetitions.fill(0);
}
void ScoringHolder::Reset()
{const auto completed=state_.snapshot.completed_lines;state_={};state_.snapshot.completed_lines=completed;}
}
