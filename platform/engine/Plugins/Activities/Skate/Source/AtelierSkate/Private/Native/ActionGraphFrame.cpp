// SPDX-License-Identifier: Apache-2.0
#include "ActionGraphFrame.h"
namespace atelier::skate
{
void ActionIntentGraphHost::PrepareInput(const ActionGraphInput& input)
{
    tick=input.tick;
    PrepareInput(input.controls,input.prior_motion,input.animation_attributes);
}
ActionGraphOutput ActionIntentGraphHost::Output() const
{return ActionGraphOutput::FromHost(tick,action_intents,motion_intents,animation_attributes);}
}
