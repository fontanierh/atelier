//! Minimal in-process fixture seam. Scripted faults never launch or kill tools.
//! Full graph scenarios, hooks and the reference model belong to A8/H1.
use crate::protocol::{FailureKind, JobOutputs, JobRequest, WorkerFailure};
use std::collections::VecDeque;

pub trait Worker {
    fn run(&mut self, job: &JobRequest) -> Result<JobOutputs, WorkerFailure>;
}

#[derive(Clone, Debug, PartialEq)]
pub struct FixtureFile {
    pub path: String,
    pub bytes: Vec<u8>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MockStep {
    pub expected_unit: String,
    /// Bytes are returned to the harness separately from the wire result.
    pub result: Result<Vec<FixtureFile>, WorkerFailure>,
}

#[derive(Default)]
pub struct MockWorker {
    steps: VecDeque<MockStep>,
    calls: Vec<JobRequest>,
    produced: Vec<(String, Vec<FixtureFile>)>,
}

impl MockWorker {
    pub fn new(steps: impl IntoIterator<Item = MockStep>) -> Self {
        Self {
            steps: steps.into_iter().collect(),
            ..Self::default()
        }
    }

    pub fn calls(&self) -> &[JobRequest] {
        &self.calls
    }
    pub fn produced(&self) -> &[(String, Vec<FixtureFile>)] {
        &self.produced
    }
    pub fn is_exhausted(&self) -> bool {
        self.steps.is_empty()
    }
}

impl Worker for MockWorker {
    fn run(&mut self, job: &JobRequest) -> Result<JobOutputs, WorkerFailure> {
        self.calls.push(job.clone());
        let step = self.steps.pop_front().ok_or_else(|| WorkerFailure {
            kind: FailureKind::Protocol,
            message: format!("unexpected job: {}", job.unit),
        })?;
        if step.expected_unit != job.unit {
            return Err(WorkerFailure {
                kind: FailureKind::Protocol,
                message: format!("expected {}, received {}", step.expected_unit, job.unit),
            });
        }
        let files = step.result?;
        let outputs = JobOutputs {
            files: files.iter().map(|file| file.path.clone()).collect(),
        };
        self.produced.push((job.job_id.clone(), files));
        Ok(outputs)
    }
}
