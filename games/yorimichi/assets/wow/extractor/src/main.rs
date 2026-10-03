//! Offline, read-only vanilla extraction. The game never depends on this Rust binary.
#![recursion_limit = "256"]
mod models;
mod spells;
mod world;

use anyhow::{bail, Context, Result};
use benilla_formats::Chain;
use clap::{Parser, Subcommand};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, VecDeque};
use std::io::{Cursor, Write};
use std::path::{Component, Path, PathBuf};

const REVISION: &str = "b396bbf69a0486b6d29829ec191145f63c363eea";

#[derive(Parser)]
#[command(about = "Export local WoW 1.12.1 assets into engine-independent data")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Inventory {
        data: PathBuf,
        output: PathBuf,
    },
    Pack {
        data: PathBuf,
        plan: PathBuf,
        output: PathBuf,
    },
    /// Decode one loose source file; also useful for fixtures independent of a retail install.
    Convert {
        input: PathBuf,
        output: PathBuf,
    },
}

#[derive(Deserialize)]
struct Plan {
    schema_version: u32,
    seeds: Vec<String>,
    #[serde(default)]
    prefixes: Vec<String>,
    #[serde(default)]
    world: Option<WorldSelection>,
    spell_family: u32,
    class_id: u32,
    level: u32,
    max_assets: usize,
}

#[derive(Deserialize)]
struct WorldSelection {
    map: String,
    center_yards: [f32; 2],
    tile_radius: u32,
}

fn normalize(name: &str) -> Result<String> {
    let s = name.replace('\\', "/").to_ascii_lowercase();
    if s.is_empty() || s.contains(':') || s.as_bytes().contains(&0) {
        bail!("invalid archive path");
    }
    if Path::new(&s)
        .components()
        .any(|c| !matches!(c, Component::Normal(_)))
    {
        bail!("unsafe archive path: {s}");
    }
    Ok(s)
}

fn model_path(name: &str) -> String {
    let lower = name.to_ascii_lowercase();
    if lower.ends_with(".mdx") || lower.ends_with(".mdl") {
        format!("{}.m2", &name[..name.len() - 4])
    } else {
        name.into()
    }
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn write_bytes(path: &Path, bytes: &[u8]) -> Result<()> {
    std::fs::create_dir_all(path.parent().context("output has no parent")?)?;
    // A failed decode must never publish a truncated result. One writer owns an output folder.
    let temporary = path.with_extension(format!(
        "{}.partial",
        path.extension().unwrap_or_default().to_string_lossy()
    ));
    let mut f = std::fs::File::create(&temporary)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    std::fs::rename(temporary, path)?;
    Ok(())
}

fn write_json(path: &Path, value: &Value) -> Result<()> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    write_bytes(path, &bytes)
}

/// Decoding preserves raw WoW axes and yards. No Unreal or Blender transforms are applied.
fn decode(
    name: &str,
    bytes: &[u8],
    output: &Path,
) -> Result<(Option<String>, Vec<String>, Vec<String>)> {
    let extension = Path::new(name)
        .extension()
        .unwrap_or_default()
        .to_string_lossy();
    let mut dependencies = Vec::new();
    let mut warnings = Vec::new();
    let destination = format!("decoded/{name}.json");
    let value = match extension.as_ref() {
        "m2" => {
            let (value, refs) = models::decode(bytes)?;
            dependencies.extend(refs);
            value
        }
        "wmo" => {
            let (value, refs) = world::wmo(name, bytes)?;
            dependencies.extend(refs);
            value
        }
        "adt" => {
            let (value, refs) = world::adt(bytes)?;
            dependencies.extend(refs);
            value
        }
        "blp" => {
            let decoded = benilla_blp::decode(bytes).map_err(|e| anyhow::anyhow!("BLP: {e}"))?;
            let mip = decoded.mips.first().context("BLP has no mip")?;
            let destination = format!("decoded/{name}.png");
            let image = image::RgbaImage::from_raw(mip.width, mip.height, mip.rgba.clone())
                .context("invalid BLP pixels")?;
            let mut encoded = Cursor::new(Vec::new());
            image.write_to(&mut encoded, image::ImageFormat::Png)?;
            write_bytes(&output.join(&destination), &encoded.into_inner())?;
            return Ok((Some(destination), dependencies, warnings));
        }
        "dbc" => {
            let destination = format!("decoded/{name}.csv");
            let target = output.join(&destination);
            std::fs::create_dir_all(target.parent().unwrap())?;
            // Use conventional names for the familiar seeded tables; unsupported schemas
            // remain raw rather than being interpreted with guessed column types.
            let original = dbc_name(name);
            match benilla_formats::dbc_to_csv(bytes, &original, &target) {
                Ok(_) => return Ok((Some(destination), dependencies, warnings)),
                Err(e) if e.to_string().starts_with("no schema defined") => {
                    warnings.push("No typed CSV schema; lossless raw DBC retained".into());
                    return Ok((None, dependencies, warnings));
                }
                Err(e) => return Err(e),
            }
        }
        _ => return Ok((None, dependencies, warnings)),
    };
    write_json(&output.join(&destination), &value)?;
    Ok((Some(destination), dependencies, warnings))
}

fn dbc_name(name: &str) -> String {
    // The complete original spelling is passed via the inventory where possible. This list
    // covers explicit seeds that may be absent from MPQ listfiles.
    const NAMES: &[&str] = &[
        "Spell",
        "SpellIcon",
        "SpellRange",
        "SpellCastTimes",
        "SpellDuration",
        "SpellRadius",
        "SpellVisual",
        "SpellVisualKit",
        "SpellVisualEffectName",
        "SkillLine",
        "SkillLineAbility",
        "ChrClasses",
        "ChrRaces",
        "CharSections",
        "CharHairGeosets",
        "CharacterFacialHairStyles",
        "CharStartOutfit",
        "CreatureDisplayInfo",
        "CreatureDisplayInfoExtra",
        "CreatureModelData",
        "ItemDisplayInfo",
        "ItemClass",
        "ItemSubClass",
        "ItemSet",
        "ItemVisuals",
        "ItemVisualEffects",
        "SpellItemEnchantment",
        "Talent",
        "TalentTab",
        "AnimationData",
        "GameObjectDisplayInfo",
        "AreaTable",
        "Map",
        "SoundEntries",
        "Light",
        "LightParams",
        "WMOAreaTable",
        "HelmetGeosetVisData",
        "Faction",
        "FactionTemplate",
        "AreaTrigger",
        "GroundEffectTexture",
        "GroundEffectDoodad",
    ];
    let base = name.rsplit('/').next().unwrap_or(name);
    NAMES
        .iter()
        .find(|n| base.eq_ignore_ascii_case(&format!("{n}.dbc")))
        .map(|n| format!("{n}.dbc"))
        .unwrap_or_else(|| base.into())
}

fn inventory(data: &Path, output: &Path) -> Result<()> {
    let chain = Chain::open(data)?;
    let list = chain.list()?;
    let entries: Vec<_> = list
        .iter()
        .map(|e| json!({"path":e.name,"bytes":e.size}))
        .collect();
    write_json(
        output,
        &json!({
            "schema_version":1,"benilla_revision":REVISION,"entries":entries,
            "coverage":"MPQ listfiles are incomplete; explicit names and parsed dependencies are also required"
        }),
    )
}

fn disjoint(data: &Path, output: &Path) -> Result<()> {
    let data = data.canonicalize().context("source data does not exist")?;
    std::fs::create_dir_all(output)?;
    let output = output.canonicalize()?;
    if output.starts_with(&data) || data.starts_with(&output) {
        bail!("source and output must be separate directories");
    }
    Ok(())
}

fn pack(data: &Path, plan_path: &Path, output: &Path) -> Result<()> {
    disjoint(data, output)?;
    let plan: Plan = serde_json::from_slice(&std::fs::read(plan_path)?)?;
    if plan.schema_version != 1 || !(1..=60).contains(&plan.level) || plan.max_assets == 0 {
        bail!("unsupported extraction plan");
    }
    let mut chain = Chain::open(data)?;
    // This audit is written before extraction so interruptions cannot look like completion.
    write_json(
        &output.join("status.json"),
        &json!({"status":"running","complete":false}),
    )?;
    let list = chain.list()?;
    let mut seeds: BTreeSet<String> = plan
        .seeds
        .iter()
        .map(|s| normalize(s))
        .collect::<Result<_>>()?;
    let prefixes: Vec<_> = plan
        .prefixes
        .iter()
        .map(|s| normalize(s.trim_end_matches('/')))
        .collect::<Result<_>>()?;
    for entry in &list {
        let name = normalize(&entry.name)?;
        if prefixes.iter().any(|p| name.starts_with(&format!("{p}/"))) {
            seeds.insert(name);
        }
    }
    if let Some(selection) = &plan.world {
        if selection.tile_radius > 4 || !selection.center_yards.iter().all(|x| x.is_finite()) {
            bail!("world radius must be <= 4 and center must be finite");
        }
        let map = normalize(&selection.map)?;
        if map.contains('/') {
            bail!("map must be a directory name");
        }
        let wdt = format!("world/maps/{map}/{map}.wdt");
        seeds.insert(wdt.clone());
        let bytes = chain.read(&wdt)?;
        let parsed =
            benilla_wdt::WdtReader::new(Cursor::new(&bytes), benilla_wdt::WowVersion::Classic)
                .read()?;
        let (x, y) =
            benilla_wdt::world_to_tile(selection.center_yards[0], selection.center_yards[1]);
        let r = selection.tile_radius;
        for ty in y.saturating_sub(r)..=y.saturating_add(r).min(63) {
            for tx in x.saturating_sub(r)..=x.saturating_add(r).min(63) {
                if parsed
                    .get_tile(tx as usize, ty as usize)
                    .is_some_and(|t| t.has_adt)
                {
                    seeds.insert(format!("world/maps/{map}/{map}_{tx}_{ty}.adt"));
                }
            }
        }
    }
    let (spell_data, spell_dependencies) =
        spells::catalogue(&mut chain, plan.spell_family, plan.class_id, plan.level)?;
    seeds.extend(
        spell_dependencies
            .into_iter()
            .map(|s| normalize(&s))
            .collect::<Result<Vec<_>>>()?,
    );
    write_json(&output.join("catalogues/spells.json"), &spell_data)?;
    // Creature model filenames can be absent from listfiles, and replaceable skin textures
    // are not hardcoded M2 dependencies. Resolve them through client display tables too.
    let creatures = benilla_formats::load_creature_catalog(&mut chain)?;
    for (display, _) in creatures.display_models() {
        let Some(creature) = creatures.model(display) else {
            continue;
        };
        let path = normalize(&model_path(&creature.model_path))?;
        if seeds.contains(&path) || prefixes.iter().any(|p| path.starts_with(&format!("{p}/"))) {
            seeds.insert(path.clone());
            let directory = path.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
            for texture in creature
                .textures
                .into_iter()
                .flatten()
                .filter(|s| !s.is_empty())
            {
                let texture = if texture.contains(['/', '\\']) {
                    texture
                } else {
                    format!("{directory}/{texture}")
                };
                let texture = if texture.to_ascii_lowercase().ends_with(".blp") {
                    texture
                } else {
                    format!("{texture}.blp")
                };
                seeds.insert(normalize(&texture)?);
            }
        }
    }
    let mut queue: VecDeque<_> = seeds.into_iter().collect();
    let mut seen = BTreeSet::new();
    let mut assets = Vec::new();
    let mut failures = Vec::new();
    while let Some(name) = queue.pop_front() {
        if !seen.insert(name.clone()) {
            continue;
        }
        if seen.len() > plan.max_assets {
            failures.push(
                json!({"path":name,"error":"asset limit exceeded; remaining queue not extracted"}),
            );
            break;
        }
        let extracted = (|| -> Result<Value> {
            let bytes = chain.read(&name)?;
            let source_archive = chain
                .find_file_archive(&name)
                .and_then(|p| p.file_name())
                .map(|n| n.to_string_lossy().into_owned());
            write_bytes(&output.join("raw").join(&name), &bytes)?;
            let (decoded, dependencies, warnings) = decode(&name, &bytes, output)?;
            let dependencies: Vec<_> = dependencies
                .iter()
                .filter(|s| !s.is_empty())
                .map(|s| normalize(&model_path(s)))
                .collect::<Result<_>>()?;
            queue.extend(dependencies.iter().cloned());
            let decoded_hash = decoded
                .as_ref()
                .map(|p| std::fs::read(output.join(p)).map(|b| hash(&b)))
                .transpose()?;
            Ok(
                json!({"path":name,"source_archive":source_archive,"bytes":bytes.len(),"sha256":hash(&bytes),
                "raw":format!("raw/{name}"),"decoded":decoded,"decoded_sha256":decoded_hash,
                "dependencies":dependencies,"warnings":warnings}),
            )
        })();
        match extracted {
            Ok(asset) => assets.push(asset),
            Err(e) => failures.push(json!({"path":name,"error":format!("{e:#}")})),
        }
        if seen.len() % 100 == 0 {
            eprintln!("{} assets visited; {} failures", seen.len(), failures.len());
        }
    }
    assets.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    let complete = failures.is_empty();
    write_json(
        &output.join("manifest.json"),
        &json!({
            "schema_version":1,"benilla_revision":REVISION,"client_target":{"version":"1.12.1","build":5875,"locale":"enUS"},
            "source_build_verified":false,"units":"yards","axes":"raw WoW: X north/forward, Y west/left, Z up",
            "retail_content":"private, derived from locally supplied installation; not for public repository",
            "assets":assets,"failures":failures,"complete":complete,
            "limits":["Client DBCs do not contain complete NPC/item templates, spawns, loot or quest rules",
                      "Raw records and animation channels are preserved; renderer/VFX parity is not claimed"]
        }),
    )?;
    write_json(
        &output.join("status.json"),
        &json!({"status":if complete {"extracted"} else {"incomplete"},"complete":complete}),
    )?;
    if !complete {
        bail!("extraction incomplete; see manifest.json failures");
    }
    Ok(())
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Inventory { data, output } => inventory(&data, &output),
        Command::Pack { data, plan, output } => pack(&data, &plan, &output),
        Command::Convert { input, output } => {
            let bytes = std::fs::read(&input)?;
            let name = normalize(
                &input
                    .file_name()
                    .context("input has no filename")?
                    .to_string_lossy(),
            )?;
            decode(&name, &bytes, &output)?;
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reject_archive_escape() {
        for path in [
            "../bad.m2",
            "/bad.m2",
            "a/../../bad",
            "C:\\bad",
            "a\\..\\bad",
        ] {
            assert!(normalize(path).is_err(), "{path}");
        }
        assert_eq!(
            normalize("Character\\Human\\Male\\HumanMale.M2").unwrap(),
            "character/human/male/humanmale.m2"
        );
    }
}
