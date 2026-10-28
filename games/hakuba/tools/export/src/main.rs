//! The `export` command: exports asset folders, or checks that their committed exports are current.
//!
//! ```sh
//! cargo export assets/characters/nox      # export it, record its inputs
//! cargo export assets                     # every asset folder under assets/, each after those it reads
//! cargo export --check assets             # check every asset folder under assets/
//! ```
//!
//! An asset folder's `asset.toml` names its kind and that kind's settings ([`Asset`]). Exporting writes the folder's
//! `<folder name>.glb` (`.ktx2` for a texture, `.ogg` and the list of its takes for a sound) and records in
//! `asset.toml` a checksum of the inputs: the settings, the folder's `src/`, the exporter's code for that kind
//! ([`code`]) and the assets it reads. A check reports a folder whose export is missing or whose inputs no longer
//! match that checksum.

mod glb;
mod model;
mod rig;
mod shapes;
mod sound;
mod texture;
mod world;

use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use toml_edit::DocumentMut;

/// What an `asset.toml` describes: its `kind` and the settings of that kind.
#[derive(Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Asset {
    Animation(rig::animation::Settings),
    Character(rig::character::Settings),
    Equipment(rig::equipment::Settings),
    Plant(Box<model::plant::Settings>),
    Prop(model::prop::Settings),
    Sound(sound::Settings),
    Texture(texture::Settings),
    World(world::Settings),
}

impl Asset {
    /// The other assets whose exports this one reads, by folder relative to `assets/`.
    fn reads(&self) -> Vec<String> {
        match self {
            Asset::Animation(_)
            | Asset::Equipment(_)
            | Asset::Plant(_)
            | Asset::Prop(_)
            | Asset::Sound(_)
            | Asset::Texture(_) => Vec::new(),
            Asset::Character(settings) if settings.uses_authored_clips() => Vec::new(),
            Asset::Character(_) => rig::animations::ANIMATIONS.into_iter().map(rig::animation::folder).collect(),
            Asset::World(settings) => world::reads(settings),
        }
    }

    /// The exporter's folder holding this kind's code, relative to the exporter.
    fn code_folder(&self) -> &'static str {
        match self {
            Asset::Animation(_) | Asset::Character(_) | Asset::Equipment(_) => "src/rig",
            Asset::Plant(_) | Asset::Prop(_) => "src/model",
            Asset::Sound(_) => "src/sound",
            Asset::Texture(_) => "src/texture",
            Asset::World(_) => "src/world",
        }
    }

    /// The extension of the file this kind exports.
    fn extension(&self) -> &'static str {
        match self {
            Asset::Animation(_)
            | Asset::Character(_)
            | Asset::Equipment(_)
            | Asset::Plant(_)
            | Asset::Prop(_)
            | Asset::World(_) => "glb",
            Asset::Sound(_) => "ogg",
            Asset::Texture(_) => "ktx2",
        }
    }

    /// The files this asset's own kind publishes.
    fn outputs(&self, output: &Path) -> Vec<PathBuf> {
        match self {
            Asset::Texture(settings) => settings.outputs(output),
            Asset::Sound(_) => vec![output.to_path_buf(), sound::takes_file(output)],
            _ => vec![output.to_path_buf()],
        }
    }

    /// Validation belongs to the kind that owns the output.
    fn output_problems(&self, output: &Path) -> Vec<String> {
        match self {
            Asset::Texture(settings) => settings.output_problems(output),
            _ => Vec::new(),
        }
    }

    /// Asset-relative files named by this export, checked without making them rebuild inputs.
    fn required_outputs(&self, output: &Path) -> Result<Vec<String>> {
        match self {
            Asset::Plant(_) | Asset::Prop(_) => model::required_outputs(output),
            _ => Ok(Vec::new()),
        }
    }
}

/// The checksum `export` writes into `asset.toml`.
const CHECKSUM: &str = "inputs_sha256";

/// This crate's folder.
const EXPORTER: &str = env!("CARGO_MANIFEST_DIR");

/// The exporter's files that every kind is built from, relative to the exporter: the command, the glTF reader and
/// writer, the shapes meshes are built from, and the crate and Rust versions.
const SHARED_CODE: [&str; 6] = [
    "src/main.rs",
    "src/glb.rs",
    "src/shapes.rs",
    "Cargo.toml",
    "../../Cargo.lock",
    "../../rust-toolchain.toml",
];

/// The exporter's files that a kind is built from: [`SHARED_CODE`] and the `.rs` files in the kind's `folder`. Docs
/// and other kinds' code are left out, so editing them marks no export of this kind out of date.
fn code(folder: &str) -> Result<Vec<PathBuf>> {
    let root = Path::new(EXPORTER);
    let mut code: Vec<PathBuf> = SHARED_CODE.iter().map(|file| root.join(file)).collect();
    code.extend(files(&root.join(folder))?.into_iter().filter(|file| file.extension().is_some_and(|e| e == "rs")));
    if folder == "src/world" {
        // Only world metadata uses this shared schema; its edits must invalidate the world export.
        code.push(root.join("../../schemas/water/Cargo.toml"));
        code.extend(
            files(&root.join("../../schemas/water/src"))?
                .into_iter()
                .filter(|p| p.extension().is_some_and(|e| e == "rs")),
        );
    }
    Ok(code)
}

/// Adds each file to `digest`: its path relative to `base`, then a checksum of its bytes.
fn add_files(digest: &mut Sha256, base: &Path, files: &[PathBuf]) -> Result<()> {
    for file in files {
        digest.update(file.strip_prefix(base)?.to_string_lossy().as_bytes());
        digest.update([0]);
        digest.update(Sha256::digest(fs::read(file).with_context(|| format!("reading {}", file.display()))?));
    }
    Ok(())
}

/// The game's `assets/` folder.
const ASSETS: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../assets");

/// Where an export two folders below `assets/`, such as a plant's or a tile's, finds the export of the asset `folder`
/// (relative to `assets/`), whose file has the `extension`. Fails if there is no such asset.
fn uri_of_asset(folder: &str, extension: &str) -> Result<String> {
    if !Path::new(ASSETS).join(folder).join("asset.toml").is_file() {
        bail!("there is no asset assets/{folder}/");
    }
    let name = folder.rsplit('/').next().unwrap_or(folder);
    Ok(format!("../../{folder}/{name}.{extension}"))
}

/// Where an export two folders below `assets/` finds the texture `name`. An export names its textures and never holds
/// them, so repainting a texture rebuilds nothing else. Fails if there is no such texture asset.
fn uri_of_texture(name: &str) -> Result<String> {
    uri_of_asset(&format!("textures/{name}"), "ktx2")
}

/// An asset folder's parsed `asset.toml`.
struct Folder {
    path: PathBuf,
    document: DocumentMut,
    asset: Asset,
}

impl Folder {
    fn read(path: &Path) -> Result<Self> {
        let file = path.join("asset.toml");
        let text = fs::read_to_string(&file).with_context(|| format!("reading {}", file.display()))?;
        let document: DocumentMut = text.parse().with_context(|| format!("parsing {}", file.display()))?;
        let mut settings = document.clone();
        settings.remove(CHECKSUM);
        let asset = toml_edit::de::from_document(settings).with_context(|| format!("reading {}", file.display()))?;
        Ok(Self { path: path.to_path_buf(), document, asset })
    }

    fn output(&self) -> PathBuf {
        let name = self.path.file_name().expect("an asset folder has a name").to_string_lossy();
        self.path.join(format!("{name}.{}", self.asset.extension()))
    }

    fn recorded_checksum(&self) -> Option<&str> {
        self.document.get(CHECKSUM).and_then(|item| item.as_str())
    }

    fn inputs_checksum(&self) -> Result<String> {
        let mut digest = Sha256::new();
        digest.update(serde_json::to_vec(&self.asset)?);
        digest.update([0]);
        add_files(&mut digest, &self.path, &files(&self.path.join("src"))?)?;
        add_files(&mut digest, Path::new(EXPORTER), &code(self.asset.code_folder())?)?;
        // An asset read covers its own code too, through its recorded checksum: a character runs each animation's.
        for folder in self.asset.reads() {
            let read = Folder::read(&Path::new(ASSETS).join(&folder))?;
            digest.update(folder.as_bytes());
            digest.update([0]);
            digest.update(read.recorded_checksum().unwrap_or_default().as_bytes());
            digest.update([0]);
            let output = read.output();
            digest.update(Sha256::digest(fs::read(&output).with_context(|| format!("reading {}", output.display()))?));
        }
        Ok(format!("{:x}", digest.finalize()))
    }

    fn problems(&self) -> Result<Vec<String>> {
        let mut found = Vec::new();
        let output = self.output();
        for file in self.asset.outputs(&output) {
            if !file.is_file() {
                found.push(format!("{} is missing", file.file_name().unwrap().to_string_lossy()));
            }
        }
        found.extend(self.asset.output_problems(&output));
        if output.is_file() {
            match self.asset.required_outputs(&output) {
                Ok(paths) => {
                    for path in paths {
                        let required = Path::new(ASSETS).join(&path);
                        let Some(folder) = required.parent() else {
                            found.push(format!("invalid required output path: {path}"));
                            continue;
                        };
                        let result = (|| -> Result<()> {
                            let dependency = Folder::read(folder)?;
                            if !dependency.asset.outputs(&dependency.output()).contains(&required) {
                                bail!("required output is not declared");
                            }
                            let problems = dependency.problems()?;
                            if !problems.is_empty() {
                                bail!("{}", problems.join(", "));
                            }
                            Ok(())
                        })();
                        if let Err(error) = result {
                            found.push(format!("{path}: {error}"));
                        }
                    }
                }
                Err(error) => found.push(format!("invalid required output metadata: {error}")),
            }
        }
        if self.recorded_checksum() != Some(self.inputs_checksum()?.as_str()) {
            found.push("its inputs changed since the last export".into());
        }
        Ok(found)
    }

    fn export(mut self) -> Result<()> {
        for folder in self.asset.reads() {
            let read = Folder::read(&Path::new(ASSETS).join(&folder))?;
            if !read.problems()?.is_empty() {
                bail!("{}: export assets/{folder} first, its export is out of date", self.path.display());
            }
        }
        let output = self.output();
        match &self.asset {
            Asset::Animation(settings) => rig::animation::export(&self.path, settings, &output)?,
            Asset::Character(settings) => rig::character::export(&self.path, settings, &output)?,
            Asset::Equipment(settings) => rig::equipment::export(&self.path, settings, &output)?,
            Asset::Plant(settings) => model::plant::export(settings, &output)?,
            Asset::Prop(settings) => model::prop::export(settings, &output)?,
            Asset::Sound(settings) => sound::export(&self.path, settings, &output)?,
            Asset::Texture(settings) => texture::export(&self.path, settings, &output)?,
            Asset::World(settings) => world::export(&self.path, settings, &output)?,
        }
        self.document[CHECKSUM] = toml_edit::value(self.inputs_checksum()?);
        fs::write(self.path.join("asset.toml"), self.document.to_string())?;
        println!("{}: exported {}", self.path.display(), output.file_name().unwrap().to_string_lossy());
        Ok(())
    }
}

/// Every file under `root`, sorted, leaving out hidden files and build outputs.
fn files(root: &Path) -> Result<Vec<PathBuf>> {
    let mut found = Vec::new();
    if !root.is_dir() {
        return Ok(found);
    }
    for entry in fs::read_dir(root)? {
        let path = entry?.path();
        let name = path.file_name().unwrap().to_string_lossy();
        if name.starts_with('.') || name == "target" {
            continue;
        }
        if path.is_dir() {
            found.extend(files(&path)?);
        } else {
            found.push(path);
        }
    }
    found.sort();
    Ok(found)
}

/// Every asset folder at or under `root`.
fn asset_folders(root: &Path) -> Result<Vec<PathBuf>> {
    if root.join("asset.toml").is_file() {
        return Ok(vec![root.to_path_buf()]);
    }
    let mut found = Vec::new();
    let mut entries: Vec<_> = fs::read_dir(root)?.map(|entry| entry.map(|e| e.path())).collect::<Result<_, _>>()?;
    entries.sort();
    for path in entries.into_iter().filter(|path| path.is_dir()) {
        found.extend(asset_folders(&path)?);
    }
    Ok(found)
}

fn main() -> Result<ExitCode> {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let check = args.first().is_some_and(|arg| arg == "--check");
    if check {
        args.remove(0);
    }
    if args.is_empty() || args.iter().any(|arg| arg.starts_with('-')) {
        bail!("usage: cargo export [--check] FOLDER...");
    }
    let (mut stale, mut exports) = (0, Vec::new());
    for arg in &args {
        let path = fs::canonicalize(arg).with_context(|| format!("finding {arg}"))?;
        for folder in asset_folders(&path)? {
            if !check {
                exports.push(Folder::read(&folder)?);
                continue;
            }
            for problem in Folder::read(&folder)?.problems()? {
                println!("{}: {problem}", folder.display());
                stale += 1;
            }
        }
    }
    export_in_order(exports)?;
    Ok(if stale == 0 { ExitCode::SUCCESS } else { ExitCode::FAILURE })
}

/// Exports each folder after those among `pending` whose exports it reads.
fn export_in_order(mut pending: Vec<Folder>) -> Result<()> {
    let waits = |folder: &Folder, pending: &[Folder]| {
        folder.asset.reads().iter().any(|read| {
            let read = fs::canonicalize(Path::new(ASSETS).join(read)).ok();
            pending.iter().any(|other| Some(&other.path) == read.as_ref())
        })
    };
    while !pending.is_empty() {
        let Some(next) = pending.iter().position(|folder| !waits(folder, &pending)) else {
            let names: Vec<String> = pending.iter().map(|folder| folder.path.display().to_string()).collect();
            bail!("these assets read each other's exports: {}", names.join(", "));
        };
        pending.remove(next).export()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn character_dependencies_follow_the_clip_source() {
        let authored = Folder::read(&Path::new(ASSETS).join("characters/wanderer")).unwrap();
        let shared = Folder::read(&Path::new(ASSETS).join("characters/nox")).unwrap();
        assert!(authored.asset.reads().is_empty());
        let expected: Vec<_> = rig::animations::ANIMATIONS.into_iter().map(rig::animation::folder).collect();
        assert!(!expected.is_empty());
        assert_eq!(shared.asset.reads(), expected);
    }

    /// Each kind's code folder under `src/`, and the asset groups whose `.rs` files it compiles in.
    const KINDS: [(&str, &[&str]); 5] = [
        ("model", &["plants", "props"]),
        ("rig", &["animations", "characters"]),
        ("sound", &["sounds"]),
        ("texture", &["textures"]),
        ("world", &["world"]),
    ];

    /// The `.rs` files under `root`.
    fn sources(root: &Path) -> Vec<PathBuf> {
        files(root).unwrap().into_iter().filter(|file| file.extension().is_some_and(|e| e == "rs")).collect()
    }

    /// The kinds whose code `file` names, as `crate::<kind>` or `super::<kind>`.
    fn kinds_named(file: &Path) -> Vec<&'static str> {
        let text = fs::read_to_string(file).unwrap();
        let names = |kind: &str| text.contains(&format!("crate::{kind}")) || text.contains(&format!("super::{kind}"));
        KINDS.iter().map(|(kind, _)| *kind).filter(|kind| names(kind)).collect()
    }

    #[test]
    fn every_file_beside_main_is_shared_code() {
        for file in fs::read_dir(Path::new(EXPORTER).join("src")).unwrap() {
            let path = file.unwrap().path();
            let name = path.file_name().unwrap().to_string_lossy().into_owned();
            if path.is_dir() {
                assert!(KINDS.iter().any(|(kind, _)| *kind == name), "src/{name}/ is no kind's folder");
            } else {
                assert!(SHARED_CODE.contains(&format!("src/{name}").as_str()), "src/{name} is not in SHARED_CODE");
            }
        }
    }

    #[test]
    fn shared_code_names_no_kind() {
        let file = Path::new(EXPORTER).join("src/glb.rs");
        assert!(kinds_named(&file).is_empty(), "{} uses a kind's code", file.display());
    }

    #[test]
    fn each_kind_uses_only_its_own_code_and_the_shared_code() {
        for (kind, groups) in KINDS {
            let mut files = sources(&Path::new(EXPORTER).join("src").join(kind));
            for group in groups {
                files.extend(sources(&Path::new(ASSETS).join(group)));
            }
            for file in files {
                for other in kinds_named(&file) {
                    assert_eq!(other, kind, "{} is {kind} code but uses crate::{other}", file.display());
                }
            }
        }
    }

    #[test]
    fn each_kind_compiles_in_only_its_own_assets() {
        for (kind, groups) in KINDS {
            let allowed: Vec<PathBuf> =
                groups.iter().map(|g| fs::canonicalize(Path::new(ASSETS).join(g)).unwrap()).collect();
            for file in sources(&Path::new(EXPORTER).join("src").join(kind)) {
                for line in fs::read_to_string(&file).unwrap().lines() {
                    let Some(path) = line.trim().strip_prefix("#[path = \"").and_then(|rest| rest.strip_suffix("\"]"))
                    else {
                        continue;
                    };
                    let target = fs::canonicalize(file.parent().unwrap().join(path)).unwrap();
                    assert!(
                        allowed.iter().any(|folder| target.starts_with(folder)),
                        "{} compiles in {}, outside its kind's assets",
                        file.display(),
                        target.display()
                    );
                }
            }
        }
    }
}
