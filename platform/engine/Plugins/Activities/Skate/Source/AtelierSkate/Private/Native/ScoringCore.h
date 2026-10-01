// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace atelier::skate
{
inline constexpr std::size_t ScorableCount=332;
inline constexpr std::size_t ScoreTypeCount=14;

struct ScoringScorable
{
    std::size_t id{};
    std::uint32_t category{};
    std::size_t score_type{};
    bool Valid() const {return id<ScorableCount&&score_type<ScoreTypeCount;}
    bool RepetitionApplies() const {return Valid()&&category!=5&&category!=6;}
};

struct ScoringSnapshot
{
    float completed_lines{},line{},accumulated{},last_reward{};
    float general_pending{},fingerflip_pending{},grind_reward{};
};

struct ScoringHolderState
{
    ScoringSnapshot snapshot{};
    std::array<std::int8_t,ScorableCount> repetitions{},sequence_history{};
    std::array<std::int8_t,ScoreTypeCount> type_history{};
    bool pending_sequence{},suppressed{};
};

class ScoringHolder
{
public:
    const ScoringHolderState& State() const {return state_;}
    bool HasPendingSequence() const {return state_.pending_sequence;}
    std::optional<std::int8_t> RepetitionCount(ScoringScorable) const;
    void SetSuppressed(bool suppressed) {state_.suppressed=suppressed;}
    void CreditTrick(ScoringScorable,float reward);
    void EndTrick(ScoringScorable,float reward);
    void FinishCollector() {state_.pending_sequence=true;}
    void CancelPending();
    void RewardSequence(float multiplier);
    void Publish(float reward,bool add_to_line);
    void ClearSequenceHistory();
    void FinishLine() {BankLine(true);}
    void BankLine(bool clear_repetition);
    void Reset();
private:
    ScoringHolderState state_{};
    void CountTrick(ScoringScorable);
};
}
