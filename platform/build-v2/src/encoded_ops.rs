//! Lossless selected encoded-GLB publication through the existing Python executor.
use crate::keys::{ImplementationIdentity, PreparedUnit, canonical_bytes};
use crate::results::FrozenOutput;
use crate::schema::{Destination, InputKind};
use crate::source_hashes::sha256;
use crate::validate::{
    InputRole, InputRule, OpDefinition, OpRegistry, ParamKind, ParamRule, SnapshotEntry,
    SourceSnapshot,
};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;

pub const KIND: &str = "encoded_export_piece";
pub const CODE: [&str; 5] = [
    "platform/studio/atelier/encoded_glb.py",
    "platform/studio/atelier/gltf.py",
    "platform/studio/atelier/gltf_partition.py",
    "platform/studio/atelier/export_manifest.py",
    "platform/studio/atelier/model_files.py",
];
pub fn identity_from_code(
    code: &BTreeMap<String, String>,
) -> Result<ImplementationIdentity, String> {
    let files = CODE
        .into_iter()
        .map(|name| {
            code.get(name)
                .map(|hash| (name, hash))
                .ok_or("encoded decoder code missing")
        })
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    Ok(ImplementationIdentity {
        version: "encoded-piece-validator-1".into(),
        digest: sha256(&canonical_bytes(&files)?),
    })
}
pub fn identity(snapshot: &SourceSnapshot) -> Result<ImplementationIdentity, String> {
    let code = CODE
        .into_iter()
        .map(|name| match snapshot.get(name) {
            Some(SnapshotEntry::File(bytes)) => Ok((name.into(), sha256(bytes))),
            _ => Err("encoded decoder source missing"),
        })
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    identity_from_code(&code)
}
pub fn register(registry: &mut OpRegistry) {
    let inputs = BTreeMap::from([(
        "payload".into(),
        InputRule {
            role: InputRole::Content,
            required: true,
            allow_absent_file: false,
            allow_selector: false,
            require_whole_reason: false,
            item_classes: BTreeSet::from(["GeometryPayload".into()]),
        },
    )]);
    let params = ["payload_member", "payload_encoding", "payload_role"]
        .into_iter()
        .map(|name| {
            (
                name.into(),
                ParamRule {
                    kind: ParamKind::String,
                    required: true,
                },
            )
        })
        .collect();
    registry.insert(
        (KIND.into(), "1".into()),
        OpDefinition {
            inputs,
            params,
            output_classes: BTreeSet::from(["StaticMeshSource".into()]),
        },
    );
}
pub fn check(unit: &PreparedUnit) -> Result<(), String> {
    let i = unit.ingredients();
    let validator = identity_from_code(&i.code)?;
    if i.op.kind != KIND
        || i.op.version != "1"
        || i.validator_version != validator.version
        || i.validator_digest != validator.digest
        || i.worker_version != crate::launch::PYTHON_JOB_LOOP_VERSION
        || i.content.len() != 1
        || !i.content.contains_key("payload")
        || !i.references.is_empty()
        || !i.output_groups.is_empty()
        || i.input_kinds.get("payload") != Some(&InputKind::Item)
        || i.params.get("payload_encoding").and_then(Value::as_str) != Some("encoded_glb")
        || !matches!(
            i.params.get("payload_role").and_then(Value::as_str),
            Some("render" | "collision")
        )
        || i.logical_outputs.len() != 1
    {
        return Err("unsupported encoded piece identity".into());
    }
    let payload = crate::blender_ops::selected_payload(unit)?;
    let piece = payload
        .path
        .strip_suffix(".mesh")
        .ok_or("encoded payload must be one .mesh member")?;
    crate::groups::name(piece)?;
    let item = &i.logical_outputs[0];
    if item.class != "StaticMeshSource"
        || item.destination != Destination::Store
        || item.files.len() != 2
        || item
            .files
            .iter()
            .any(|f| !f.required || f.install_path.is_some())
        || !item.files.iter().any(|f| f.path == format!("{piece}.glb"))
        || !item.files.iter().any(|f| f.path == "export.json")
    {
        return Err("encoded piece must own exactly its GLB and receipt".into());
    }
    Ok(())
}
pub fn validate_outputs(
    unit: &PreparedUnit,
    outputs: &[FrozenOutput<'_>],
    staged: &crate::staging::StagedJob,
) -> Result<(), String> {
    check(unit)?;
    let i = unit.ingredients();
    let item = &i.logical_outputs[0];
    let payload = crate::blender_ops::selected_payload(unit)?;
    let piece = payload
        .path
        .strip_suffix(".mesh")
        .ok_or("invalid encoded member")?;
    if outputs.len() != 2
        || outputs.iter().any(|o| {
            o.item != item || crate::keys::normalized_mode(o.object.source_mode()) != 0o644
        })
    {
        return Err("incomplete encoded frozen outputs".into());
    }
    let primary = outputs
        .iter()
        .find(|o| o.path == format!("{piece}.glb"))
        .ok_or("missing encoded GLB")?;
    let receipt = outputs
        .iter()
        .find(|o| o.path == "export.json")
        .ok_or("missing encoded receipt")?;
    if !(20..=64 * 1024 * 1024).contains(&primary.object.size())
        || receipt.object.size() > 1024 * 1024
    {
        return Err("encoded output bound exceeded".into());
    }
    let mut header = [0u8; 12];
    primary
        .object
        .reader()
        .map_err(|e| e.to_string())?
        .read_exact(&mut header)
        .map_err(|e| e.to_string())?;
    if &header[..4] != b"glTF"
        || u32::from_le_bytes(header[4..8].try_into().unwrap()) != 2
        || u32::from_le_bytes(header[8..12].try_into().unwrap()) as u64 != primary.object.size()
    {
        return Err("invalid GLB framing".into());
    }
    let mut raw = Vec::new();
    receipt
        .object
        .reader()
        .map_err(|e| e.to_string())?
        .take(1024 * 1024 + 1)
        .read_to_end(&mut raw)
        .map_err(|e| e.to_string())?;
    crate::py_data::validate_py_data_payload("JsonData", "export.json", &raw)?;
    let value: Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    let hash = primary.object.digest().as_hex();
    let packet_identity = validate_selected_packet(unit, staged, hash)?;
    if value["triangles"] != packet_identity["triangles"]
        || value["bounds"] != packet_identity["bounds"]
    {
        return Err("encoded frozen geometry facts differ from actual selected packet".into());
    }
    validate_receipt(
        &value,
        piece,
        primary.path,
        hash,
        &payload.digest,
        i.params["payload_role"]
            .as_str()
            .ok_or("missing encoded role")?,
    )
}

/// @cc [owner:fontanierh,label:correctness] encoded-selected-packet-frozen-publication
/// A frozen encoded export MUST retain its exact GLB identity and a receipt bound to
/// the selected packet digest, asset, role and complete bounded geometry facts.
/// Neither a planner key nor a sibling's digest may certify this member.
pub fn validate_receipt(
    value: &Value,
    piece: &str,
    primary: &str,
    hash: &str,
    payload: &str,
    role: &str,
) -> Result<(), String> {
    if value["schema"] != 1
        || value["asset"] != piece
        || value["primary"] != primary
        || value["sha256"] != hash
        || value["metadata"]["geometry_sha256"] != hash
        || value["metadata"]["payload_sha256"] != payload
        || value["metadata"]["role"] != role
        || !value["triangles"]
            .as_u64()
            .is_some_and(|n| n > 0 && n <= 32768)
        || !value["bounds"].as_array().is_some_and(|rows| {
            rows.len() == 2
                && rows.iter().all(|row| {
                    row.as_array().is_some_and(|r| {
                        r.len() == 3 && r.iter().all(|v| v.as_f64().is_some_and(f64::is_finite))
                    })
                })
        })
    {
        return Err("encoded receipt differs from selected packet or frozen GLB".into());
    }
    Ok(())
}

fn validate_selected_packet(
    unit: &PreparedUnit,
    staged: &crate::staging::StagedJob,
    expected_glb: &str,
) -> Result<Value, String> {
    use sha2::{Digest, Sha256};
    use std::fs::OpenOptions;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    let payload = crate::blender_ops::selected_payload(unit)?;
    let input = unit
        .inputs()
        .iter()
        .find(|i| i.wire.name == "payload")
        .ok_or("missing selected packet slot")?;
    let path = staged.job_dir().join(&input.wire.path).join(&payload.path);
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&path)
        .map_err(|e| e.to_string())?;
    let before = file.metadata().map_err(|e| e.to_string())?;
    if !before.is_file() || before.len() != payload.size || before.len() > 66 * 1024 * 1024 {
        return Err("selected packet changed or exceeds bound".into());
    }
    const MAGIC: &[u8] = b"ATELIER-STATIC-MESH-1\0";
    let mut prefix = vec![0; MAGIC.len() + 4];
    file.read_exact(&mut prefix).map_err(|e| e.to_string())?;
    if &prefix[..MAGIC.len()] != MAGIC {
        return Err("selected packet has invalid framing".into());
    }
    let size = u32::from_le_bytes(prefix[MAGIC.len()..].try_into().unwrap()) as usize;
    if size == 0 || size > 1024 * 1024 {
        return Err("selected packet header bound exceeded".into());
    }
    let mut raw = vec![0; size];
    file.read_exact(&mut raw).map_err(|e| e.to_string())?;
    crate::py_data::validate_py_data_payload("JsonData", "encoded header", &raw)?;
    let identity: Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    let piece = payload
        .path
        .strip_suffix(".mesh")
        .ok_or("invalid packet extension")?;
    if identity["schema"] != 1
        || identity["asset"] != piece
        || identity["role"] != unit.ingredients().params["payload_role"]
        || identity["sha256"] != expected_glb
    {
        return Err("selected packet header differs from frozen GLB identity".into());
    }
    let mut packet_hash = Sha256::new();
    packet_hash.update(&prefix);
    packet_hash.update(&raw);
    let mut glb_hash = Sha256::new();
    let mut count = (prefix.len() + raw.len()) as u64;
    let mut buffer = [0u8; 65536];
    loop {
        let n = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        packet_hash.update(&buffer[..n]);
        glb_hash.update(&buffer[..n]);
        count += n as u64;
    }
    let after = file.metadata().map_err(|e| e.to_string())?;
    let named = std::fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    let state = |m: &std::fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    };
    if state(&before) != state(&after)
        || state(&after) != state(&named)
        || count != payload.size
        || format!("{:x}", packet_hash.finalize()) != payload.digest
        || format!("{:x}", glb_hash.finalize()) != expected_glb
    {
        return Err("selected packet or exact original GLB bytes changed".into());
    }
    Ok(identity)
}
