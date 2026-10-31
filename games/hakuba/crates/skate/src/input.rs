//! Platform input adapter; no animation or physics state mutation here.

mod controllers;
pub(crate) mod gesture_catalog;
pub(crate) mod gesture_input;
pub(crate) mod gesture_mapping;
mod gesture_mapping_data;
pub(crate) mod platform;
pub(crate) use controllers::ControllerInput;
pub(crate) fn sample(input: &mut ControllerInput, state: crate::core::input::xbox::XboxState) {
    input.collect([
        Ok(platform::DevicePacket { number: input.publications as u32 + 1, state, subtype: 1 }),
        Err(platform::DeviceError::Disconnected),
        Err(platform::DeviceError::Disconnected),
        Err(platform::DeviceError::Disconnected),
    ]);
    input.publish_actions();
}
