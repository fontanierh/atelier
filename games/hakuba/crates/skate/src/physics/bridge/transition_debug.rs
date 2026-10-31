//! Test-only native mount/dismount observations for lifecycle regressions.
use super::Session;
impl Session {
    pub(crate) fn transition_debug(&self) -> String {
        let animation = &self.skater.animation;
        let action =
            animation.action_controller.frame.current.map(|id| self.graphs.action.binding.states[id].name.as_str());
        let motion =
            animation.motion_controller.frame.current.map(|id| self.graphs.motion.binding.states[id].name.as_str());
        let physical = &self.skater.player_input.physical;
        format!(
            "raw={:08x}/{:08x} actor={:08x} AG={action:?} MG={motion:?} toggle={:?}/{:?} dismount={:?} mount={:?} armount={:?} category={} air452={}",
            self.controls.controller.words()[6],
            self.controls.controller.words()[13],
            self.controls.actor_flags,
            animation.action.action_intents.get("NewToggleOffBoardState"),
            animation.action.action_intents.get("ToggleOffBoardState"),
            animation.action.motion_intents.get("OB_Dismount"),
            animation.action.motion_intents.get("OB_Mount"),
            animation.action.motion_intents.get("OB_MountRaw"),
            physical.state.category_12,
            physical.air.use_air_reckoning_452
        )
    }
}
