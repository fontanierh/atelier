use atelier_build_v2::protocol::*;
use std::io::{self, Cursor, Read};

fn raw_frame(payload: &[u8]) -> Vec<u8> {
    let mut bytes = (payload.len() as u32).to_be_bytes().to_vec();
    bytes.extend_from_slice(payload);
    bytes
}

#[test]
fn consecutive_frames_roundtrip_and_clean_eof() {
    let requests = [
        Request::Cancel {
            job_id: "job-1".into(),
        },
        Request::Shutdown {},
    ];
    let mut bytes = vec![];
    for request in &requests {
        write_frame(&mut bytes, request).unwrap();
    }
    let mut reader = Cursor::new(bytes);
    for request in requests {
        assert_eq!(
            read_frame::<_, Request>(&mut reader).unwrap(),
            Some(request)
        );
    }
    assert_eq!(read_frame::<_, Request>(&mut reader).unwrap(), None);
}

#[test]
fn responses_and_failure_classes_roundtrip() {
    let responses = [
        Response::Hello {
            worker_version: "fixture-1".into(),
        },
        Response::Started {
            job_id: "job-1".into(),
        },
        Response::Completed {
            job_id: "job-1".into(),
            outputs: JobOutputs {
                files: vec!["piece.glb".into()],
            },
        },
        Response::Failed {
            job_id: "job-1".into(),
            failure: WorkerFailure {
                kind: FailureKind::Dependency,
                message: "undeclared read".into(),
            },
        },
        Response::Stopped {},
    ];
    for response in responses {
        let mut bytes = vec![];
        write_frame(&mut bytes, &response).unwrap();
        assert_eq!(
            read_frame::<_, Response>(&mut Cursor::new(bytes)).unwrap(),
            Some(response)
        );
    }
    for kind in [
        FailureKind::Job,
        FailureKind::Dependency,
        FailureKind::Protocol,
        FailureKind::Crash,
        FailureKind::Cancelled,
        FailureKind::Timeout,
        FailureKind::GuardStop,
    ] {
        let encoded = serde_json::to_string(&kind).unwrap();
        assert_eq!(serde_json::from_str::<FailureKind>(&encoded).unwrap(), kind);
    }
}

#[test]
fn malformed_frames_fail_closed() {
    let payloads = [
        br#"{"version":2,"message":{"type":"shutdown"}}"#.as_slice(),
        br#"{"version":1,"message":{"type":"unknown"}}"#,
        br#"{"version":1,"message":{"type":"cancel"}}"#,
        br#"{"version":1,"message":{"type":"shutdown","typo":1}}"#,
        br#"{"version":1,"message":{"type":"shutdown"},"typo":1}"#,
        b"not json",
        &[0xff],
    ];
    for payload in payloads {
        assert_eq!(
            read_frame::<_, Request>(&mut Cursor::new(raw_frame(payload)))
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
    }
    for length in [0, MAX_FRAME_BYTES as u32 + 1, u32::MAX] {
        assert_eq!(
            read_frame::<_, Request>(&mut Cursor::new(length.to_be_bytes()))
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
    }
}

#[test]
fn every_partial_header_and_body_fails() {
    let frame = raw_frame(br#"{"version":1,"message":{"type":"shutdown"}}"#);
    for end in 1..frame.len() {
        assert_eq!(
            read_frame::<_, Request>(&mut Cursor::new(&frame[..end]))
                .unwrap_err()
                .kind(),
            io::ErrorKind::UnexpectedEof
        );
    }
}

struct Fragmented<'a> {
    bytes: &'a [u8],
    interrupt: bool,
}
impl Read for Fragmented<'_> {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        if self.interrupt {
            self.interrupt = false;
            return Err(io::ErrorKind::Interrupted.into());
        }
        self.interrupt = true;
        self.bytes.read(&mut buffer[..1])
    }
}

#[test]
fn fragmented_reads_and_interrupts_are_supported() {
    let frame = raw_frame(br#"{"version":1,"message":{"type":"shutdown"}}"#);
    let mut reader = Fragmented {
        bytes: &frame,
        interrupt: true,
    };
    assert_eq!(
        read_frame::<_, Request>(&mut reader).unwrap(),
        Some(Request::Shutdown {})
    );
    assert!(read_frame::<_, Request>(&mut reader).unwrap().is_none());
}

#[test]
fn oversized_writer_does_not_emit_partial_frame() {
    let mut bytes = vec![];
    assert_eq!(
        write_frame(&mut bytes, &"x".repeat(MAX_FRAME_BYTES))
            .unwrap_err()
            .kind(),
        io::ErrorKind::InvalidData
    );
    assert!(bytes.is_empty());
}

#[test]
fn stopped_response_refuses_unknown_fields() {
    let frame = raw_frame(br#"{"version":1,"message":{"type":"stopped","typo":1}}"#);
    assert_eq!(
        read_frame::<_, Response>(&mut Cursor::new(frame))
            .unwrap_err()
            .kind(),
        io::ErrorKind::InvalidData
    );
}
