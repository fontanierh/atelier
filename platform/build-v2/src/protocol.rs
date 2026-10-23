//! A dedicated binary pipe carries these frames; stdout/stderr remain logs.
use crate::schema::{ContentIdentity, Op, OutputFile, Params};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Map, Value};
use std::fmt;
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
/// Decoding is strict: duplicate keys and positional (array) forms of the envelope, the message or
/// any typed record fail, as do unknown fields and versions. Arrays stay legitimate in params and
/// in string lists. This is framing, not a session state machine; C1 validates message ordering.
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
    let StrictValue(document) = serde_json::from_slice(&payload).map_err(invalid)?;
    object_records(&document).map_err(invalid)?;
    let envelope: Envelope<T> = serde_json::from_value(document).map_err(invalid)?;
    if envelope.version != PROTOCOL_VERSION {
        return Err(invalid("unsupported protocol version"));
    }
    Ok(Some(envelope.message))
}

fn object<'a>(value: &'a Value, label: &str) -> Result<&'a Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| format!("{label} must be a JSON object"))
}

/// serde-derived structs and internally tagged enums also accept positional arrays. Every record
/// position of protocol v1 must therefore be an object before serde maps it; missing or mistyped
/// fields are left to serde's own errors.
fn object_records(document: &Value) -> Result<(), String> {
    let envelope = object(document, "envelope")?;
    let Some(message) = envelope.get("message") else {
        return Ok(());
    };
    let message = object(message, "message")?;
    match message.get("type").and_then(Value::as_str) {
        Some("run") => {
            let Some(job) = message.get("job") else {
                return Ok(());
            };
            let job = object(job, "job")?;
            if let Some(op) = job.get("op") {
                object(op, "job.op")?;
            }
            if let Some(Value::Array(inputs)) = job.get("inputs") {
                for input in inputs {
                    if let Some(identity) = object(input, "job.inputs[]")?.get("identity") {
                        object(identity, "job.inputs[].identity")?;
                    }
                }
            }
            if let Some(Value::Array(outputs)) = job.get("outputs") {
                for output in outputs {
                    object(output, "job.outputs[]")?;
                }
            }
        }
        Some("completed") => {
            if let Some(outputs) = message.get("outputs") {
                object(outputs, "completed.outputs")?;
            }
        }
        Some("failed") => {
            if let Some(failure) = message.get("failure") {
                object(failure, "failed.failure")?;
            }
        }
        _ => {}
    }
    Ok(())
}

/// A JSON value that refuses duplicate object keys.
struct StrictValue(Value);

impl<'de> serde::Deserialize<'de> for StrictValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(StrictVisitor).map(StrictValue)
    }
}

struct StrictVisitor;

impl<'de> serde::de::Visitor<'de> for StrictVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }
    fn visit_bool<E>(self, value: bool) -> Result<Value, E> {
        Ok(Value::Bool(value))
    }
    fn visit_i64<E>(self, value: i64) -> Result<Value, E> {
        Ok(value.into())
    }
    fn visit_u64<E>(self, value: u64) -> Result<Value, E> {
        Ok(value.into())
    }
    fn visit_f64<E>(self, value: f64) -> Result<Value, E> {
        Ok(value.into())
    }
    fn visit_str<E>(self, value: &str) -> Result<Value, E> {
        Ok(Value::String(value.into()))
    }
    fn visit_string<E>(self, value: String) -> Result<Value, E> {
        Ok(Value::String(value))
    }
    fn visit_unit<E>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }
    fn visit_seq<A: serde::de::SeqAccess<'de>>(self, mut items: A) -> Result<Value, A::Error> {
        let mut values = Vec::new();
        while let Some(StrictValue(value)) = items.next_element()? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }
    fn visit_map<A: serde::de::MapAccess<'de>>(self, mut entries: A) -> Result<Value, A::Error> {
        let mut object = serde_json::Map::new();
        while let Some(key) = entries.next_key::<String>()? {
            if object.contains_key(&key) {
                return Err(serde::de::Error::custom(format!("duplicate key {key:?}")));
            }
            let StrictValue(value) = entries.next_value()?;
            object.insert(key, value);
        }
        Ok(Value::Object(object))
    }
}
