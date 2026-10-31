use crate::core::player::wipeout_state::{output::Output, response};
use crate::physics::SkaterRuntime;

pub(crate) fn fill(skater: &SkaterRuntime) -> Output {
    let runtime = &skater.wipeout_state;
    let feedback = &skater.collision_feedback;
    let normal = response::response_normal(
        feedback.flags.compliant.then_some(feedback.highest_normal),
        runtime.prediction.result.valid().then_some(runtime.prediction.result.landing_normal),
    );
    runtime.state.output(&skater.skeleton.record.pose[23], normal)
}
