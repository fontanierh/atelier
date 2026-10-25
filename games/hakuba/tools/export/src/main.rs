//! The `export` command: exports asset folders, or checks that their committed exports are current.
//!
//! ```sh
//! cargo export assets/characters/nox      # export it, record its inputs
//! cargo export --check assets             # every asset folder under assets/
//! ```
//!
//! An asset folder's `asset.toml` names its kind and that kind's settings ([`Asset`]). Exporting writes the folder's
//! `<folder name>.glb` and records in `asset.toml` a checksum of the inputs: the settings, the folder's `src/` and
//! this crate. A check reports a folder whose `.glb` is missing or whose inputs no longer match that checksum.

mod animation;
mod animations;
mod character;
mod characters;
mod glb;
mod pose;
mod pose_edit;
mod retarget;
mod rig;

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
    Animation(animation::Settings),
    Character(character::Settings),
}

impl Asset {
    /// The other assets whose exports this one reads, by folder relative to `assets/`.
    fn reads(&self) -> Vec<&'static str> {
        match self {
            Asset::Animation(_) => Vec::new(),
            Asset::Character(_) => character::ANIMATIONS.iter().map(|animation| animation.folder()).collect(),
        }
    }
}

/// The checksum `export` writes into `asset.toml`.
const CHECKSUM: &str = "inputs_sha256";

/// This crate's folder, whose files are inputs of every export.
const EXPORTER: &str = env!("CARGO_MANIFEST_DIR");

/// The game's `assets/` folder.
const ASSETS: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../assets");

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
        self.path.join(format!("{name}.glb"))
    }

    fn recorded_checksum(&self) -> Option<&str> {
        self.document.get(CHECKSUM).and_then(|item| item.as_str())
    }

    fn inputs_checksum(&self) -> Result<String> {
        let mut digest = Sha256::new();
        digest.update(serde_json::to_vec(&self.asset)?);
        digest.update([0]);
        for root in [self.path.join("src"), PathBuf::from(EXPORTER)] {
            let base = root.parent().expect("an input folder has a parent");
            for file in files(&root)? {
                digest.update(file.strip_prefix(base)?.to_string_lossy().as_bytes());
                digest.update([0]);
                digest.update(Sha256::digest(fs::read(&file)?));
            }
        }
        for folder in self.asset.reads() {
            let output = Folder::read(&Path::new(ASSETS).join(folder))?.output();
            digest.update(folder.as_bytes());
            digest.update([0]);
            digest.update(Sha256::digest(fs::read(&output).with_context(|| format!("reading {}", output.display()))?));
        }
        Ok(format!("{:x}", digest.finalize()))
    }

    fn problems(&self) -> Result<Vec<String>> {
        let mut found = Vec::new();
        if !self.output().is_file() {
            found.push(format!("{} is missing", self.output().file_name().unwrap().to_string_lossy()));
        }
        if self.recorded_checksum() != Some(self.inputs_checksum()?.as_str()) {
            found.push("its inputs changed since the last export".into());
        }
        Ok(found)
    }

    fn export(mut self) -> Result<()> {
        for folder in self.asset.reads() {
            let read = Folder::read(&Path::new(ASSETS).join(folder))?;
            if !read.problems()?.is_empty() {
                bail!("{}: export assets/{folder} first, its export is out of date", self.path.display());
            }
        }
        let output = self.output();
        match &self.asset {
            Asset::Animation(settings) => animation::export(&self.path, settings, &output)?,
            Asset::Character(settings) => character::export(&self.path, settings, &output)?,
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
        if !check {
            exports.push(Folder::read(&path)?);
            continue;
        }
        for folder in asset_folders(&path)? {
            for problem in Folder::read(&folder)?.problems()? {
                println!("{}: {problem}", folder.display());
                stale += 1;
            }
        }
    }
    // Animations first: characters read their exports.
    exports.sort_by_key(|folder| !matches!(folder.asset, Asset::Animation(_)));
    for folder in exports {
        folder.export()?;
    }
    Ok(if stale == 0 { ExitCode::SUCCESS } else { ExitCode::FAILURE })
}
