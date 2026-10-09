#include "PlayerStateCoordinator.h"
#include <cmath>
namespace atelier::skate
{
bool AdvancePlayerPreState(PlayerStateCoordinatorOwners owners,const OffboardGrabScene& scene,std::string& error)
{
    ++owners.input.player.state_count_1312;
    const auto state=owners.state.Current();
    if(!owners.state.registry.Capability(state).has_enter)
    {error="PreState requires the selected state's actual PredictFutureOfDeck";return false;}
    constexpr auto deck_index=static_cast<std::size_t>(BoardBodyId::Deck);
    const auto deck=owners.physical.board.PartTransforms()[deck_index];
    const auto velocity=owners.physical.board.Bodies()[deck_index].rates.linear_velocity;
    const float dt=owners.input.processed.timestep_2604;
    const Vec4 prediction{std::fma(velocity.x,dt,deck.translation.x),
        std::fma(velocity.y,dt,deck.translation.y),std::fma(velocity.z,dt,deck.translation.z),0};
    auto& roots=owners.physical.roots;
    roots.predicted_board_position=prediction;roots.supplied_prediction=prediction;
    owners.ik.state.contacts.support_failed=false;
    const auto& p=owners.input.processed;
    return owners.grab.Sync(scene,{p.actor_query_2948,static_cast<std::int32_t>(p.actor_query_2952)},error);
}
}
