//! Controller-side ordering of one worker conversation over protocol v1 (C1a).
//!
//! [`Session`] is a pure state machine: it validates each request the controller is about to send
//! and each response the worker returns. [`Channel`] drives it over a dedicated framed pipe.
//! Order: the worker says `hello` with the expected version; then, one job at a time, `run` is
//! answered by `started` and exactly one terminal `completed`/`failed` with the same job ID;
//! `shutdown` (only while idle) is answered by `stopped`, then a clean end of stream.
//! Any other response, a malformed frame or an early end of stream breaks the session for good.
//!
//! Sending `cancel` only records a request. A job is cancelled only when the worker answers
//! `failed` with kind `cancelled`; a job that finished first still reports `completed`.
//! The session does not stage files, launch processes, keep deadlines, retry, classify crashes or
//! validate returned output paths: C1b, C5 and the result validator own those decisions.
use crate::protocol::{
    FailureKind, JobOutputs, JobRequest, Request, Response, WorkerFailure, read_frame, write_frame,
};
use std::collections::BTreeSet;
use std::fmt;
use std::io::{self, Read, Write};

#[derive(Clone, Debug, PartialEq)]
pub enum State {
    AwaitingHello,
    Idle,
    /// `run` sent for `job_id`; `started` tells whether the worker acknowledged it.
    Active {
        job_id: String,
        started: bool,
        cancel_requested: bool,
    },
    /// `shutdown` sent; waiting for `stopped`.
    Stopping,
    /// `stopped` received; only a clean end of stream may follow.
    Closed,
    /// A protocol violation or lost pipe. The worker must be stopped, never reused.
    Broken,
}

#[derive(Clone, Debug, PartialEq)]
pub enum SessionError {
    /// The controller asked for something this state forbids. The session is unchanged.
    Misuse(String),
    /// The worker broke the protocol (bad frame, version, job ID or order). The session is broken.
    Protocol(String),
    /// The pipe failed or ended outside a clean close. The session is broken; whether the process
    /// crashed is for its supervisor to establish, not this session.
    Disconnected(String),
}

impl fmt::Display for SessionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Misuse(message) => write!(formatter, "session misuse: {message}"),
            Self::Protocol(message) => write!(formatter, "worker protocol violation: {message}"),
            Self::Disconnected(message) => write!(formatter, "worker pipe lost: {message}"),
        }
    }
}

impl std::error::Error for SessionError {}

#[derive(Clone, Debug, PartialEq)]
pub struct JobFinished {
    pub job_id: String,
    pub result: Result<JobOutputs, WorkerFailure>,
    /// Whether `cancel` had been sent; true with `Ok` means the job finished first.
    pub cancel_requested: bool,
}

impl JobFinished {
    /// True only when the worker confirmed the cancellation.
    pub fn cancelled(&self) -> bool {
        matches!(&self.result, Err(failure) if failure.kind == FailureKind::Cancelled)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Event {
    Ready { worker_version: String },
    Started { job_id: String },
    Finished(JobFinished),
    Stopped,
}

#[derive(Clone, Debug)]
pub struct Session {
    state: State,
    expected_worker_version: String,
    used_job_ids: BTreeSet<String>,
    last_finished: Option<String>,
}

fn misuse<T>(message: impl Into<String>) -> Result<T, SessionError> {
    Err(SessionError::Misuse(message.into()))
}

/// Worker-facing names are job-relative. This guards the wire against absolute or escaping
/// paths (an original checkout locator, for example); the full path policy belongs to A2/C1b.
fn job_relative(path: &str, label: &str) -> Result<(), SessionError> {
    let valid = !path.is_empty()
        && !path.starts_with('/')
        && !path.contains(['\\', '\0'])
        && path
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..");
    if valid {
        Ok(())
    } else {
        misuse(format!("{label} is not a job-relative path: {path:?}"))
    }
}

fn check_job(job: &JobRequest) -> Result<(), SessionError> {
    if job.job_id.is_empty() {
        return misuse("job ID is empty");
    }
    if job.job_dir.is_empty() {
        return misuse("job folder is empty");
    }
    job_relative(&job.script, "script")?;
    for path in &job.code {
        job_relative(path, "code file")?;
    }
    for input in &job.inputs {
        job_relative(&input.path, "input")?;
    }
    for output in &job.outputs {
        job_relative(&output.path, "output")?;
    }
    Ok(())
}

impl Session {
    /// `expected_worker_version` is the version the controller keyed this work with.
    pub fn new(expected_worker_version: impl Into<String>) -> Self {
        Self {
            state: State::AwaitingHello,
            expected_worker_version: expected_worker_version.into(),
            used_job_ids: BTreeSet::new(),
            last_finished: None,
        }
    }

    pub fn state(&self) -> &State {
        &self.state
    }

    fn usable(&self) -> Result<(), SessionError> {
        match self.state {
            State::Broken => misuse("the session is broken"),
            State::Closed => misuse("the session is closed"),
            _ => Ok(()),
        }
    }

    /// Accept a new job while idle. Job IDs are unique for the session, so a late response for an
    /// earlier job can never be mistaken for the current one.
    pub fn run(&mut self, job: JobRequest) -> Result<Request, SessionError> {
        self.usable()?;
        match &self.state {
            State::Idle => {}
            State::AwaitingHello => return misuse("run before the worker said hello"),
            State::Active { job_id, .. } => return misuse(format!("job {job_id} is still active")),
            _ => return misuse("run after shutdown"),
        }
        check_job(&job)?;
        if self.used_job_ids.contains(&job.job_id) {
            return misuse(format!("job ID {} was already used", job.job_id));
        }
        self.used_job_ids.insert(job.job_id.clone());
        self.state = State::Active {
            job_id: job.job_id.clone(),
            started: false,
            cancel_requested: false,
        };
        Ok(Request::Run { job })
    }

    /// Request cancellation of the active job. This is not a result: the job still owes one terminal.
    pub fn cancel(&mut self) -> Result<Request, SessionError> {
        self.usable()?;
        match &mut self.state {
            State::Active {
                job_id,
                cancel_requested,
                ..
            } => {
                if *cancel_requested {
                    return misuse(format!("cancel already requested for job {job_id}"));
                }
                *cancel_requested = true;
                Ok(Request::Cancel {
                    job_id: job_id.clone(),
                })
            }
            _ => misuse("cancel without an active job"),
        }
    }

    /// Shut down an idle worker. An active job must reach its terminal response first.
    pub fn shutdown(&mut self) -> Result<Request, SessionError> {
        self.usable()?;
        match &self.state {
            State::Idle => {
                self.state = State::Stopping;
                Ok(Request::Shutdown {})
            }
            State::Active { job_id, .. } => misuse(format!("job {job_id} is still active")),
            State::AwaitingHello => misuse("shutdown before the worker said hello"),
            _ => misuse("shutdown already sent"),
        }
    }

    fn disconnect(&mut self, message: String) -> SessionError {
        self.state = State::Broken;
        SessionError::Disconnected(message)
    }

    /// Validate one worker response against the current state. Any refusal breaks the session.
    pub fn receive(&mut self, response: Response) -> Result<Event, SessionError> {
        if self.state == State::Broken {
            return misuse("the session is broken");
        }
        let state = std::mem::replace(&mut self.state, State::Broken);
        let (next, event) = self
            .transition(state, response)
            .map_err(SessionError::Protocol)?;
        self.state = next;
        Ok(event)
    }

    fn transition(&mut self, state: State, response: Response) -> Result<(State, Event), String> {
        match (state, response) {
            (State::AwaitingHello, Response::Hello { worker_version }) => {
                if worker_version != self.expected_worker_version {
                    return Err(format!(
                        "worker version {worker_version:?}, expected {:?}",
                        self.expected_worker_version
                    ));
                }
                Ok((State::Idle, Event::Ready { worker_version }))
            }
            (State::AwaitingHello, other) => Err(format!("{} before hello", name(&other))),
            (State::Closed, other) => Err(format!("{} after stopped", name(&other))),
            (_, Response::Hello { .. }) => Err("duplicate hello".into()),
            (
                State::Active {
                    job_id,
                    started: false,
                    cancel_requested,
                },
                Response::Started { job_id: reported },
            ) if job_id == reported => Ok((
                State::Active {
                    job_id,
                    started: true,
                    cancel_requested,
                },
                Event::Started { job_id: reported },
            )),
            (
                State::Active {
                    job_id,
                    started: true,
                    ..
                },
                Response::Started { job_id: reported },
            ) if job_id == reported => Err(format!("duplicate started for job {reported}")),
            (
                State::Active {
                    job_id,
                    started,
                    cancel_requested,
                },
                response @ (Response::Completed { .. } | Response::Failed { .. }),
            ) => {
                let (reported, result) = terminal(response);
                if job_id != reported {
                    return Err(format!(
                        "terminal response for job {reported} while job {job_id} is active"
                    ));
                }
                if !started {
                    return Err(format!(
                        "terminal response before started for job {reported}"
                    ));
                }
                let cancelled =
                    matches!(&result, Err(failure) if failure.kind == FailureKind::Cancelled);
                if cancelled && !cancel_requested {
                    return Err(format!(
                        "job {reported} reported an unrequested cancellation"
                    ));
                }
                self.last_finished = Some(reported.clone());
                Ok((
                    State::Idle,
                    Event::Finished(JobFinished {
                        job_id: reported,
                        result,
                        cancel_requested,
                    }),
                ))
            }
            (State::Stopping, Response::Stopped {}) => Ok((State::Closed, Event::Stopped)),
            (State::Idle, response @ (Response::Completed { .. } | Response::Failed { .. })) => {
                let (reported, _) = terminal(response);
                if self.last_finished.as_deref() == Some(reported.as_str()) {
                    Err(format!("duplicate terminal response for job {reported}"))
                } else {
                    Err(format!(
                        "terminal response for job {reported} with no active job"
                    ))
                }
            }
            (State::Active { job_id, .. }, other) => Err(format!(
                "unexpected {} while job {job_id} is active",
                name(&other)
            )),
            (_, other) => Err(format!("unexpected {}", name(&other))),
        }
    }

    /// Record a clean end of stream. Only a closed session may end; otherwise the worker vanished.
    pub fn end_of_stream(&mut self) -> Result<(), SessionError> {
        match self.state {
            State::Closed => Ok(()),
            State::Broken => misuse("the session is broken"),
            _ => {
                let state = format!("{:?}", self.state);
                Err(self.disconnect(format!("end of stream in state {state}")))
            }
        }
    }

    fn lost(&mut self, error: io::Error) -> SessionError {
        match error.kind() {
            io::ErrorKind::InvalidData => {
                self.state = State::Broken;
                SessionError::Protocol(format!("malformed frame: {error}"))
            }
            io::ErrorKind::UnexpectedEof => {
                self.disconnect(format!("stream ended mid-frame: {error}"))
            }
            _ => self.disconnect(error.to_string()),
        }
    }
}

fn terminal(response: Response) -> (String, Result<JobOutputs, WorkerFailure>) {
    match response {
        Response::Completed { job_id, outputs } => (job_id, Ok(outputs)),
        Response::Failed { job_id, failure } => (job_id, Err(failure)),
        _ => unreachable!("only terminal responses reach here"),
    }
}

fn name(response: &Response) -> &'static str {
    match response {
        Response::Hello { .. } => "hello",
        Response::Started { .. } => "started",
        Response::Completed { .. } => "completed",
        Response::Failed { .. } => "failed",
        Response::Stopped {} => "stopped",
    }
}

/// A session over a dedicated framed pipe: `reader` carries worker responses, `writer` requests.
pub struct Channel<R, W> {
    session: Session,
    reader: R,
    writer: W,
}

impl<R: Read, W: Write> Channel<R, W> {
    pub fn new(session: Session, reader: R, writer: W) -> Self {
        Self {
            session,
            reader,
            writer,
        }
    }

    pub fn session(&self) -> &Session {
        &self.session
    }

    /// Send a request the session has just accepted. The frame is built first: one that cannot be
    /// framed was never written, so the session goes back to its previous state. Any write or flush
    /// error afterwards breaks the session, whatever its error kind.
    fn send(&mut self, before: Session, request: Request) -> Result<(), SessionError> {
        let mut frame = Vec::new();
        if let Err(error) = write_frame(&mut frame, &request) {
            self.session = before;
            return misuse(format!("request cannot be framed: {error}"));
        }
        self.writer
            .write_all(&frame)
            .and_then(|()| self.writer.flush())
            .map_err(|error| self.session.disconnect(error.to_string()))
    }

    /// Read and validate the next worker response. `None` is the clean end after `stopped`.
    pub fn next_event(&mut self) -> Result<Option<Event>, SessionError> {
        if self.session.state == State::Broken {
            return misuse("the session is broken");
        }
        match read_frame::<_, Response>(&mut self.reader) {
            Ok(Some(response)) => self.session.receive(response).map(Some),
            Ok(None) => self.session.end_of_stream().map(|()| None),
            Err(error) => Err(self.session.lost(error)),
        }
    }

    fn expect_event(&mut self) -> Result<Event, SessionError> {
        match self.next_event()? {
            Some(event) => Ok(event),
            None => Err(SessionError::Misuse("the session is closed".into())),
        }
    }

    /// Wait for the worker's hello and return its version.
    pub fn handshake(&mut self) -> Result<String, SessionError> {
        if self.session.state != State::AwaitingHello {
            return misuse("handshake already done");
        }
        match self.expect_event()? {
            Event::Ready { worker_version } => Ok(worker_version),
            other => unreachable!("session accepted {other:?} before hello"),
        }
    }

    pub fn start(&mut self, job: JobRequest) -> Result<(), SessionError> {
        let before = self.session.clone();
        let request = self.session.run(job)?;
        self.send(before, request)
    }

    pub fn cancel(&mut self) -> Result<(), SessionError> {
        let before = self.session.clone();
        let request = self.session.cancel()?;
        self.send(before, request)
    }

    /// Run one job to its terminal response without cancelling it.
    pub fn run(&mut self, job: JobRequest) -> Result<JobFinished, SessionError> {
        self.start(job)?;
        loop {
            match self.expect_event()? {
                Event::Started { .. } => {}
                Event::Finished(finished) => return Ok(finished),
                other => unreachable!("session accepted {other:?} during a job"),
            }
        }
    }

    /// Stop an idle worker: `shutdown`, `stopped`, then a clean end of stream.
    pub fn shutdown(&mut self) -> Result<(), SessionError> {
        let before = self.session.clone();
        let request = self.session.shutdown()?;
        self.send(before, request)?;
        match self.expect_event()? {
            Event::Stopped => {}
            other => unreachable!("session accepted {other:?} while stopping"),
        }
        match self.next_event()? {
            None => Ok(()),
            Some(other) => unreachable!("session accepted {other:?} after stopped"),
        }
    }
}
