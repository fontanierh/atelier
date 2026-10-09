#pragma once
#include "AnimationPhaseInput.h"
namespace atelier::skate
{
struct TeleportCheckpoint {Mat4 transform;bool on_board;};
struct TeleportTarget {RawMatrix transform;bool on_board;};
class TeleportCoreState
{
public:
    enum class Update {RequestCheckpoint,Captured};
    void Enter();
    Update Process(std::uint32_t flags_2468,RawMatrix matrix_1536,std::uint8_t byte_1600);
    std::optional<TeleportOutputFields> Output() const;
    const RawMatrix& Target() const {return target_;}
    bool Ready() const {return ready_;}
    bool Received() const {return received_;}
    bool OnBoard() const {return on_board_;}
private:
    RawMatrix target_{};
    bool ready_=false,received_=false,on_board_=true;
};
// Source physics/teleport_state.rs. Deferred replies and manual/ejection
// requests retain their distinct ownership; publishing a reply resets no body.
class TeleportStateRuntime
{
public:
    explicit TeleportStateRuntime(TeleportCheckpoint checkpoint):checkpoint_(checkpoint){}
    void RequestManual(Mat4,bool on_board);
    void RequestVehicleEjection(Mat4,std::array<float,3> velocity,std::array<float,3> angular);
    std::optional<std::pair<std::array<float,3>,std::array<float,3>>> TakeVehicleEjection();
    std::optional<bool> TakeManualOnBoard();
    void SetCheckpoint(TeleportCheckpoint);
    void Enter(){state_.Enter();}
    bool Update(const ProcessedPhysicsInput&);
    void RequestCheckpoint(){Reply(checkpoint_);}
    void Reply(TeleportCheckpoint);
    std::optional<AnimationExternalReset> TakeReply();
    std::optional<TeleportOutputFields> PublishOutput(PhysicalPlayerInput&) const;
    const TeleportCoreState& State() const {return state_;}
    const TeleportCheckpoint& Checkpoint() const {return checkpoint_;}
    const std::optional<TeleportTarget>& PendingReply() const {return pending_reply_;}
    const std::optional<bool>& ManualOnBoard() const {return manual_on_board_;}
    const std::optional<std::pair<std::array<float,3>,std::array<float,3>>>& VehicleEjection() const {return vehicle_ejection_;}
private:
    TeleportCoreState state_;
    TeleportCheckpoint checkpoint_;
    std::optional<TeleportTarget> pending_reply_;
    std::optional<bool> manual_on_board_;
    std::optional<std::pair<std::array<float,3>,std::array<float,3>>> vehicle_ejection_;
};
}
