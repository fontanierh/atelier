//! Normal gameplay camera rendering endpoint. Simulation owns the cadence of
//! CameraRuntime::advance after its complete physical/animation publication.
mod collision;
mod graph;
mod graph_conditions;
mod graph_subject;
mod publication;
mod runtime;
mod settings;
pub(crate) mod shot_data;
mod subject;
mod trajectory;
mod world_query;
pub(crate) use graph_subject::CameraGraphEnvironment;
pub(crate) use publication::{
    CameraAirOutput, CameraAnimationOutput, CameraEventsOutput, CameraGrindOutput, CameraOffboardOutput,
    CameraPreferences, CameraPublicationInputs, CameraStateOutput, snapshot as publish_camera_subject,
};
pub(crate) use runtime::CameraRuntime;
