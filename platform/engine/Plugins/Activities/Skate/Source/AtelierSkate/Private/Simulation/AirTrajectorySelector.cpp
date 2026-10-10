#include "AirTrajectorySelector.h"
#include "AirTrajectorySelectorMath.h"
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace M=air_trajectory_detail;
const std::vector<AirTrajectoryQueryRequest>& AirTrajectorySelector::Requests() const
{static const std::vector<AirTrajectoryQueryRequest> empty;return batch_?batch_->requests:empty;}
std::optional<Vec4> AirTrajectorySelector::ComDisplacement() const {return batch_?std::optional<Vec4>{batch_->com_displacement}:std::nullopt;}
std::optional<Vec4> AirTrajectorySelector::LocalComPosition() const {return batch_?std::optional<Vec4>{batch_->local_com_position}:std::nullopt;}
std::optional<Vec4> AirTrajectorySelector::LocalBoardPosition() const {return batch_?std::optional<Vec4>{batch_->local_board_position}:std::nullopt;}
std::optional<Vec4> AirTrajectorySelector::BoardPosition() const {return batch_?std::optional<Vec4>{batch_->board_position}:std::nullopt;}
std::optional<Vec4> AirTrajectorySelector::QueryOrigin() const {return batch_?std::optional<Vec4>{batch_->origin}:std::nullopt;}
void AirTrajectorySelector::Reset()
{
    valid_=false;suggested_normal_.reset();grind_normal_.reset();just_changed_=false;all_predictions_missed_=false;pass_=0;grind_locked_to_middle_=false;
    if (selection_) selection_->com_trajectory={{},{},{},-1};
}
bool AirTrajectorySelector::Launch(AirLaunchInfo info,AirSelectorInput input,const AirTrajectorySelectorSettings& s,bool& launched,std::string& error)
{
    if (pending_) {launched=false;error.clear();return true;}
    if (info.trajectory_count==0) {error="GetLaunchInfo supplied zero trajectory candidates";return false;}
    pass_=0;valid_=false;selected_index_.reset();grind_normal_.reset();
    adjusted_on_vert_=AdjustAirTrajectoryLaunchVelocity(info,input,s);launch_info_=std::move(info);LaunchPass(input,s);
    launched=true;error.clear();return true;
}
void AirTrajectorySelector::LaunchPass(AirSelectorInput input,const AirTrajectorySelectorSettings& s)
{
    if (!launch_info_) std::abort();
    all_predictions_missed_=false;if (selection_) selection_->wall_ride=false;
    auto batch=BuildAirTrajectoryLaunchBatch(*launch_info_,input,s);
    while (candidates_.size()<batch.requests.size())
        candidates_.push_back({{AirTrajectoryQueryResult::Miss(),batch.requests[0]},{},{},{},{},0,0,false,std::nullopt});
    for (std::size_t index=0;index<batch.requests.size();++index)
    {candidates_[index].start_velocity=batch.velocities[index];candidates_[index].prediction={AirTrajectoryQueryResult::Miss(),batch.requests[index]};}
    batch_=std::move(batch);pending_=true;
}
bool AirTrajectorySelector::CompleteBatch(const std::vector<AirTrajectoryQueryResult>& results,AirSelectorInput input,
    const AirTrajectorySelectorSettings& s,AirTrajectorySelectionServices& services,bool& output,std::string& error)
{
    just_changed_=false;if (!pending_) {output=valid_;error.clear();return true;}
    const auto count=Requests().size();if (results.size()!=count) {error="Trajectory completion count differs from submitted batch";return false;}
    just_changed_=pass_==2;pending_=false;pass_=static_cast<std::uint16_t>(pass_+1);
    for (std::size_t index=0;index<count;++index) candidates_[index].prediction.result=results[index];
    if (!ScoreAirTrajectoryCandidates(candidates_.data(),count,pass_,adjusted_on_vert_,input,s,services,all_predictions_missed_,error)) return false;
    std::size_t index=0;float best=-100000000;
    for (std::size_t i=0;i<count;++i) if (candidates_[i].score>best) {best=candidates_[i].score;index=i;}
    if (index>=candidates_.size()) std::abort();const auto c=candidates_[index];
    for (std::size_t i=0;i<count;++i) if (candidates_[i].grind) {grind_normal_=candidates_[i].grind->vertical_normal;break;}
    selected_index_=index;
    AirTrajectorySelection selection{index,c.prediction,c.start_velocity,c.normal,c.collision_velocity,c.collision_position,
        selection_?selection_->com_trajectory:AirTrajectory{{},{},{},-1},selection_?selection_->surface_category:0,c.wall_ride,c.grind};
    if (c.prediction.result.contact_time<s.minimum_valid_time)
    {
        suggested_normal_=c.prediction.result.contact_normal;valid_=false;just_changed_=false;selection_=selection;output=false;error.clear();return true;
    }
    selection.surface_category=(c.prediction.result.surface>>7)&31;selection.com_trajectory=ComTrajectory(selection,input,s);
    grind_locked_to_middle_=index==0&&c.grind.has_value();
    const bool second=pass_==1&&count>=2&&!grind_locked_to_middle_
        &&!(M::AngleBetween(selection.landing_normal,input.ground_normal)<s.minimum_normal_delta_second_pass);
    selection_=selection;valid_=true;
    if (second)
    {
        if (!launch_info_) std::abort();launch_info_->start_velocity=selection.start_velocity;
        launch_info_->cone_angle_x=s.cone_x_second_pass;launch_info_->cone_angle_z=s.cone_z_second_pass;LaunchPass(input,s);pass_=2;
    }
    output=valid_;error.clear();return true;
}
AirTrajectory AirTrajectorySelector::ComTrajectory(const AirTrajectorySelection& selection,AirSelectorInput input,const AirTrajectorySelectorSettings& s) const
{
    if (!launch_info_||!batch_) std::abort();const auto& info=*launch_info_;const auto& batch=*batch_;
    auto trajectory=selection.prediction.request.trajectory;
    const float scalar=s.landing_com_scalar_vs_slope.Evaluate(selection.landing_normal[1]);
    const auto delta=M::Sub(info.animation_com_position,trajectory.position);
    const float height=std::fabs(Dot3(input.reference_up,M::Sub(batch.origin,info.animation_com_position)))*scalar;
    const auto offset=M::Scale(selection.landing_normal,height);
    if (selection.prediction.result.contact_frame>0)
    {
        trajectory.position=M::Add(trajectory.position,delta);
        AdjustAirTrajectoryVelocity(trajectory,selection.prediction.result.contact_frame,M::Sub(offset,delta),s.maximum_trajectory_adjust);
    }
    return trajectory;
}
}
