//! A dedicated binary pipe carries these frames; stdout/stderr remain logs.
use crate::schema::{ContentIdentity, Op, OutputFile, Params};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use std::io::{self, Read, Write};

pub const PROTOCOL_VERSION: u32 = 1;
pub const MAX_FRAME_BYTES: usize = 8 * 1024 * 1024;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope<T> {
    version: u32,
    message: T,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    Run { job: JobRequest },
    Cancel { job_id: String },
    Shutdown {},
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Response {
    Hello {
        worker_version: String,
    },
    Started {
        job_id: String,
    },
    Completed {
        job_id: String,
        outputs: JobOutputs,
    },
    Failed {
        job_id: String,
        failure: WorkerFailure,
    },
    Stopped {},
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JobRequest {
    pub job_id: String,
    pub unit: String,
    pub op: Op,
    /// The empty, staged job folder; never a repository root.
    pub job_dir: String,
    pub script: String,
    pub code: Vec<String>,
    pub inputs: Vec<StagedInput>,
    pub params: Params,
    /// Allowed paths under job_dir/output/, with required/optional status.
    pub outputs: Vec<OutputFile>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StagedInput {
    pub name: String,
    pub path: String,
    pub identity: ContentIdentity,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JobOutputs {
    /// Workers report produced paths, not cache keys or publication success.
    pub files: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkerFailure {
    pub kind: FailureKind,
    pub message: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FailureKind {
    Job,
    Dependency,
    Protocol,
    Crash,
    Cancelled,
    Timeout,
    GuardStop,
}

fn invalid(message: impl ToString) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.to_string())
}

/// Writes u32 big-endian length followed by a UTF-8 JSON envelope, then flushes.
/// Rejected oversized frames write no bytes.
pub fn write_frame<W: Write, T: Serialize>(writer: &mut W, message: &T) -> io::Result<()> {
    let payload = serde_json::to_vec(&Envelope {
        version: PROTOCOL_VERSION,
        message,
    })
    .map_err(invalid)?;
    if payload.len() > MAX_FRAME_BYTES {
        return Err(invalid("frame exceeds maximum length"));
    }
    writer.write_all(&(payload.len() as u32).to_be_bytes())?;
    writer.write_all(&payload)?;
    writer.flush()
}

/// Clean EOF is None only between frames. A partial header/body is an error.
/// This is framing, not a session state machine; C1 validates message ordering.
pub fn read_frame<R: Read, T: DeserializeOwned>(reader: &mut R) -> io::Result<Option<T>> {
    let mut header = [0; 4];
    loop {
        match reader.read(&mut header[..1]) {
            Ok(0) => return Ok(None),
            Ok(_) => break,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
    reader.read_exact(&mut header[1..])?;
    let length = u32::from_be_bytes(header) as usize;
    if length == 0 || length > MAX_FRAME_BYTES {
        return Err(invalid("invalid frame length"));
    }
    let mut payload = vec![0; length];
    reader.read_exact(&mut payload)?;
    let envelope: Envelope<T> = serde_json::from_slice(&payload).map_err(invalid)?;
    if envelope.version != PROTOCOL_VERSION {
        return Err(invalid("unsupported protocol version"));
    }
    Ok(Some(envelope.message))
}
