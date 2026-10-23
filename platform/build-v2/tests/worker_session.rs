use atelier_build_v2::protocol::*;
use atelier_build_v2::schema::{ContentIdentity, Op, OutputFile};
use atelier_build_v2::worker_session::*;
use serde::{Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::fmt::Debug;
use std::io::{self, Cursor, Read, Write};
use std::path::Path;

const VERSION: &str = "fake-worker-1";

fn job(id: &str) -> JobRequest {
    JobRequest {
        job_id: id.into(),
        unit: "fixture/piece".into(),
        op: Op {
            kind: "fixture".into(),
            version: "1".into(),
        },
        job_dir: format!("/jobs/{id}"),
        script: "code/run.py".into(),
        code: vec!["code/run.py".into()],
        inputs: vec![StagedInput {
            name: "shape".into(),
            path: "inputs/shape.json".into(),
            identity: ContentIdentity::Digest {
                digest: "d1".into(),
            },
        }],
        params: Default::default(),
        outputs: vec![
            OutputFile {
                path: "piece.glb".into(),
                install_path: None,
                required: true,
            },
            OutputFile {
                path: "piece.log".into(),
                install_path: None,
                required: false,
            },
        ],
    }
}

fn hello(version: &str) -> Response {
    Response::Hello {
        worker_version: version.into(),
    }
}

fn started(id: &str) -> Response {
    Response::Started { job_id: id.into() }
}

fn completed(id: &str) -> Response {
    Response::Completed {
        job_id: id.into(),
        outputs: JobOutputs {
            files: vec!["piece.glb".into()],
        },
    }
}

fn failed(id: &str, kind: FailureKind) -> Response {
    Response::Failed {
        job_id: id.into(),
        failure: WorkerFailure {
            kind,
            message: "scripted".into(),
        },
    }
}

fn ready() -> Session {
    let mut session = Session::new(VERSION);
    session.receive(hello(VERSION)).unwrap();
    session
}

fn protocol_error(result: Result<Event, SessionError>, needle: &str) {
    match result {
        Err(SessionError::Protocol(message)) => {
            assert!(message.contains(needle), "{message:?} lacks {needle:?}")
        }
        other => panic!("expected a protocol violation containing {needle:?}, got {other:?}"),
    }
}

fn misuse<T: Debug>(result: Result<T, SessionError>) {
    assert!(
        matches!(result, Err(SessionError::Misuse(_))),
        "expected misuse, got {result:?}"
    );
}

#[test]
fn session_round_trip_handshake_jobs_and_shutdown() {
    let mut session = Session::new(VERSION);
    assert_eq!(session.state(), &State::AwaitingHello);
    assert_eq!(
        session.receive(hello(VERSION)).unwrap(),
        Event::Ready {
            worker_version: VERSION.into()
        }
    );
    assert_eq!(
        session.run(job("job-1")).unwrap(),
        Request::Run { job: job("job-1") }
    );
    assert_eq!(
        session.state(),
        &State::Active {
            job_id: "job-1".into(),
            started: false,
            cancel_requested: false
        }
    );
    assert_eq!(
        session.receive(started("job-1")).unwrap(),
        Event::Started {
            job_id: "job-1".into()
        }
    );
    let Event::Finished(first) = session.receive(completed("job-1")).unwrap() else {
        panic!("expected a terminal event")
    };
    assert_eq!(
        first.result,
        Ok(JobOutputs {
            files: vec!["piece.glb".into()]
        })
    );
    assert!(!first.cancel_requested && !first.cancelled());
    session.run(job("job-2")).unwrap();
    session.receive(started("job-2")).unwrap();
    let Event::Finished(second) = session.receive(failed("job-2", FailureKind::Job)).unwrap()
    else {
        panic!("expected a terminal event")
    };
    assert_eq!(second.result.unwrap_err().kind, FailureKind::Job);
    assert_eq!(session.shutdown().unwrap(), Request::Shutdown {});
    assert_eq!(session.state(), &State::Stopping);
    assert_eq!(
        session.receive(Response::Stopped {}).unwrap(),
        Event::Stopped
    );
    assert_eq!(session.state(), &State::Closed);
    session.end_of_stream().unwrap();
}

#[test]
fn handshake_requires_the_expected_version_first() {
    let mut session = Session::new(VERSION);
    misuse(session.run(job("job-1")));
    misuse(session.shutdown());
    assert_eq!(session.state(), &State::AwaitingHello);
    protocol_error(session.receive(hello("fake-worker-0")), "worker version");
    assert_eq!(session.state(), &State::Broken);
    misuse(session.receive(hello(VERSION)));

    let mut early = Session::new(VERSION);
    protocol_error(early.receive(started("job-1")), "started before hello");
    assert_eq!(early.state(), &State::Broken);

    let mut twice = ready();
    protocol_error(twice.receive(hello(VERSION)), "duplicate hello");
}

#[test]
fn wrong_job_ids_and_out_of_order_responses_break_the_session() {
    let cases: Vec<(Vec<Response>, &str)> = vec![
        (vec![started("job-2")], "unexpected started while job job-1"),
        (
            vec![started("job-1"), completed("job-2")],
            "terminal response for job job-2 while job job-1 is active",
        ),
        (
            vec![started("job-1"), failed("job-2", FailureKind::Job)],
            "while job job-1 is active",
        ),
        (vec![completed("job-1")], "before started"),
        (
            vec![started("job-1"), started("job-1")],
            "duplicate started",
        ),
        (
            vec![Response::Stopped {}],
            "unexpected stopped while job job-1",
        ),
    ];
    for (responses, needle) in cases {
        let mut session = ready();
        session.run(job("job-1")).unwrap();
        let (last, earlier) = responses.split_last().unwrap();
        for response in earlier {
            session.receive(response.clone()).unwrap();
        }
        protocol_error(session.receive(last.clone()), needle);
        assert_eq!(session.state(), &State::Broken);
    }

    let mut idle = ready();
    protocol_error(idle.receive(started("job-1")), "unexpected started");
    let mut idle = ready();
    protocol_error(idle.receive(Response::Stopped {}), "unexpected stopped");
    let mut stopping = ready();
    stopping.shutdown().unwrap();
    protocol_error(stopping.receive(completed("job-1")), "unexpected completed");
}

#[test]
fn duplicate_terminal_and_messages_after_stop_fail() {
    for duplicate in [completed("job-1"), failed("job-1", FailureKind::Crash)] {
        let mut session = ready();
        session.run(job("job-1")).unwrap();
        session.receive(started("job-1")).unwrap();
        session.receive(completed("job-1")).unwrap();
        protocol_error(
            session.receive(duplicate),
            "duplicate terminal response for job job-1",
        );
        assert_eq!(session.state(), &State::Broken);
    }

    let mut closed = ready();
    closed.shutdown().unwrap();
    closed.receive(Response::Stopped {}).unwrap();
    protocol_error(
        closed.receive(Response::Stopped {}),
        "stopped after stopped",
    );

    let mut active = ready();
    active.run(job("job-1")).unwrap();
    assert!(matches!(
        active.end_of_stream(),
        Err(SessionError::Disconnected(_))
    ));
    assert_eq!(active.state(), &State::Broken);
    for mut session in [Session::new(VERSION), ready()] {
        assert!(matches!(
            session.end_of_stream(),
            Err(SessionError::Disconnected(_))
        ));
    }
}

#[test]
fn cancellation_is_a_request_until_the_worker_confirms_it() {
    let mut session = ready();
    misuse(session.cancel());
    session.run(job("job-1")).unwrap();
    assert_eq!(
        session.cancel().unwrap(),
        Request::Cancel {
            job_id: "job-1".into()
        }
    );
    misuse(session.cancel());
    session.receive(started("job-1")).unwrap();
    let Event::Finished(raced) = session.receive(completed("job-1")).unwrap() else {
        panic!("expected a terminal event")
    };
    assert!(raced.cancel_requested && !raced.cancelled() && raced.result.is_ok());

    session.run(job("job-2")).unwrap();
    session.receive(started("job-2")).unwrap();
    session.cancel().unwrap();
    let Event::Finished(confirmed) = session
        .receive(failed("job-2", FailureKind::Cancelled))
        .unwrap()
    else {
        panic!("expected a terminal event")
    };
    assert!(confirmed.cancel_requested && confirmed.cancelled());

    session.run(job("job-3")).unwrap();
    session.receive(started("job-3")).unwrap();
    protocol_error(
        session.receive(failed("job-3", FailureKind::Cancelled)),
        "unrequested cancellation",
    );
}

#[test]
fn cancel_before_started_still_requires_started_then_one_terminal() {
    let mut session = ready();
    session.run(job("job-1")).unwrap();
    session.cancel().unwrap();
    // Even a job cancelled before it began owes `started` first.
    protocol_error(
        session
            .clone()
            .receive(failed("job-1", FailureKind::Cancelled)),
        "before started",
    );
    protocol_error(
        session.clone().receive(failed("job-1", FailureKind::Job)),
        "before started",
    );
    session.receive(started("job-1")).unwrap();
    let Event::Finished(finished) = session
        .receive(failed("job-1", FailureKind::Cancelled))
        .unwrap()
    else {
        panic!("expected a terminal event")
    };
    assert!(finished.cancel_requested && finished.cancelled());
    assert_eq!(session.state(), &State::Idle);
}

#[test]
fn one_active_job_and_controller_misuse_leave_the_session_unchanged() {
    let mut session = ready();
    session.run(job("job-1")).unwrap();
    let active = session.state().clone();
    misuse(session.run(job("job-2")));
    misuse(session.shutdown());
    assert_eq!(session.state(), &active);
    session.receive(started("job-1")).unwrap();
    session.receive(completed("job-1")).unwrap();
    misuse(session.run(job("job-1")));

    let mut bad = vec![];
    let mut empty_id = job("job-x");
    empty_id.job_id.clear();
    bad.push(empty_id);
    for (field, value) in [
        ("script", "/checkout/code/run.py"),
        ("code", "../code/run.py"),
        ("input", "inputs/../../source.json"),
        ("output", ""),
        ("output", "out//piece.glb"),
        ("output", "out\\piece.glb"),
        ("input", "./inputs/shape.json"),
    ] {
        let mut request = job("job-x");
        match field {
            "script" => request.script = value.into(),
            "code" => request.code.push(value.into()),
            "input" => request.inputs[0].path = value.into(),
            _ => request.outputs[0].path = value.into(),
        }
        bad.push(request);
    }
    for request in bad {
        misuse(session.run(request));
        assert_eq!(session.state(), &State::Idle);
    }

    // Explicit job-relative names pass through exactly: no renaming or Unicode normalisation.
    let mut exact = job("job-2");
    exact.script = "code/Été.py".into();
    exact.code = vec!["code/Été.py".into(), "code/e\u{301}te.py".into()];
    exact.inputs[0].path = "inputs/Shape.JSON".into();
    exact.outputs[0].install_path = Some("out/piece.glb".into());
    assert_eq!(
        session.run(exact.clone()).unwrap(),
        Request::Run { job: exact }
    );
}

struct OneByte<'a> {
    bytes: &'a [u8],
    interrupt: bool,
}

impl Read for OneByte<'_> {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        self.interrupt = !self.interrupt;
        if self.interrupt {
            return Err(io::ErrorKind::Interrupted.into());
        }
        let end = buffer.len().min(1);
        self.bytes.read(&mut buffer[..end])
    }
}

fn frames(responses: &[Response]) -> Vec<u8> {
    let mut bytes = vec![];
    for response in responses {
        write_frame(&mut bytes, response).unwrap();
    }
    bytes
}

fn header_and(payload: &[u8], length: u32) -> Vec<u8> {
    let mut bytes = length.to_be_bytes().to_vec();
    bytes.extend_from_slice(payload);
    bytes
}

#[test]
fn channel_turns_framing_faults_into_session_failures() {
    // A whole conversation delivered one byte at a time, with interrupts, succeeds.
    let script = frames(&[
        hello(VERSION),
        started("job-1"),
        completed("job-1"),
        Response::Stopped {},
    ]);
    let mut requests = vec![];
    let mut channel = Channel::new(
        Session::new(VERSION),
        OneByte {
            bytes: &script,
            interrupt: false,
        },
        &mut requests,
    );
    assert_eq!(channel.handshake().unwrap(), VERSION);
    assert!(channel.run(job("job-1")).unwrap().result.is_ok());
    channel.shutdown().unwrap();
    assert_eq!(channel.session().state(), &State::Closed);
    let mut sent = Cursor::new(requests);
    assert_eq!(
        read_frame::<_, Request>(&mut sent).unwrap(),
        Some(Request::Run { job: job("job-1") })
    );
    assert_eq!(
        read_frame::<_, Request>(&mut sent).unwrap(),
        Some(Request::Shutdown {})
    );
    assert_eq!(read_frame::<_, Request>(&mut sent).unwrap(), None);

    let ready_frame = frames(&[hello(VERSION)]);
    let started_payload = br#"{"version":1,"message":{"type":"started","job_id":"job-1"}}"#;
    let mut truncated_header = ready_frame.clone();
    truncated_header.extend_from_slice(&[0, 0]);
    let mut truncated_body = ready_frame.clone();
    truncated_body.extend(header_and(
        &started_payload[..10],
        started_payload.len() as u32,
    ));
    let mut oversize = ready_frame.clone();
    oversize.extend((MAX_FRAME_BYTES as u32 + 1).to_be_bytes());
    let mut unknown_field = ready_frame.clone();
    let typo = br#"{"version":1,"message":{"type":"started","job_id":"job-1","pid":1}}"#;
    unknown_field.extend(header_and(typo, typo.len() as u32));
    let mut wrong_version = ready_frame.clone();
    let future = br#"{"version":2,"message":{"type":"started","job_id":"job-1"}}"#;
    wrong_version.extend(header_and(future, future.len() as u32));
    // A positional `failure` record is a malformed frame.
    let mut positional = frames(&[hello(VERSION), started("job-1")]);
    let record =
        br#"{"version":1,"message":{"type":"failed","job_id":"job-1","failure":["job","m"]}}"#;
    positional.extend(header_and(record, record.len() as u32));
    // So are a positional envelope and a duplicated field.
    let mut positional_envelope = vec![];
    let array = br#"[1,{"type":"hello","worker_version":"fake-worker-1"}]"#;
    positional_envelope.extend(header_and(array, array.len() as u32));
    let mut duplicate = ready_frame.clone();
    let twice = br#"{"version":1,"message":{"type":"started","job_id":"other","job_id":"job-1"}}"#;
    duplicate.extend(header_and(twice, twice.len() as u32));
    let mut hidden = Channel::new(
        Session::new(VERSION),
        Cursor::new(positional_envelope),
        io::sink(),
    );
    assert!(matches!(hidden.handshake(), Err(SessionError::Protocol(_))));
    assert_eq!(hidden.session().state(), &State::Broken);
    // (bytes, whether the worker broke the protocol rather than losing the pipe)
    let cases = [
        (duplicate, true),
        (positional, true),
        (ready_frame.clone(), false),
        (truncated_header, false),
        (truncated_body, false),
        (oversize, true),
        (unknown_field, true),
        (wrong_version, true),
    ];
    for (bytes, violation) in cases {
        let mut channel = Channel::new(Session::new(VERSION), Cursor::new(bytes), io::sink());
        channel.handshake().unwrap();
        let error = channel.run(job("job-1")).unwrap_err();
        if violation {
            assert!(matches!(error, SessionError::Protocol(_)), "{error:?}");
        } else {
            assert!(matches!(error, SessionError::Disconnected(_)), "{error:?}");
        }
        assert_eq!(channel.session().state(), &State::Broken);
        misuse(channel.next_event());
    }
    let mut silent = Channel::new(Session::new(VERSION), io::empty(), io::sink());
    assert!(matches!(
        silent.handshake(),
        Err(SessionError::Disconnected(_))
    ));
}

/// Accepts every byte, then fails to flush with a data error.
struct FlushFails;

impl Write for FlushFails {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Err(io::ErrorKind::InvalidData.into())
    }
}

struct BrokenPipe;

impl Write for BrokenPipe {
    fn write(&mut self, _: &[u8]) -> io::Result<usize> {
        Err(io::ErrorKind::BrokenPipe.into())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn unframeable_requests_are_not_sent_and_write_failures_break_the_session() {
    let mut requests = vec![];
    let mut channel = Channel::new(
        Session::new(VERSION),
        Cursor::new(frames(&[hello(VERSION)])),
        &mut requests,
    );
    channel.handshake().unwrap();
    let mut huge = job("job-1");
    huge.params
        .insert("blob".into(), json!("x".repeat(MAX_FRAME_BYTES)));
    misuse(channel.start(huge));
    assert_eq!(channel.session().state(), &State::Idle);
    // Nothing reached the worker, so the same job ID remains available.
    channel.start(job("job-1")).unwrap();
    drop(channel);
    assert_eq!(
        read_frame::<_, Request>(&mut Cursor::new(requests)).unwrap(),
        Some(Request::Run { job: job("job-1") })
    );

    let mut broken = Channel::new(
        Session::new(VERSION),
        Cursor::new(frames(&[hello(VERSION)])),
        BrokenPipe,
    );
    broken.handshake().unwrap();
    assert!(matches!(
        broken.start(job("job-1")),
        Err(SessionError::Disconnected(_))
    ));
    assert_eq!(broken.session().state(), &State::Broken);

    // A writer error of any kind after the frame was handed over breaks the session, so a second
    // job can never start while the first may still be running.
    let mut flaky = Channel::new(
        Session::new(VERSION),
        Cursor::new(frames(&[hello(VERSION)])),
        FlushFails,
    );
    flaky.handshake().unwrap();
    assert!(matches!(
        flaky.start(job("job-1")),
        Err(SessionError::Disconnected(_))
    ));
    assert_eq!(flaky.session().state(), &State::Broken);
    misuse(flaky.start(job("job-2")));
}

fn vector_bytes(vector: &Value) -> Vec<u8> {
    chunk_bytes(&vector["chunks"])
}

fn chunk_bytes(chunks: &Value) -> Vec<u8> {
    let mut bytes = vec![];
    for chunk in chunks.as_array().unwrap() {
        if let Some(hex) = chunk.get("hex") {
            let hex = hex.as_str().unwrap();
            for index in (0..hex.len()).step_by(2) {
                bytes.push(u8::from_str_radix(&hex[index..index + 2], 16).unwrap());
            }
        } else {
            bytes.extend_from_slice(chunk["text"].as_str().unwrap().as_bytes());
        }
    }
    bytes
}

fn check_vector<T: DeserializeOwned + Serialize + PartialEq + Debug>(vector: &Value) {
    let name = vector["name"].as_str().unwrap();
    let bytes = vector_bytes(vector);
    let expected: Vec<T> = vector["messages"]
        .as_array()
        .unwrap()
        .iter()
        .map(|message| serde_json::from_value(message.clone()).unwrap())
        .collect();
    let opaque = vector
        .get("opaque_messages")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    let canonical = vector["canonical"].as_bool().unwrap();
    assert!(opaque == 0 || canonical, "{name}");
    let readers: [Box<dyn Read + '_>; 2] = [
        Box::new(Cursor::new(&bytes)),
        Box::new(OneByte {
            bytes: &bytes,
            interrupt: false,
        }),
    ];
    for mut reader in readers {
        let mut decoded = vec![];
        for _ in 0..expected.len() + opaque {
            decoded.push(
                read_frame::<_, T>(&mut reader)
                    .unwrap_or_else(|error| panic!("{name}: {error}"))
                    .unwrap_or_else(|| panic!("{name}: early end")),
            );
        }
        assert_eq!(decoded[..expected.len()], expected[..], "{name}");
        let end = read_frame::<_, T>(&mut reader);
        match vector["error"].as_str() {
            None => assert!(matches!(end, Ok(None)), "{name}: {end:?}"),
            Some(kind) => {
                let wanted = match kind {
                    "invalid" => io::ErrorKind::InvalidData,
                    "truncated" => io::ErrorKind::UnexpectedEof,
                    other => panic!("{name}: unknown error class {other}"),
                };
                match end {
                    Err(error) => assert_eq!(error.kind(), wanted, "{name}: {error}"),
                    Ok(message) => panic!("{name}: Rust accepted {message:?}"),
                }
            }
        }
        let mut encoded = vec![];
        for message in &decoded {
            write_frame(&mut encoded, message).unwrap();
        }
        if canonical {
            assert_eq!(encoded, bytes, "{name}: Rust encoding differs");
        }
        if let Some(reencoded) = vector.get("reencoded") {
            assert_eq!(
                encoded,
                chunk_bytes(reencoded),
                "{name}: Rust re-encoding differs"
            );
        }
    }
}

#[test]
fn shared_vectors_decode_and_encode_like_python() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/vectors/protocol_v1.json");
    let document: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
    let vectors = document["vectors"].as_array().unwrap();
    assert!(vectors.len() > 40);
    for vector in vectors {
        match vector["kind"].as_str().unwrap() {
            "request" => check_vector::<Request>(vector),
            "response" => check_vector::<Response>(vector),
            other => panic!("unknown vector kind {other}"),
        }
    }
}

mod python_worker {
    use super::*;
    use std::ffi::c_int;
    use std::io::{PipeReader, PipeWriter};
    use std::os::fd::AsRawFd;
    use std::os::unix::process::CommandExt;
    use std::process::{Command, ExitStatus, Stdio};
    use std::sync::mpsc;
    use std::thread;
    use std::time::{Duration, Instant};

    unsafe extern "C" {
        fn fcntl(fd: c_int, command: c_int, ...) -> c_int;
    }
    const F_SETFD: c_int = 2;
    /// One bound for the whole worker lifetime; the tests never sleep.
    const LIMIT: Duration = Duration::from_secs(5);

    pub struct Worker {
        channel: Option<Channel<PipeReader, PipeWriter>>,
        watchdog: thread::JoinHandle<(bool, ExitStatus, [Vec<u8>; 2])>,
    }

    pub struct Exit {
        pub status: ExitStatus,
        pub stdout: String,
        pub stderr: String,
    }

    /// Start the Python fixture with its protocol pipe on two inherited descriptors and its
    /// stdout/stderr captured separately as logs. A watchdog kills it if it outlives LIMIT.
    pub fn spawn(scenario: &str) -> Worker {
        let (request_reader, request_writer) = io::pipe().unwrap();
        let (response_reader, response_writer) = io::pipe().unwrap();
        let inherited = [request_reader.as_raw_fd(), response_writer.as_raw_fd()];
        let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/fake_worker.py");
        let mut command = Command::new("python3");
        command
            .arg(script)
            .arg(scenario)
            .arg(inherited[0].to_string())
            .arg(inherited[1].to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        // SAFETY: between fork and exec this only calls fcntl, which is async-signal-safe, to
        // clear close-on-exec on the child's two protocol descriptors.
        unsafe {
            command.pre_exec(move || {
                for fd in inherited {
                    if fcntl(fd, F_SETFD, 0) == -1 {
                        return Err(io::Error::last_os_error());
                    }
                }
                Ok(())
            });
        }
        let mut child = command.spawn().expect("python3 runs the worker fixture");
        drop(request_reader);
        drop(response_writer);
        let (logs, collected) = mpsc::channel();
        collect(0, child.stdout.take().unwrap(), logs.clone());
        collect(1, child.stderr.take().unwrap(), logs);
        let watchdog = thread::spawn(move || {
            let deadline = Instant::now() + LIMIT;
            let mut output = [vec![], vec![]];
            let mut expired = false;
            for _ in 0..2 {
                match collected.recv_timeout(deadline.saturating_duration_since(Instant::now())) {
                    Ok((index, bytes)) => output[index] = bytes,
                    Err(_) => {
                        expired = true;
                        let _ = child.kill();
                        break;
                    }
                }
            }
            (expired, child.wait().unwrap(), output)
        });
        Worker {
            channel: Some(Channel::new(
                Session::new(VERSION),
                response_reader,
                request_writer,
            )),
            watchdog,
        }
    }

    fn collect(
        index: usize,
        mut stream: impl Read + Send + 'static,
        logs: mpsc::Sender<(usize, Vec<u8>)>,
    ) {
        thread::spawn(move || {
            let mut bytes = vec![];
            let _ = stream.read_to_end(&mut bytes);
            let _ = logs.send((index, bytes));
        });
    }

    impl Worker {
        pub fn channel(&mut self) -> &mut Channel<PipeReader, PipeWriter> {
            self.channel.as_mut().unwrap()
        }

        /// Close the controller's pipe ends and collect the exit within the same bound.
        pub fn finish(mut self) -> Exit {
            drop(self.channel.take());
            let (expired, status, [stdout, stderr]) = self.watchdog.join().unwrap();
            assert!(!expired, "the Python worker outlived {LIMIT:?}");
            Exit {
                status,
                stdout: String::from_utf8(stdout).unwrap(),
                stderr: String::from_utf8(stderr).unwrap(),
            }
        }
    }
}

#[test]
fn python_worker_round_trip_over_dedicated_pipes() {
    let mut worker = python_worker::spawn("normal");
    let channel = worker.channel();
    assert_eq!(channel.handshake().unwrap(), VERSION);
    let mut first = job("job-1");
    first
        .params
        .insert("label".into(), json!("ünï ☕ 𝄞 \"q\" \\ \n\t\u{1}"));
    first.params.insert(
        "limits".into(),
        json!({"max": u64::MAX, "min": i64::MIN, "flags": [true, null]}),
    );
    first.params.insert(
        "floats".into(),
        json!([1e-7, 0.00001, 1e16, 1e15, 1.5e300, 0.1, -2.5e-10]),
    );
    first.outputs[0].install_path = Some("out/piece.glb".into());
    let finished = channel.run(first).unwrap();
    // The worker answers `failed` if its own encoding of the request differs from Rust's bytes.
    assert_eq!(
        finished.result,
        Ok(JobOutputs {
            files: vec!["piece.glb".into()]
        })
    );
    let mut second = job("job-2");
    second
        .params
        .insert("fixture".into(), json!("await_cancel"));
    channel.start(second).unwrap();
    assert_eq!(
        channel.next_event().unwrap(),
        Some(Event::Started {
            job_id: "job-2".into()
        })
    );
    channel.cancel().unwrap();
    let Some(Event::Finished(cancelled)) = channel.next_event().unwrap() else {
        panic!("expected a terminal event")
    };
    assert!(cancelled.cancel_requested && cancelled.cancelled());
    channel.shutdown().unwrap();
    assert_eq!(channel.session().state(), &State::Closed);
    let exit = worker.finish();
    assert!(exit.status.success(), "{}", exit.stderr);
    assert!(exit.stdout.contains("job job-1 started") && exit.stdout.contains("job job-2 started"));
    assert!(exit.stderr.contains("job job-1 log on stderr"));
}

#[test]
fn python_worker_faults_break_the_session_over_dedicated_pipes() {
    let cases = [
        ("wrong_version", "worker version", Some(0)),
        ("unknown_field_hello", "malformed frame", Some(0)),
        ("oversize_hello", "malformed frame", Some(0)),
        ("wrong_job_id", "unexpected started", Some(0)),
        ("terminal_before_started", "before started", Some(0)),
        ("duplicate_terminal", "duplicate terminal", Some(0)),
        ("truncated_body", "mid-frame", Some(0)),
        ("exit_mid_job", "end of stream", Some(3)),
    ];
    for (scenario, needle, code) in cases {
        let mut worker = python_worker::spawn(scenario);
        let channel = worker.channel();
        let error = channel
            .handshake()
            .and_then(|_| channel.run(job("job-1")))
            .and_then(|_| channel.next_event())
            .expect_err(scenario);
        let message = error.to_string();
        assert!(message.contains(needle), "{scenario}: {message}");
        assert_eq!(channel.session().state(), &State::Broken, "{scenario}");
        let exit = worker.finish();
        assert_eq!(exit.status.code(), code, "{scenario}: {}", exit.stderr);
    }
}
