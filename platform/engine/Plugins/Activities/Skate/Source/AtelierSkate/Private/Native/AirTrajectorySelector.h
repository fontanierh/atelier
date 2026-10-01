// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirTrajectoryLaunch.h"
#include "AirTrajectoryScoring.h"
namespace atelier::skate
{
class AirTrajectorySelector
{
public:
    bool Pending() const {return pending_;}
    bool Valid() const {return valid_;}
    bool JustChanged() const {return just_changed_;}
    bool AllPredictionsMissed() const {return all_predictions_missed_;}
    std::optional<Vec4> SuggestedNormal() const {return suggested_normal_;}
    const std::optional<AirTrajectorySelection>& Selection() const {return selection_;}
    std::optional<std::size_t> SelectedIndex() const {return selected_index_;}
    bool GrindLockedToMiddle() const {return grind_locked_to_middle_;}
    std::optional<Vec4> GrindNormal() const {return grind_normal_;}
    const std::optional<AirLaunchInfo>& LaunchInfo() const {return launch_info_;}
    const std::vector<AirTrajectoryQueryRequest>& Requests() const;
    std::optional<Vec4> ComDisplacement() const;
    std::optional<Vec4> LocalComPosition() const;
    std::optional<Vec4> LocalBoardPosition() const;
    std::optional<Vec4> BoardPosition() const;
    std::optional<Vec4> QueryOrigin() const;
    bool UpdateWithoutCompletion() {just_changed_=false;return valid_;}
    void CancelPending() {pending_=false;}
    void Reset();
    bool Launch(AirLaunchInfo,AirSelectorInput,const AirTrajectorySelectorSettings&,bool& launched,std::string& error);
    bool CompleteBatch(const std::vector<AirTrajectoryQueryResult>&,AirSelectorInput,
        const AirTrajectorySelectorSettings&,AirTrajectorySelectionServices&,bool& valid,std::string& error);
    // Read-only retained state is useful to verify lifecycle continuity.
    const std::vector<AirTrajectoryCandidate>& Candidates() const {return candidates_;}
    const std::optional<AirTrajectoryLaunchBatch>& Batch() const {return batch_;}
    std::uint16_t Pass() const {return pass_;}
    bool AdjustedOnVert() const {return adjusted_on_vert_;}
private:
    std::optional<AirLaunchInfo> launch_info_;
    std::optional<AirTrajectoryLaunchBatch> batch_;
    std::vector<AirTrajectoryCandidate> candidates_;
    std::optional<AirTrajectorySelection> selection_;
    std::optional<std::size_t> selected_index_;
    bool grind_locked_to_middle_=false;
    std::optional<Vec4> grind_normal_;
    std::uint16_t pass_=0;
    bool adjusted_on_vert_=false,pending_=false,valid_=false,just_changed_=false,all_predictions_missed_=false;
    std::optional<Vec4> suggested_normal_;
    void LaunchPass(AirSelectorInput,const AirTrajectorySelectorSettings&);
    AirTrajectory ComTrajectory(const AirTrajectorySelection&,AirSelectorInput,const AirTrajectorySelectorSettings&) const;
};
}
