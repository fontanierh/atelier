//! Exact-owned-set checkout installs. Store/root/worker lifecycle policy remains separate.
//! Pre-install interruptions quarantine the pre-owned scope; later unknown mutations fail closed.
//! The library remains unused pending final validation and separately reviewed caller integration.
use crate::checkout_locks::{
    BuildGuard, CheckoutLocks, ContentReadGuard, INSTALL_METADATA, LockError,
};
use crate::graph::BuildGraph;
pub use crate::install_fs::FileObservation;
use crate::install_fs::{CreatedDirectory, RootFs};
use crate::keys::{InputPayload, PreparedInput, PreparedUnit, canonical_bytes};
use crate::leases::ProcessIdentity;
use crate::paths::{Claims, claim, conflict, folded, logical_path, relative_path};
use crate::results::{ResultEnvelope, ResultError, ResultStore, WriteTransaction};
use crate::schema::{ContentSource, Destination, Input, Item, Provenance, StoredFile, StoredItem};
use crate::source_hashes::sha256;
use crate::staging::{ObjectSource, SourceError, SourceErrorKind};
use crate::store::{ObjectDigest, ObjectStore, StoreError};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::io;
use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

pub const RECEIPT_VERSION: u32 = 1;
pub const JOURNAL_VERSION: u32 = 1;
const INDEX: &str = "build/build-v2/install/index.json";
const JOURNAL: &str = "build/build-v2/install/journal.json";
static NEXT: AtomicU64 = AtomicU64::new(0);

#[derive(Debug)]
pub enum InstallError {
    Invalid(String),
    RecoveryRequired(String),
    Lock(LockError),
    Cache(ResultError),
    LocalCompletion(ResultError),
    Store(StoreError),
    Io(io::Error),
}
impl fmt::Display for InstallError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invalid(reason) => write!(formatter, "invalid install: {reason}"),
            Self::RecoveryRequired(reason) => {
                write!(formatter, "install recovery required: {reason}")
            }
            Self::Lock(error) => error.fmt(formatter),
            Self::LocalCompletion(error) => write!(formatter, "local completion: {error}"),
            Self::Cache(error) => error.fmt(formatter),
            Self::Store(error) => error.fmt(formatter),
            Self::Io(error) => error.fmt(formatter),
        }
    }
}
impl std::error::Error for InstallError {}
impl From<io::Error> for InstallError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}
impl From<LockError> for InstallError {
    fn from(error: LockError) -> Self {
        Self::Lock(error)
    }
}
impl From<ResultError> for InstallError {
    fn from(error: ResultError) -> Self {
        Self::Cache(error)
    }
}
impl From<StoreError> for InstallError {
    fn from(error: StoreError) -> Self {
        Self::Store(error)
    }
}
fn invalid(reason: impl Into<String>) -> InstallError {
    InstallError::Invalid(reason.into())
}
fn recovery(reason: impl Into<String>) -> InstallError {
    InstallError::RecoveryRequired(reason.into())
}
fn bytes(value: &impl Serialize) -> Result<Vec<u8>, InstallError> {
    canonical_bytes(value).map_err(invalid)
}
fn digest(value: &str) -> Result<(), InstallError> {
    ObjectDigest::from_hex(value)?;
    Ok(())
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ProjectNamespace(String);
impl ProjectNamespace {
    pub fn new(value: &str) -> Result<Self, InstallError> {
        if value.is_empty()
            || value == "."
            || value == ".."
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b"_.:-".contains(&byte))
        {
            return Err(invalid(
                "project namespace must be a stable explicit opaque identifier",
            ));
        }
        Ok(Self(value.into()))
    }
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// Namespace is explicit project identity, never selected roots/targets or a unit label.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OwnerId {
    pub project: ProjectNamespace,
    pub logical_path: String,
}
impl OwnerId {
    pub fn new(project: ProjectNamespace, path: &str) -> Result<Self, InstallError> {
        logical_path(path).map_err(invalid)?;
        Ok(Self {
            project,
            logical_path: folded(path),
        })
    }
    fn fingerprint(&self) -> Result<String, InstallError> {
        Ok(sha256(&bytes(self)?))
    }
}

#[derive(Clone, Debug)]
pub struct InstallPolicy {
    pub project: ProjectNamespace,
    pub allowed_install_roots: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReceiptFile {
    pub output_path: String,
    pub install_path: String,
    pub digest: String,
    pub size: u64,
    pub mode: u32,
    pub observation: FileObservation,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ItemReceipt {
    pub version: u32,
    pub owner: OwnerId,
    pub logical_path: String,
    pub class: String,
    pub result_key: String,
    pub files: Vec<ReceiptFile>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReceiptIndex {
    version: u32,
    /// Owner fingerprint -> immutable item receipt ID.
    receipts: BTreeMap<String, String>,
    /// Normalized checkout-relative file path -> owner fingerprint, across ALL projects.
    paths: BTreeMap<String, String>,
}
impl Default for ReceiptIndex {
    fn default() -> Self {
        Self {
            version: RECEIPT_VERSION,
            receipts: BTreeMap::new(),
            paths: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Debug)]
struct DeclaredOwner {
    class: String,
    files: BTreeMap<String, (String, bool)>,
}

/// Pure complete declared ownership/reference/source view, not just selected targets.
/// The caller supplies every project declaration relevant to this checkout.
#[derive(Clone, Debug)]
pub struct OwnershipSnapshot {
    projects: BTreeSet<ProjectNamespace>,
    owners: BTreeMap<OwnerId, DeclaredOwner>,
    paths: Claims,
    sources: Claims,
    references: BTreeSet<OwnerId>,
}
impl OwnershipSnapshot {
    pub fn from_projects<'a>(
        projects: impl IntoIterator<Item = (ProjectNamespace, &'a BuildGraph)>,
    ) -> Result<Self, InstallError> {
        let mut view = Self {
            projects: BTreeSet::new(),
            owners: BTreeMap::new(),
            paths: Claims::new(),
            sources: Claims::new(),
            references: BTreeSet::new(),
        };
        for (namespace, graph) in projects {
            if !view.projects.insert(namespace.clone()) {
                return Err(invalid("duplicate project ownership view"));
            }
            for unit in &graph.declaration().units {
                for path in &unit.code {
                    claim_source(&mut view.sources, path)?;
                }
                for input in &unit.inputs {
                    match input {
                        Input::Content {
                            source: ContentSource::File { path, .. },
                            ..
                        } => claim_source(&mut view.sources, path)?,
                        Input::Reference { logical_path, .. } => {
                            view.references
                                .insert(OwnerId::new(namespace.clone(), logical_path)?);
                        }
                        _ => {}
                    }
                }
                for item in &unit.outputs {
                    if item.destination != Destination::Checkout {
                        continue;
                    }
                    let owner = OwnerId::new(namespace.clone(), &item.logical_path)?;
                    let fingerprint = owner.fingerprint()?;
                    let mut files = BTreeMap::new();
                    for file in &item.files {
                        let path = file
                            .install_path
                            .as_ref()
                            .ok_or_else(|| invalid("checkout output lacks install mapping"))?;
                        relative_path(path, true).map_err(invalid)?;
                        claim(&mut view.paths, path, &fingerprint).map_err(invalid)?;
                        files.insert(file.path.clone(), (path.clone(), file.required));
                    }
                    if view
                        .owners
                        .insert(
                            owner,
                            DeclaredOwner {
                                class: item.class.clone(),
                                files,
                            },
                        )
                        .is_some()
                    {
                        return Err(invalid("duplicate logical owner"));
                    }
                }
            }
        }
        for (path, _) in view.paths.values() {
            if conflict(&view.sources, path).is_some() {
                return Err(invalid("checkout output overlaps current source/code"));
            }
        }
        Ok(view)
    }
}
fn claim_source(claims: &mut Claims, path: &str) -> Result<(), InstallError> {
    relative_path(path, false).map_err(invalid)?;
    // Sources may share/overlap declarations. Retain every normalized claim so a
    // later wider source cannot disappear behind an earlier narrower claim.
    claims
        .entry(folded(path))
        .or_insert((path.into(), "declared source/code".into()));
    Ok(())
}

#[derive(Clone, Debug)]
pub struct RemovalIntent {
    pub owner: OwnerId,
    pub expected_receipt_id: String,
    pub exact_paths: BTreeSet<String>,
}

pub struct LeaseIdentity {
    pub provenance: Provenance,
    pub owner: ProcessIdentity,
    pub workers: Vec<ProcessIdentity>,
    pub upstream_result_keys: BTreeSet<String>,
}

#[derive(Clone, Debug)]
pub enum CurrentStatus {
    Current(Vec<ItemReceipt>),
    Dirty,
    NotMaterialized,
}

/// Sealed identity observation only: no retained checkout guard, FD or byte-availability claim.
/// Source staging must separately reacquire and revalidate CurrentSources.
pub struct CurrentIdentities {
    key: String,
    items: Vec<StoredItem>,
}
impl CurrentIdentities {
    pub fn key(&self) -> &str {
        &self.key
    }
    pub fn items(&self) -> &[StoredItem] {
        &self.items
    }
}

/// Sealed checkout-byte availability. Custody ends after staging independent job clones.
/// Public CurrentStatus receipt vectors cannot construct this capability.
pub struct CurrentSources<'build> {
    _build: &'build BuildGuard,
    _read: ContentReadGuard,
    receipts: Vec<ItemReceipt>,
    files: BTreeMap<ObjectDigest, CurrentFile>,
}
struct CurrentFile {
    file: fs::File,
    observation: FileObservation,
}
impl CurrentSources<'_> {
    pub fn receipts(&self) -> &[ItemReceipt] {
        &self.receipts
    }
    pub fn contains(&self, digest: &ObjectDigest) -> bool {
        self.files.contains_key(digest)
    }
    /// Bind exact consumer-visible item metadata before allowing any clone.
    pub fn objects_for<'a>(
        &'a self,
        inputs: &[&PreparedInput],
    ) -> Result<CurrentObjects<'a, '_>, InstallError> {
        let mut allowed = BTreeSet::new();
        for input in inputs {
            let InputPayload::Item {
                logical_path,
                class,
                files,
            } = &input.payload
            else {
                return Err(invalid("current source requires a typed item input"));
            };
            let receipt = self
                .receipts
                .iter()
                .find(|receipt| receipt.logical_path == *logical_path && receipt.class == *class)
                .ok_or_else(|| invalid("current input item differs from certified receipt"))?;
            if files
                .iter()
                .map(|file| &file.path)
                .collect::<BTreeSet<_>>()
                .len()
                != files.len()
                || receipt.files.len() != files.len()
                || files.iter().any(|file| {
                    !receipt.files.iter().any(|saved| {
                        saved.output_path == file.path
                            && saved.digest == file.digest
                            && saved.size == file.size
                            && saved.mode == file.mode
                    })
                })
            {
                return Err(invalid(
                    "current input content/mode differs from certified receipt",
                ));
            }
            for file in files {
                allowed.insert(ObjectDigest::from_hex(&file.digest)?);
            }
        }
        Ok(CurrentObjects {
            sources: self,
            allowed,
        })
    }
    /// Every descriptor is checked again by the staging adapter before and after cloning.
    pub(crate) fn file(&self, digest: &ObjectDigest) -> Result<&fs::File, InstallError> {
        let current = self
            .files
            .get(digest)
            .ok_or_else(|| invalid("uncertified current digest"))?;
        let metadata = current.file.metadata()?;
        if !metadata.is_file() || FileObservation::from_metadata(&metadata) != current.observation {
            return Err(invalid("current source changed under read custody"));
        }
        Ok(&current.file)
    }
}

/// Borrowed only across C1b stage; it cannot outlive checkout read custody.
pub struct CurrentObjects<'sources, 'build> {
    sources: &'sources CurrentSources<'build>,
    allowed: BTreeSet<ObjectDigest>,
}
impl ObjectSource for CurrentObjects<'_, '_> {
    fn clone_object(&self, digest: &ObjectDigest, destination: &Path) -> Result<(), SourceError> {
        let error = |kind, message: String| SourceError {
            kind,
            digest: digest.clone(),
            message,
        };
        if !self.allowed.contains(digest) {
            return Err(error(
                SourceErrorKind::Unavailable,
                "uncertified current digest".into(),
            ));
        }
        let source = self
            .sources
            .file(digest)
            .map_err(|e| error(SourceErrorKind::Changed, e.to_string()))?;
        clone_current_fd(source, destination).map_err(|e| {
            error(
                if e.kind() == io::ErrorKind::Unsupported
                    || matches!(e.raw_os_error(), Some(libc::ENOTSUP) | Some(libc::EXDEV))
                {
                    SourceErrorKind::CloneUnsupported
                } else {
                    SourceErrorKind::Io
                },
                e.to_string(),
            )
        })?;
        if let Err(failure) = self.sources.file(digest) {
            // Only our successful clone owns this leaf; never remove a pre-existing destination.
            let _ = fs::remove_file(destination);
            return Err(error(SourceErrorKind::Changed, failure.to_string()));
        }
        Ok(())
    }
}

fn clone_current_fd(source: &fs::File, destination: &Path) -> io::Result<()> {
    #[cfg(target_os = "macos")]
    {
        use std::os::fd::AsRawFd;
        use std::os::unix::ffi::OsStrExt;
        use std::os::unix::fs::OpenOptionsExt;
        unsafe extern "C" {
            fn fclonefileat(
                source: libc::c_int,
                directory: libc::c_int,
                name: *const libc::c_char,
                flags: u32,
            ) -> libc::c_int;
        }
        let parent = destination.parent().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "clone destination has no parent",
            )
        })?;
        let name = destination.file_name().ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidInput, "clone destination has no name")
        })?;
        let name = std::ffi::CString::new(name.as_bytes()).map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "clone destination contains NUL",
            )
        })?;
        let directory = fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(parent)?;
        if unsafe { fclonefileat(source.as_raw_fd(), directory.as_raw_fd(), name.as_ptr(), 0) } != 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (source, destination);
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "current sources require APFS clone support",
        ))
    }
}

/// Receipt/status access does not open or create the cache, including on cold start.
#[derive(Clone)]
pub struct ReceiptReader {
    locks: CheckoutLocks,
    fs: Arc<RootFs>,
    policy: InstallPolicy,
    reserved: Claims,
}
#[derive(Clone)]
pub struct CheckoutInstaller {
    reader: ReceiptReader,
    objects: ObjectStore,
    results: ResultStore,
}
impl std::ops::Deref for CheckoutInstaller {
    type Target = ReceiptReader;
    fn deref(&self) -> &Self::Target {
        &self.reader
    }
}

#[derive(Clone, Debug)]
struct DesiredFile {
    owner: OwnerId,
    output_path: String,
    install_path: String,
    stored: StoredFile,
}

/// Only validated cached/local preparation constructs this pinned plan. Retrying Busy keeps it.
pub struct RestorePlan {
    installer: ReceiptReader,
    completion: Option<PlanCompletion>,
    retained_sources: Option<PlanCompletion>,
    retained_rooted: bool,
    keep_sources: bool,
    result: ResultEnvelope,
    view: OwnershipSnapshot,
    removals: Vec<RemovalIntent>,
    desired: BTreeMap<String, DesiredFile>,
    items: BTreeMap<OwnerId, Item>,
    retention: QuarantineRetention,
}

enum PlanCompletion {
    Cache {
        transaction: WriteTransaction,
        objects: ObjectStore,
    },
    Local(crate::completion::FrozenCompletion),
}

/// A miss retains the original write transaction for dispatch; no second begin/lease.
pub enum RestoreLookup {
    Miss(WriteTransaction),
    Hit(RestorePlan),
}

impl CheckoutInstaller {
    pub fn open(
        checkout: impl AsRef<Path>,
        store: impl AsRef<Path>,
        policy: InstallPolicy,
    ) -> Result<Self, InstallError> {
        let mut reader = ReceiptReader::open(checkout, policy)?;
        let objects = ObjectStore::open(store)
            .map_err(|error| InstallError::Cache(ResultError::Store(error)))?;
        let results = ResultStore::open(objects.root())?;
        if let Ok(relative) = objects.root().strip_prefix(reader.locks.root()) {
            let relative = relative
                .to_str()
                .ok_or_else(|| invalid("in-checkout store path is not UTF-8"))?;
            relative_path(relative, true).map_err(invalid)?;
            reader
                .reserved
                .insert(folded(relative), (relative.into(), "object store".into()));
        }
        reader.ensure_install_layout()?;
        Ok(Self {
            reader,
            objects,
            results,
        })
    }
}

impl ReceiptReader {
    pub fn open(checkout: impl AsRef<Path>, policy: InstallPolicy) -> Result<Self, InstallError> {
        ProjectNamespace::new(policy.project.as_str())?;
        let locks = CheckoutLocks::open(checkout)?;
        let fs = Arc::new(RootFs::open(locks.root())?);
        let mut reserved = Claims::new();
        claim(&mut reserved, ".git", "git metadata").map_err(invalid)?;
        claim(&mut reserved, INSTALL_METADATA, "install metadata/locks").map_err(invalid)?;
        if policy.allowed_install_roots.is_empty() {
            return Err(invalid("no install roots supplied"));
        }
        for root in &policy.allowed_install_roots {
            relative_path(root, true).map_err(invalid)?;
        }
        Ok(Self {
            locks,
            fs,
            policy,
            reserved,
        })
    }
    fn ensure_install_layout(&self) -> Result<(), InstallError> {
        for folder in ["receipts", "transactions", "quarantine"] {
            self.fs
                .mkdirs(&format!("{INSTALL_METADATA}/{folder}"), 0o700)?;
        }
        Ok(())
    }
    pub fn locks(&self) -> &CheckoutLocks {
        &self.locks
    }
    fn guard(&self, guard: &BuildGuard) -> Result<(), InstallError> {
        if guard.root() != self.locks.root() {
            return Err(invalid("build guard belongs to another checkout"));
        }
        Ok(())
    }
    fn output_path(&self, path: &str) -> Result<(), InstallError> {
        relative_path(path, true).map_err(invalid)?;
        if conflict(&self.reserved, path).is_some()
            || !self
                .policy
                .allowed_install_roots
                .iter()
                .any(|root| path.starts_with(&(root.clone() + "/")))
        {
            return Err(invalid(
                "install path is outside allowed roots or overlaps protected metadata",
            ));
        }
        Ok(())
    }
    fn index(&self) -> Result<ReceiptIndex, InstallError> {
        let bytes = match self.fs.read(INDEX) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return Ok(ReceiptIndex::default());
            }
            Err(error) => return Err(error.into()),
        };
        let index: ReceiptIndex = decode(&bytes)?;
        if index.version != RECEIPT_VERSION {
            return Err(recovery("unsupported receipt index"));
        }
        for (owner, receipt) in &index.receipts {
            digest(owner)?;
            digest(receipt)?;
        }
        let mut claims = self.reserved.clone();
        for (path, owner) in &index.paths {
            relative_path(path, true).map_err(invalid)?;
            if path != &folded(path) || !index.receipts.contains_key(owner) {
                return Err(recovery("invalid receipt path owner"));
            }
            claim(&mut claims, path, owner).map_err(recovery)?;
        }
        Ok(index)
    }
    fn receipt(&self, id: &str) -> Result<ItemReceipt, InstallError> {
        digest(id)?;
        let path = format!("{INSTALL_METADATA}/receipts/{id}.json");
        let data = self.fs.read(&path)?;
        if sha256(&data) != id {
            return Err(recovery("receipt content does not match its identity"));
        }
        let receipt: ItemReceipt = decode(&data)?;
        ProjectNamespace::new(receipt.owner.project.as_str())?;
        if receipt.version != RECEIPT_VERSION
            || OwnerId::new(receipt.owner.project.clone(), &receipt.logical_path)? != receipt.owner
            || receipt.class.is_empty()
        {
            return Err(recovery("invalid receipt owner/version/class"));
        }
        digest(&receipt.result_key)?;
        let mut claims = Claims::new();
        for file in &receipt.files {
            relative_path(&file.output_path, true).map_err(invalid)?;
            relative_path(&file.install_path, true).map_err(invalid)?;
            if conflict(&self.reserved, &file.install_path).is_some() {
                return Err(recovery("receipt overlaps protected metadata"));
            }
            claim(&mut claims, &file.install_path, "receipt output").map_err(recovery)?;
            digest(&file.digest)?;
            if ![0o644, 0o755].contains(&file.mode)
                || file.size != file.observation.size
                || file.mode != file.observation.mode
            {
                return Err(recovery("invalid receipt file mode/size"));
            }
        }
        Ok(receipt)
    }

    fn consistent_receipt(
        &self,
        index: &ReceiptIndex,
        owner: &OwnerId,
    ) -> Result<Option<(String, ItemReceipt)>, InstallError> {
        let key = owner.fingerprint()?;
        let Some(id) = index.receipts.get(&key) else {
            return Ok(None);
        };
        let receipt = self.receipt(id)?;
        if &receipt.owner != owner {
            return Err(recovery("receipt index owner mismatch"));
        }
        let recorded: BTreeSet<_> = receipt
            .files
            .iter()
            .map(|f| folded(&f.install_path))
            .collect();
        let indexed: BTreeSet<_> = index
            .paths
            .iter()
            .filter(|(_, v)| *v == &key)
            .map(|(p, _)| p.clone())
            .collect();
        if recorded != indexed {
            return Err(recovery("receipt/index file membership mismatch"));
        }
        Ok(Some((id.clone(), receipt)))
    }

    /// @cc [owner:fontanierh,label:correctness] retirement-authority-before-cache
    /// Retirement namespace/reference/path/source and exact receipt membership/identity MUST
    /// validate without cache access before lookup or dispatch. Authority refusals MUST stay
    /// hard errors; only true cache-origin failures may be softened as Cache. Commit MUST
    /// repeat fresh authority checks under exclusive content custody. See tests/demand.rs
    /// and whole_item_retirement_requires_exact_current_namespaced_receipt_authority.
    pub fn preflight_removals(
        &self,
        guard: &BuildGuard,
        view: &OwnershipSnapshot,
        removals: &[RemovalIntent],
    ) -> Result<(), InstallError> {
        self.guard(guard)?;
        if removals.is_empty() {
            return Ok(());
        }
        if !view.projects.contains(&self.policy.project) {
            return Err(invalid("missing complete project ownership view"));
        }
        for removal in removals {
            if removal.owner.project != self.policy.project
                || view.owners.contains_key(&removal.owner)
                || view.references.contains(&removal.owner)
            {
                return Err(invalid(
                    "removal belongs to another project or a live owner/reference",
                ));
            }
            ObjectDigest::from_hex(&removal.expected_receipt_id)
                .map_err(|_| invalid("invalid retirement receipt identity"))?;
            for path in &removal.exact_paths {
                self.output_path(path)?;
                if conflict(&view.sources, path).is_some() {
                    return Err(invalid("removal would delete a declared source/code path"));
                }
            }
        }
        let _reader = self.locks.try_read_content()?;
        let index = self.index()?;
        let mut owners = BTreeSet::new();
        for removal in removals {
            if !owners.insert(removal.owner.clone()) {
                return Err(invalid("duplicate retirement owner"));
            }
            let Some((id, receipt)) = self.consistent_receipt(&index, &removal.owner)? else {
                return Err(invalid("retirement has no owned receipt"));
            };
            if id != removal.expected_receipt_id
                || receipt
                    .files
                    .iter()
                    .map(|file| file.install_path.clone())
                    .collect::<BTreeSet<_>>()
                    != removal.exact_paths
            {
                return Err(invalid("stale or incomplete retirement authority"));
            }
        }
        Ok(())
    }

    pub fn receipt_status(
        &self,
        guard: &BuildGuard,
        unit: &PreparedUnit,
    ) -> Result<CurrentStatus, InstallError> {
        self.guard(guard)?;
        let _reader = self.locks.try_read_content()?;
        self.current_locked(unit)
    }

    /// @cc [owner:fontanierh,label:correctness;safety] current-identity-observation-releases-custody
    /// Identity observation MUST reuse complete Current validation and retain no guard or FD.
    /// Returning metadata MUST NOT certify future byte availability; staging separately reacquires
    /// and revalidates CurrentSources. See current_sources_pin_without_cache_and_clone_only_certified_unchanged_items.
    pub fn current_identities(
        &self,
        guard: &BuildGuard,
        unit: &PreparedUnit,
    ) -> Result<Option<CurrentIdentities>, InstallError> {
        self.guard(guard)?;
        let _read = self.locks.try_read_content()?;
        let CurrentStatus::Current(receipts) = self.current_locked(unit)? else {
            return Ok(None);
        };
        let mut items = vec![];
        for item in unit
            .ingredients()
            .logical_outputs
            .iter()
            .filter(|item| item.destination == Destination::Checkout)
        {
            let owner = OwnerId::new(self.policy.project.clone(), &item.logical_path)?;
            let receipt = receipts
                .iter()
                .find(|receipt| receipt.owner == owner)
                .ok_or_else(|| invalid("missing certified current item"))?;
            items.push(StoredItem {
                item: item.clone(),
                files: receipt
                    .files
                    .iter()
                    .map(|file| StoredFile {
                        path: file.output_path.clone(),
                        digest: file.digest.clone(),
                        size: file.size,
                        mode: file.mode,
                    })
                    .collect(),
                external_locator: None,
            });
        }
        Ok(Some(CurrentIdentities {
            key: unit.key().into(),
            items,
        }))
    }

    fn plan_owned(
        &self,
        result: &ResultEnvelope,
        view: &OwnershipSnapshot,
    ) -> Result<(BTreeMap<String, DesiredFile>, BTreeMap<OwnerId, Item>), InstallError> {
        let mut desired = BTreeMap::new();
        let mut items = BTreeMap::new();
        for stored in &result.result.outputs {
            if stored.item.destination != Destination::Checkout {
                continue;
            }
            let owner = OwnerId::new(self.policy.project.clone(), &stored.item.logical_path)?;
            let definition = view.owners.get(&owner).ok_or_else(|| {
                invalid("result logical owner is absent from current declaration")
            })?;
            if definition.class != stored.item.class {
                return Err(invalid("result class differs from declared owner"));
            }
            let declared_files: BTreeMap<_, _> = stored
                .item
                .files
                .iter()
                .map(|file| {
                    Ok((
                        file.path.clone(),
                        (
                            file.install_path
                                .clone()
                                .ok_or_else(|| invalid("missing output mapping"))?,
                            file.required,
                        ),
                    ))
                })
                .collect::<Result<_, InstallError>>()?;
            if declared_files != definition.files {
                return Err(invalid(
                    "result complete mapping differs from current declaration",
                ));
            }
            for file in &stored.files {
                let declared = stored
                    .item
                    .files
                    .iter()
                    .find(|expected| expected.path == file.path)
                    .ok_or_else(|| invalid("unknown saved output"))?;
                let path = declared
                    .install_path
                    .clone()
                    .ok_or_else(|| invalid("missing output install mapping"))?;
                if definition.files.get(&file.path) != Some(&(path.clone(), declared.required)) {
                    return Err(invalid("result mapping differs from current declaration"));
                }
                self.output_path(&path)?;
                if conflict(&view.sources, &path).is_some() {
                    return Err(invalid(
                        "install would overwrite a declared source/code path",
                    ));
                }
                if desired
                    .insert(
                        folded(&path),
                        DesiredFile {
                            owner: owner.clone(),
                            output_path: file.path.clone(),
                            install_path: path,
                            stored: file.clone(),
                        },
                    )
                    .is_some()
                {
                    return Err(invalid("duplicate desired output"));
                }
            }
            items.insert(owner, stored.item.clone());
        }
        Ok((desired, items))
    }

    /// Prepare a validated local result without opening a cache. No available-cache token is minted.
    pub fn prepare_local(
        &self,
        guard: &BuildGuard,
        completion: crate::completion::FrozenCompletion,
        view: &OwnershipSnapshot,
        removals: Vec<RemovalIntent>,
    ) -> Result<RestorePlan, InstallError> {
        self.guard(guard)?;
        if !view.projects.contains(&self.policy.project) {
            return Err(invalid("missing complete project ownership view"));
        }
        self.preflight_removals(guard, view, &removals)?;
        if completion.refused {
            return Err(invalid(
                "local completion refused semantic publication conflict",
            ));
        }
        let result = completion.result().clone();
        let (desired, items) = self.plan_owned(&result, view)?;
        // A saved same-key receipt is evidence of previously produced content, even when edited.
        let _read = self.locks.try_read_content()?;
        let index = self.index()?;
        self.check_local_history(&result, &index)?;
        let retention = QuarantineRetention {
            owner: completion.lease().owner.clone(),
            workers: completion.lease().workers.clone(),
            result_key: result.result.key.clone(),
            object_digests: result.files().map(|file| file.digest.clone()).collect(),
            upstream_result_keys: result.upstream_result_keys.clone(),
        };
        Ok(RestorePlan {
            installer: self.clone(),
            completion: Some(PlanCompletion::Local(completion)),
            retained_sources: None,
            retained_rooted: false,
            keep_sources: false,
            result,
            view: view.clone(),
            removals,
            desired,
            items,
            retention,
        })
    }

    fn check_local_history(
        &self,
        result: &ResultEnvelope,
        index: &ReceiptIndex,
    ) -> Result<(), InstallError> {
        for stored in &result.result.outputs {
            if stored.item.destination != Destination::Checkout {
                continue;
            }
            let owner = OwnerId::new(self.policy.project.clone(), &stored.item.logical_path)?;
            if let Some((_, receipt)) = self.consistent_receipt(&index, &owner)? {
                let mut saved: Vec<_> = receipt
                    .files
                    .iter()
                    .map(|file| StoredFile {
                        path: file.output_path.clone(),
                        digest: file.digest.clone(),
                        size: file.size,
                        mode: file.mode,
                    })
                    .collect();
                let mut produced = stored.files.clone();
                saved.sort_by(|a, b| a.path.cmp(&b.path));
                produced.sort_by(|a, b| a.path.cmp(&b.path));
                if receipt.result_key == result.result.key
                    && (saved != produced || receipt.class != stored.item.class)
                {
                    return Err(InstallError::LocalCompletion(ResultError::Nondeterminism(
                        result.result.key.clone(),
                    )));
                }
            }
        }
        Ok(())
    }

    pub fn begin_completion(
        &self,
        guard: &BuildGuard,
        unit: &PreparedUnit,
        identity: LeaseIdentity,
    ) -> Result<crate::completion::CompletionWork, InstallError> {
        self.guard(guard)?;
        let path = format!("{INSTALL_METADATA}/completions");
        self.fs.mkdirs(&path, 0o700)?;
        crate::completion::CompletionWork::begin(&self.fs.absolute(&path), unit, identity)
            .map_err(InstallError::LocalCompletion)
    }

    /// @cc [owner:fontanierh,label:correctness;safety] sealed-current-source-custody
    /// Current sources MUST use the shared complete receipt/stat validator under read custody,
    /// then pin anchored no-follow regular descriptors matching exact receipt observations.
    /// Issuance MUST NOT open the cache, hash payloads or treat public receipt data as authority.
    /// The read guard and build borrow MUST outlive staging; independent clones need no checkout lock.
    pub fn pin_current_sources<'build>(
        &self,
        guard: &'build BuildGuard,
        unit: &PreparedUnit,
    ) -> Result<Option<CurrentSources<'build>>, InstallError> {
        self.guard(guard)?;
        let read = self.locks.try_read_content()?;
        let CurrentStatus::Current(receipts) = self.current_locked(unit)? else {
            return Ok(None);
        };
        let mut files = BTreeMap::new();
        for receipt in &receipts {
            for expected in &receipt.files {
                let file = self.fs.file(&expected.install_path)?;
                let observation = FileObservation::from_metadata(&file.metadata()?);
                if observation != expected.observation
                    || observation.size != expected.size
                    || observation.mode != expected.mode
                {
                    return Err(invalid("current source changed before pinning"));
                }
                let digest = ObjectDigest::from_hex(&expected.digest)?;
                files
                    .entry(digest)
                    .or_insert(CurrentFile { file, observation });
            }
        }
        Ok(Some(CurrentSources {
            _build: guard,
            _read: read,
            receipts,
            files,
        }))
    }

    fn current_locked(&self, unit: &PreparedUnit) -> Result<CurrentStatus, InstallError> {
        let items: Vec<_> = unit
            .ingredients()
            .logical_outputs
            .iter()
            .filter(|item| item.destination == Destination::Checkout)
            .collect();
        if items.is_empty() {
            return Ok(CurrentStatus::NotMaterialized);
        }
        let index = self.index()?;
        let mut receipts = vec![];
        for item in items {
            let owner = OwnerId::new(self.policy.project.clone(), &item.logical_path)?;
            let Some((_, receipt)) = self.consistent_receipt(&index, &owner)? else {
                return Ok(CurrentStatus::Dirty);
            };
            if receipt.owner != owner
                || receipt.result_key != unit.key()
                || receipt.class != item.class
            {
                return Ok(CurrentStatus::Dirty);
            }
            let mut found = BTreeSet::new();
            for file in &receipt.files {
                if !item.files.iter().any(|expected| {
                    expected.path == file.output_path
                        && expected.install_path.as_ref() == Some(&file.install_path)
                }) || index.paths.get(&folded(&file.install_path)) != Some(&owner.fingerprint()?)
                    || self.fs.observe(&file.install_path)? != Some(file.observation.clone())
                {
                    return Ok(CurrentStatus::Dirty);
                }
                found.insert(file.output_path.clone());
            }
            if item
                .files
                .iter()
                .any(|file| file.required && !found.contains(&file.path))
            {
                return Ok(CurrentStatus::Dirty);
            }
            receipts.push(receipt);
        }
        Ok(CurrentStatus::Current(receipts))
    }
}

impl CheckoutInstaller {
    pub fn prepare_restore(
        &self,
        guard: &BuildGuard,
        unit: &PreparedUnit,
        identity: LeaseIdentity,
        view: &OwnershipSnapshot,
        removals: Vec<RemovalIntent>,
    ) -> Result<Option<RestorePlan>, InstallError> {
        match self.lookup_restore(guard, unit, identity, view, removals)? {
            RestoreLookup::Miss(_transaction) => Ok(None),
            RestoreLookup::Hit(plan) => Ok(Some(plan)),
        }
    }

    /// Potential materialization uses one lookup. A miss carries its lease into dispatch.
    /// The compatibility prepare_restore wrapper conservatively drops a miss transaction.
    pub fn lookup_restore(
        &self,
        guard: &BuildGuard,
        unit: &PreparedUnit,
        identity: LeaseIdentity,
        view: &OwnershipSnapshot,
        removals: Vec<RemovalIntent>,
    ) -> Result<RestoreLookup, InstallError> {
        self.guard(guard)?;
        if !view.projects.contains(&self.policy.project) {
            return Err(invalid("missing complete project ownership view"));
        }
        self.preflight_removals(guard, view, &removals)?;
        let mut retention = QuarantineRetention {
            owner: identity.owner.clone(),
            workers: identity.workers.clone(),
            result_key: unit.key().into(),
            object_digests: BTreeSet::new(),
            upstream_result_keys: identity.upstream_result_keys.clone(),
        };
        let mut transaction = self.results.begin(
            unit,
            identity.provenance,
            identity.owner,
            identity.workers,
            identity.upstream_result_keys,
        )?;
        let Some(result) = transaction.lookup()? else {
            return Ok(RestoreLookup::Miss(transaction));
        };
        retention
            .object_digests
            .extend(result.files().map(|file| file.digest.clone()));
        retention
            .upstream_result_keys
            .extend(result.upstream_result_keys.iter().cloned());
        let (desired, items) = self.plan_owned(&result, view)?;
        Ok(RestoreLookup::Hit(RestorePlan {
            installer: self.reader.clone(),
            completion: Some(PlanCompletion::Cache {
                transaction,
                objects: self.objects.clone(),
            }),
            retained_sources: None,
            retained_rooted: false,
            keep_sources: false,
            result,
            view: view.clone(),
            removals,
            desired,
            items,
            retention,
        }))
    }
}

/// Named filesystem transitions for fault injection, never successful stamps.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InstallEvent {
    JournalCreated,
    /// Clone returned, but its inode has not yet been observed and durably recorded.
    CloneCreated(usize),
    FileStaged(usize),
    Ready,
    OldMoved(usize),
    NewMoved(usize),
    ReceiptsReady,
    IndexCommitted,
    Cleanup(CleanupEvent),
    CleanupComplete,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CleanupEvent {
    Leaf(usize),
    Directory(usize),
    BarrierCleared,
}

#[derive(Debug)]
pub enum InstallOutcome {
    Installed,
    /// Checkout receipts are committed. B2 keeps its lease when rooting fails.
    InstalledWithRootPending(String),
    /// Receipt/index publication succeeded from validated local snapshots; CAS availability is unclaimed.
    /// Local evidence and its owner lease remain; retention failure never invalidates installed bytes.
    InstalledLocally {
        retention_error: Option<String>,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RecoveryEvent {
    AbortIntentDurable,
    JournalArchived,
    ScopeQuarantined,
    ReaderBarrierCleared,
    Cleanup(CleanupEvent),
}

/// Quarantine owns independent staging artifacts/evidence, not a successful result/root.
/// B2's failed-transaction lease is unchanged; its ordinary liveness policy remains B5's.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct QuarantineRetention {
    owner: ProcessIdentity,
    workers: Vec<ProcessIdentity>,
    result_key: String,
    object_digests: BTreeSet<String>,
    upstream_result_keys: BTreeSet<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct AbortIntent {
    quarantine: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct JournalEntry {
    old_path: Option<String>,
    old: Option<FileObservation>,
    destination: String,
    stage: String,
    trash: String,
    new: Option<StoredFile>,
    staged: Option<FileObservation>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct InstallJournal {
    version: u32,
    project: ProjectNamespace,
    scope: String,
    old_index: ReceiptIndex,
    after_index: Option<ReceiptIndex>,
    ready: bool,
    entries: Vec<JournalEntry>,
    directories: Vec<CreatedDirectory>,
    retention: QuarantineRetention,
    abort: Option<AbortIntent>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct JournalRecord {
    digest: String,
    journal: InstallJournal,
}

impl ReceiptReader {
    fn reserve_scope(
        &self,
        mut next: impl FnMut() -> u64,
    ) -> Result<(String, CreatedDirectory), InstallError> {
        loop {
            let serial = next();
            let scope = format!(
                "{INSTALL_METADATA}/transactions/{}-{serial}",
                std::process::id()
            );
            let quarantine = format!(
                "{INSTALL_METADATA}/quarantine/{}-{serial}",
                std::process::id()
            );
            // A restarted/reused PID must not select a scope whose preserved abort
            // destination already exists. Every occupied entry, including links, reserves it.
            if self.fs.occupied(&quarantine)? {
                continue;
            }
            match self.fs.create_directory(&scope, 0o700) {
                Ok(directory) => return Ok((scope, directory)),
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error.into()),
            }
        }
    }
    fn journal_present(&self) -> Result<bool, InstallError> {
        match fs::symlink_metadata(self.fs.absolute(JOURNAL)) {
            Ok(_) => Ok(true),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
            Err(error) => Err(error.into()),
        }
    }
    fn save_journal(&self, journal: &InstallJournal) -> Result<(), InstallError> {
        let record = JournalRecord {
            digest: sha256(&bytes(journal)?),
            journal: journal.clone(),
        };
        self.fs.replace_metadata(JOURNAL, &bytes(&record)?)?;
        Ok(())
    }
    fn load_journal(&self, view: &OwnershipSnapshot) -> Result<InstallJournal, InstallError> {
        let record: JournalRecord = decode(&self.fs.read(JOURNAL)?)?;
        let journal = record.journal;
        if record.digest != sha256(&bytes(&journal)?)
            || journal.version != JOURNAL_VERSION
            || journal.project != self.policy.project
            || !view.projects.contains(&journal.project)
        {
            return Err(recovery("journal identity/version/project mismatch"));
        }
        for index in std::iter::once(&journal.old_index).chain(journal.after_index.iter()) {
            if index.version != RECEIPT_VERSION {
                return Err(recovery("unsupported journal receipt index"));
            }
            let mut claims = self.reserved.clone();
            for (owner, receipt) in &index.receipts {
                digest(owner)?;
                digest(receipt)?;
            }
            for (path, owner) in &index.paths {
                relative_path(path, true).map_err(recovery)?;
                if folded(path) != *path || !index.receipts.contains_key(owner) {
                    return Err(recovery("invalid journal receipt ownership"));
                }
                claim(&mut claims, path, owner).map_err(recovery)?;
            }
        }
        if journal.after_index.is_some() && !journal.ready {
            return Err(recovery("unready journal has committed receipts"));
        }
        digest(&journal.retention.result_key)?;
        for digest_value in journal
            .retention
            .object_digests
            .iter()
            .chain(journal.retention.upstream_result_keys.iter())
        {
            digest(digest_value)?;
        }
        for process in
            std::iter::once(&journal.retention.owner).chain(journal.retention.workers.iter())
        {
            if process.pid == 0
                || process.boot.trim().is_empty()
                || process.started.trim().is_empty()
            {
                return Err(recovery("invalid quarantine custody identity"));
            }
        }
        let prefix = format!("{INSTALL_METADATA}/transactions/");
        let serial = journal
            .scope
            .strip_prefix(&prefix)
            .ok_or_else(|| recovery("foreign journal scope"))?;
        if serial.is_empty()
            || serial.contains('/')
            || !serial.bytes().all(|b| b.is_ascii_digit() || b == b'-')
        {
            return Err(recovery("invalid transaction scope"));
        }
        if let Some(abort) = &journal.abort {
            if journal.ready
                || abort.quarantine != format!("{INSTALL_METADATA}/quarantine/{serial}")
            {
                return Err(recovery("invalid pre-install abort intent"));
            }
        }
        if journal
            .directories
            .iter()
            .filter(|directory| directory.path == journal.scope)
            .count()
            != 1
        {
            return Err(recovery("missing unique pre-owned scope identity"));
        }
        let mut claims = Claims::new();
        for (i, entry) in journal.entries.iter().enumerate() {
            self.output_path(&entry.destination)?;
            if conflict(&view.sources, &entry.destination).is_some() {
                return Err(recovery("journal destination is now source/code"));
            }
            claim(&mut claims, &entry.destination, "journal output").map_err(recovery)?;
            if let Some(old) = &entry.old_path {
                self.output_path(old)?;
                if folded(old) != folded(&entry.destination)
                    || conflict(&view.sources, old).is_some()
                {
                    return Err(recovery("journal old output is foreign or now source/code"));
                }
            }
            if entry.old.is_some() && entry.old_path.is_none()
                || entry.stage != format!("{}/new/{i}", journal.scope)
                || entry.trash != format!("{}/trash/{i}", journal.scope)
                || entry.staged.is_some() && entry.new.is_none()
                || journal.ready && entry.new.is_some() && entry.staged.is_none()
            {
                return Err(recovery("invalid journal entry"));
            }
            if let Some(file) = &entry.new {
                digest(&file.digest)?;
                if ![0o644, 0o755].contains(&file.mode) {
                    return Err(recovery("invalid staged mode"));
                }
                if let Some(staged) = &entry.staged {
                    if staged.size != file.size || staged.mode != file.mode {
                        return Err(recovery("invalid staged observation"));
                    }
                }
            }
        }
        for directory in &journal.directories {
            relative_path(&directory.path, true).map_err(recovery)?;
            let private = directory.path == journal.scope
                || directory.path.starts_with(&(journal.scope.clone() + "/"));
            let output_parent = journal
                .entries
                .iter()
                .any(|e| e.destination.starts_with(&(directory.path.clone() + "/")));
            if !private && !output_parent {
                return Err(recovery("foreign directory cleanup intent"));
            }
        }
        Ok(journal)
    }

    /// @cc [owner:fontanierh,label:correctness;safety] recover-owned-checkout-install
    /// Recovery MUST hold build and exclusive content custody. Before the receipt-index commit
    /// it MUST restore the prior owned bytes; after commit it MUST finish only exact owned cleanup.
    /// Unknown checkout leaves, unproved scope identities and newly declared source paths MUST refuse.
    /// No output-directory discovery, payload hashing, cache mutation or process launch is permitted.
    pub fn recover(
        &self,
        guard: &BuildGuard,
        view: &OwnershipSnapshot,
    ) -> Result<(), InstallError> {
        self.recover_with(guard, view, |_| Ok(()))
    }

    pub fn recover_with(
        &self,
        guard: &BuildGuard,
        view: &OwnershipSnapshot,
        mut event: impl FnMut(RecoveryEvent) -> io::Result<()>,
    ) -> Result<(), InstallError> {
        self.guard(guard)?;
        let _writer = guard.try_write_content()?;
        if !self.journal_present()? {
            return Ok(());
        }
        let mut journal = self.load_journal(view)?;
        let index = self.index()?;
        let committed = journal.after_index.as_ref() == Some(&index);
        if !committed && index != journal.old_index {
            return Err(recovery("receipt index changed outside journal"));
        }
        if !journal.ready {
            return self.abort_preinstall(&mut journal, &mut event);
        }
        if !committed {
            self.rollback(&journal)?;
        }
        self.cleanup_journal(&journal, committed, &mut |step| {
            event(RecoveryEvent::Cleanup(step))
        })
    }

    fn preinstall_unchanged(
        &self,
        journal: &InstallJournal,
        scope: &str,
    ) -> Result<(), InstallError> {
        if journal.ready || journal.after_index.is_some() || self.index()? != journal.old_index {
            return Err(recovery("pre-install abort index/phase changed"));
        }
        for entry in &journal.entries {
            if let Some(path) = &entry.old_path {
                if self.fs.observe(path)? != entry.old {
                    return Err(recovery("pre-install old output changed"));
                }
            }
            let destination = self.fs.observe(&entry.destination)?;
            let same_name = entry.old_path.as_deref() == Some(entry.destination.as_str());
            if destination != entry.old && (same_name || destination.is_some()) {
                return Err(recovery("pre-install destination changed"));
            }
            let trash = entry
                .trash
                .strip_prefix(&(journal.scope.clone() + "/"))
                .ok_or_else(|| recovery("foreign abort trash"))?;
            if self.fs.observe(&format!("{scope}/{trash}"))?.is_some() {
                return Err(recovery("unready journal has moved prior output"));
            }
        }
        Ok(())
    }

    /// @cc [owner:fontanierh,label:correctness;safety] preinstall-owned-scope-abort
    /// Only an unready journal with unchanged prior index, exact old output observations,
    /// absent trash and the pre-owned directory identity MAY abort by quarantine. Persist
    /// abort intent and exact journal archive, rename the directory without replacement and
    /// fsync both parents, then recheck all preconditions/evidence before clearing readers.
    /// Preserve every unknown private leaf and failed B2 lease; never adopt/delete/hash/scan it.
    /// Quarantine artifact cleanup and ordinary dead-producer CAS retention remain separate.
    /// See preinstall_abort_preserves_unknown_clone_and_resumes_every_durable_cut and
    /// preinstall_abort_rejects_changed_outputs_trash_and_replaced_directory_identities in tests/installs.rs.
    fn abort_preinstall(
        &self,
        journal: &mut InstallJournal,
        event: &mut impl FnMut(RecoveryEvent) -> io::Result<()>,
    ) -> Result<(), InstallError> {
        let expected = journal
            .directories
            .iter()
            .find(|directory| directory.path == journal.scope)
            .unwrap()
            .clone();
        let serial = journal.scope.rsplit('/').next().unwrap();
        let target = format!("{INSTALL_METADATA}/quarantine/{serial}");
        let matches = |directory: &CreatedDirectory| {
            directory.device == expected.device && directory.inode == expected.inode
        };
        let source = self.fs.directory_identity(&journal.scope)?;
        let destination = self.fs.directory_identity(&target)?;
        let current_scope = match (&source, &destination) {
            (Some(source), None) if matches(source) => journal.scope.clone(),
            (None, Some(destination)) if journal.abort.is_some() && matches(destination) => {
                target.clone()
            }
            _ => {
                return Err(recovery(
                    "pre-install scope identity or quarantine namespace changed",
                ));
            }
        };
        self.preinstall_unchanged(journal, &current_scope)?;
        if journal.abort.is_none() {
            journal.abort = Some(AbortIntent {
                quarantine: target.clone(),
            });
            self.save_journal(journal)?;
            event(RecoveryEvent::AbortIntentDurable)?;
        }
        let record = JournalRecord {
            digest: sha256(&bytes(journal)?),
            journal: journal.clone(),
        };
        let archived = bytes(&record)?;
        if self.fs.read(JOURNAL)? != archived {
            return Err(recovery("active abort journal changed"));
        }
        let archive = format!("{current_scope}/journal.json");
        if current_scope == journal.scope {
            // Only journal-named candidates, no discovery or content reads. Fsync preserves
            // an unobserved clone without adopting/certifying it as a result or owned leaf.
            for entry in &journal.entries {
                match self.fs.file(&entry.stage) {
                    Ok(file) => file.sync_all()?,
                    Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                    Err(error) => return Err(error.into()),
                }
            }
            self.fs.sync_directory(&format!("{}/new", journal.scope))?;
            match self.fs.publish_metadata(&archive, &archived) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                    if self.fs.read(&archive)? != archived {
                        return Err(recovery("foreign journal archive"));
                    }
                }
                Err(error) => return Err(error.into()),
            }
            event(RecoveryEvent::JournalArchived)?;
            if !self
                .fs
                .directory_identity(&journal.scope)?
                .is_some_and(|directory| matches(&directory))
            {
                return Err(recovery("pre-install scope replaced before quarantine"));
            }
            self.fs.rename_exclusive(&journal.scope, &target)?;
            event(RecoveryEvent::ScopeQuarantined)?;
        }
        if !self
            .fs
            .directory_identity(&target)?
            .is_some_and(|directory| matches(&directory))
            || self.fs.read(&format!("{target}/journal.json"))? != archived
            || self.fs.read(JOURNAL)? != archived
        {
            return Err(recovery("quarantine evidence changed"));
        }
        self.preinstall_unchanged(journal, &target)?;
        let observation = self
            .fs
            .observe(JOURNAL)?
            .ok_or_else(|| recovery("active abort barrier disappeared"))?;
        self.fs.remove_owned(JOURNAL, &observation)?;
        event(RecoveryEvent::ReaderBarrierCleared)?;
        Ok(())
    }

    fn rollback(&self, journal: &InstallJournal) -> Result<(), InstallError> {
        // Reverse the exact leaf moves. File contents are never read or copied.
        for entry in journal.entries.iter().rev() {
            let destination = self.fs.observe(&entry.destination)?;
            if let Some(actual) = destination {
                if entry
                    .staged
                    .as_ref()
                    .is_some_and(|new| actual.same_payload(new))
                {
                    self.fs.remove_owned(&entry.destination, &actual)?;
                } else if !entry
                    .old
                    .as_ref()
                    .is_some_and(|old| actual.same_payload(old))
                {
                    return Err(recovery("rollback destination replaced by unknown file"));
                }
            }
            if let (Some(old), Some(path)) = (&entry.old, &entry.old_path) {
                if let Some(trash) = self.fs.observe(&entry.trash)? {
                    if !trash.same_payload(old) {
                        return Err(recovery("rollback trash was replaced"));
                    }
                    if self.fs.observe(path)?.is_some() {
                        return Err(recovery("rollback old name is occupied"));
                    }
                    self.fs.rename_exclusive(&entry.trash, path)?;
                } else if !self
                    .fs
                    .observe(path)?
                    .is_some_and(|actual| actual.same_payload(old))
                {
                    return Err(recovery("rollback prior bytes missing"));
                }
            }
        }
        Ok(())
    }

    fn cleanup_journal(
        &self,
        journal: &InstallJournal,
        committed: bool,
        event: &mut impl FnMut(CleanupEvent) -> io::Result<()>,
    ) -> Result<(), InstallError> {
        // Validate the complete committed set before retiring any prior-byte evidence.
        if committed {
            for entry in &journal.entries {
                match (
                    &entry.new,
                    &entry.staged,
                    self.fs.observe(&entry.destination)?,
                ) {
                    (Some(_), Some(expected), Some(actual)) if actual.same_payload(expected) => {}
                    (None, _, None) => {}
                    _ => return Err(recovery("committed output disappeared or changed identity")),
                }
            }
        }
        for (i, entry) in journal.entries.iter().enumerate() {
            for (leaf_index, (path, expected)) in [
                (&entry.stage, entry.staged.as_ref()),
                (&entry.trash, entry.old.as_ref()),
            ]
            .into_iter()
            .enumerate()
            {
                if let Some(actual) = self.fs.observe(path)? {
                    let expected = expected.ok_or_else(|| {
                        recovery("unrecorded staging leaf; preserve for investigation")
                    })?;
                    if !actual.same_payload(expected) {
                        return Err(recovery("cleanup leaf replaced"));
                    }
                    self.fs.remove_owned(path, expected)?;
                    event(CleanupEvent::Leaf(i * 2 + leaf_index))?;
                }
            }
        }
        for (i, directory) in journal.directories.iter().rev().enumerate() {
            let private = directory.path == journal.scope
                || directory.path.starts_with(&(journal.scope.clone() + "/"));
            // Output parents legitimately contain installed/foreign neighbors. An owned
            // private scope must actually be empty before its sole journal barrier clears.
            match self.fs.remove_empty_directory(directory, !private) {
                Ok(()) => {}
                Err(error) if private && error.kind() == io::ErrorKind::DirectoryNotEmpty => {
                    return Err(recovery(format!(
                        "private transaction directory {} contains unknown leaves",
                        directory.path
                    )));
                }
                Err(error) => return Err(error.into()),
            }
            event(CleanupEvent::Directory(i))?;
        }
        let observation = self
            .fs
            .observe(JOURNAL)?
            .ok_or_else(|| recovery("journal disappeared"))?;
        self.fs.remove_owned(JOURNAL, &observation)?;
        event(CleanupEvent::BarrierCleared)?;
        Ok(())
    }
}

impl RestorePlan {
    pub fn result(&self) -> &ResultEnvelope {
        &self.result
    }

    /// Borrow the sealed local completion after successful local installation.
    pub fn local_completion(&self) -> Option<&crate::completion::FrozenCompletion> {
        match &self.retained_sources {
            Some(PlanCompletion::Local(completion)) => Some(completion),
            _ => None,
        }
    }

    /// Borrow only already-pinned cached sources, before commit or after an opted-in commit.
    pub fn cached_sources(&self) -> Option<crate::results::SelectedItems<'_>> {
        match self.completion.as_ref().or(self.retained_sources.as_ref()) {
            Some(PlanCompletion::Cache { transaction, .. }) => Some(transaction.pinned_objects()),
            _ => None,
        }
    }

    /// Retain cached source claims after durable installation/rooting for downstream staging.
    /// Normal commit still releases per-unit claims. Dropping retained custody conservatively
    /// preserves claims; finish_sources releases only after durable rooting succeeds.
    pub fn commit_with_sources(
        &mut self,
        guard: &BuildGuard,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<InstallOutcome, InstallError> {
        self.keep_sources = true;
        let result = self.commit(guard, root);
        self.keep_sources = false;
        result
    }

    pub fn finish_sources(
        &mut self,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<(), InstallError> {
        if let Some(PlanCompletion::Cache { transaction, .. }) = self.retained_sources.as_mut() {
            if !self.retained_rooted {
                root(&self.result).map_err(|reason| {
                    InstallError::Cache(crate::results::ResultError::Root(reason))
                })?;
                self.retained_rooted = true;
            }
            transaction.release_sources().map_err(InstallError::Cache)?;
            self.retained_sources = None;
        }
        Ok(())
    }

    /// Root a pinned cached result used only as metadata, without installing its files.
    pub fn retain_cached(
        mut self,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<ResultEnvelope, InstallError> {
        match self
            .completion
            .take()
            .ok_or_else(|| invalid("restore plan already consumed"))?
        {
            PlanCompletion::Cache { transaction, .. } => {
                transaction.retain_hit(root).map_err(InstallError::Cache)
            }
            PlanCompletion::Local(_) => Err(invalid("local result is not a cached hit")),
        }
    }

    pub fn commit(
        &mut self,
        guard: &BuildGuard,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<InstallOutcome, InstallError> {
        self.commit_with(guard, |_| Ok(()), root)
    }

    /// @cc [owner:fontanierh,label:correctness;safety] checkout-install-transaction
    /// Install MUST retain certified source custody, acquire build/exclusive content custody and durably journal
    /// exact old/new leaf ownership before staging or mutation. It MUST clone named CAS objects or sealed local snapshots,
    /// apply recorded normalized modes and publish complete per-project receipts before cleanup.
    /// Existing foreign files, other projects and declared code/sources MUST never be overwritten.
    /// Faults preserve recovery evidence and cache leases; successful later rooting releases claims.
    /// Busy before journal creation is a precondition refusal, not a journaled transaction failure:
    /// healthy shared readers remain allowed. An injected pre-index failure after JournalCreated
    /// MUST preserve the reader barrier until recovery. Fault tests MUST establish the exact cut was reached, not
    /// merely accept any error. See busy_before_install_start_is_distinct_from_a_journaled_failure_and_recovery
    /// and interrupted_local_install_retains_completion_and_uses_existing_quarantine_recovery.
    /// No fallback copy, payload rehash, tree walk or inferred prefix ownership is permitted.
    pub fn commit_with(
        &mut self,
        guard: &BuildGuard,
        mut event: impl FnMut(InstallEvent) -> io::Result<()>,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> Result<InstallOutcome, InstallError> {
        let installer = &self.installer;
        installer.guard(guard)?;
        if self.completion.is_none() {
            return Err(invalid("restore plan already consumed"));
        }
        let _writer = guard.try_write_content()?;
        if installer.journal_present()? {
            return Err(recovery("prior journal requires recovery"));
        }
        if self.items.is_empty() && self.removals.is_empty() {
            return Ok(self.finish_root(root));
        }
        installer.ensure_install_layout()?;
        let before = installer.index()?;
        if matches!(self.completion.as_ref(), Some(PlanCompletion::Local(_))) {
            installer.check_local_history(&self.result, &before)?;
        }
        let (mut journal, affected) = self.plan_journal(before)?;
        installer.save_journal(&journal)?;
        event(InstallEvent::JournalCreated)?;
        for i in 0..journal.entries.len() {
            let entry = &mut journal.entries[i];
            if let Some(stored) = &entry.new {
                let digest = ObjectDigest::from_hex(&stored.digest)?;
                let destination = installer.fs.absolute(&entry.stage);
                match self.completion.as_ref().unwrap() {
                    PlanCompletion::Cache { objects, .. } => {
                        objects.clone_to(&digest, &destination)?
                    }
                    PlanCompletion::Local(completion) => {
                        completion.clone_to(&digest, &destination)?
                    }
                }
                event(InstallEvent::CloneCreated(i))?;
                let file = installer.fs.file(&entry.stage)?;
                file.set_permissions(fs::Permissions::from_mode(stored.mode))?;
                file.sync_all()?;
                entry.staged = Some(FileObservation::from_metadata(&file.metadata()?));
                if entry.staged.as_ref().unwrap().size != stored.size {
                    return Err(recovery("staged object size changed"));
                }
                installer.save_journal(&journal)?;
                event(InstallEvent::FileStaged(i))?;
            }
        }
        journal.ready = true;
        installer.save_journal(&journal)?;
        event(InstallEvent::Ready)?;
        for i in 0..journal.entries.len() {
            let entry = journal.entries[i].clone();
            if let Some(path) = &entry.old_path {
                if let Some(expected) = &entry.old {
                    let actual = installer
                        .fs
                        .observe(path)?
                        .ok_or_else(|| recovery("old output disappeared"))?;
                    if actual != *expected {
                        return Err(recovery("old output changed after preflight"));
                    }
                    installer.fs.rename_exclusive(path, &entry.trash)?;
                    event(InstallEvent::OldMoved(i))?;
                }
            }
            if entry.new.is_some() {
                if let Some((parent, _)) = entry.destination.rsplit_once('/') {
                    journal
                        .directories
                        .extend(installer.fs.mkdirs(parent, 0o755)?);
                    installer.save_journal(&journal)?;
                }
                installer
                    .fs
                    .rename_exclusive(&entry.stage, &entry.destination)?;
                event(InstallEvent::NewMoved(i))?;
            }
        }
        let after = self.receipt_index(&journal, &affected)?;
        journal.after_index = Some(after.clone());
        installer.save_journal(&journal)?;
        event(InstallEvent::ReceiptsReady)?;
        installer.fs.replace_metadata(INDEX, &bytes(&after)?)?;
        event(InstallEvent::IndexCommitted)?;
        installer.cleanup_journal(&journal, true, &mut |step| {
            event(InstallEvent::Cleanup(step))
        })?;
        event(InstallEvent::CleanupComplete)?;
        Ok(self.finish_root(root))
    }

    fn finish_root(
        &mut self,
        root: impl FnOnce(&ResultEnvelope) -> Result<(), String>,
    ) -> InstallOutcome {
        match self.completion.take().unwrap() {
            completion @ PlanCompletion::Cache { .. } if self.keep_sources => {
                let failure = root(&self.result).err();
                self.retained_rooted = failure.is_none();
                self.retained_sources = Some(completion);
                match failure {
                    None => InstallOutcome::Installed,
                    Some(error) => InstallOutcome::InstalledWithRootPending(error),
                }
            }
            PlanCompletion::Cache { transaction, .. } => match transaction.retain_hit(root) {
                Ok(_) => InstallOutcome::Installed,
                Err(error) => InstallOutcome::InstalledWithRootPending(error.to_string()),
            },
            PlanCompletion::Local(mut completion) => {
                let mut lease = completion.work.lease.clone();
                lease.rooted = true;
                lease.result_keys.clear();
                lease.object_digests.clear();
                let failure = completion
                    .work
                    .leases
                    .lock()
                    .and_then(|guard| guard.save(&lease))
                    .err()
                    .map(|e| e.to_string());
                if failure.is_none() {
                    completion.work.lease = lease;
                }
                self.retained_sources = Some(PlanCompletion::Local(completion));
                InstallOutcome::InstalledLocally {
                    retention_error: failure,
                }
            }
        }
    }

    fn plan_journal(
        &self,
        before: ReceiptIndex,
    ) -> Result<(InstallJournal, BTreeSet<OwnerId>), InstallError> {
        let installer = &self.installer;
        let mut affected: BTreeSet<_> = self.items.keys().cloned().collect();
        let mut prior = BTreeMap::new();
        for removal in &self.removals {
            if !affected.insert(removal.owner.clone()) {
                return Err(invalid("duplicate removal or live replacement owner"));
            }
            let Some((id, receipt)) = installer.consistent_receipt(&before, &removal.owner)? else {
                return Err(invalid("removal has no owned receipt"));
            };
            if id != removal.expected_receipt_id
                || receipt
                    .files
                    .iter()
                    .map(|f| f.install_path.clone())
                    .collect::<BTreeSet<_>>()
                    != removal.exact_paths
            {
                return Err(invalid("stale or incomplete removal intent"));
            }
            prior.insert(removal.owner.clone(), receipt);
        }
        for owner in self.items.keys() {
            if let Some((_, receipt)) = installer.consistent_receipt(&before, owner)? {
                prior.insert(owner.clone(), receipt);
            }
        }
        let mut old_files = BTreeMap::new();
        for receipt in prior.values() {
            for file in &receipt.files {
                installer.output_path(&file.install_path)?;
                if conflict(&self.view.sources, &file.install_path).is_some() {
                    return Err(invalid("prior output became declared source/code"));
                }
                if let Some((_, current_owner)) = conflict(&self.view.paths, &file.install_path) {
                    let current_transaction_owners: BTreeSet<_> = self
                        .items
                        .keys()
                        .map(OwnerId::fingerprint)
                        .collect::<Result<_, _>>()?;
                    if current_owner != &receipt.owner.fingerprint()?
                        && !current_transaction_owners.contains(current_owner)
                    {
                        return Err(invalid(
                            "prior output path is now assigned to another current owner",
                        ));
                    }
                }
                if old_files
                    .insert(folded(&file.install_path), file.clone())
                    .is_some()
                {
                    return Err(recovery("duplicate prior file"));
                }
            }
        }
        for (path, new) in &self.desired {
            if let Some(owner) = before.paths.get(path) {
                if !affected
                    .iter()
                    .any(|affected| affected.fingerprint().ok().as_ref() == Some(owner))
                {
                    return Err(invalid("output owned by another logical item/project"));
                }
            }
            if let Some((_, owner)) = conflict(&self.view.paths, &new.install_path) {
                if owner != &new.owner.fingerprint()? {
                    return Err(invalid(
                        "current declaration assigns output to another owner",
                    ));
                }
            }
        }
        let paths: BTreeSet<_> = old_files
            .keys()
            .chain(self.desired.keys())
            .cloned()
            .collect();
        let mut entries = vec![];
        for path in paths {
            let old_file = old_files.get(&path);
            let desired = self.desired.get(&path);
            let destination = desired
                .map(|f| f.install_path.clone())
                .unwrap_or_else(|| old_file.unwrap().install_path.clone());
            let old_path = old_file.map(|f| f.install_path.clone());
            let old = old_path
                .as_ref()
                .map(|p| installer.fs.observe(p))
                .transpose()?
                .flatten();
            if let (Some(receipt), Some(actual)) = (old_file, &old) {
                // A dirty original inode remains managed: preserve its CURRENT bytes/metadata.
                // A replacement inode has no receipt authority, even at a previously owned name.
                if !actual.same_inode(&receipt.observation) {
                    return Err(invalid("prior owned file was replaced by a foreign inode"));
                }
            }
            if let Some(existing) = installer.fs.observe(&destination)? {
                if !old.as_ref().is_some_and(|old| old.same_inode(&existing)) {
                    return Err(invalid("unmanaged or foreign destination file"));
                }
            }
            entries.push(JournalEntry {
                old_path,
                old,
                destination,
                stage: String::new(),
                trash: String::new(),
                new: desired.map(|d| d.stored.clone()),
                staged: None,
            });
        }
        // Scope creation owns only a fresh private directory. No payload precedes the journal.
        let (scope, root_directory) =
            installer.reserve_scope(|| NEXT.fetch_add(1, Ordering::Relaxed))?;
        let mut directories = vec![root_directory];
        directories.extend(installer.fs.mkdirs(&format!("{scope}/new"), 0o700)?);
        directories.extend(installer.fs.mkdirs(&format!("{scope}/trash"), 0o700)?);
        for (i, entry) in entries.iter_mut().enumerate() {
            entry.stage = format!("{scope}/new/{i}");
            entry.trash = format!("{scope}/trash/{i}");
        }
        Ok((
            InstallJournal {
                version: JOURNAL_VERSION,
                project: installer.policy.project.clone(),
                scope,
                old_index: before,
                after_index: None,
                ready: false,
                entries,
                directories,
                retention: self.retention.clone(),
                abort: None,
            },
            affected,
        ))
    }

    fn receipt_index(
        &self,
        journal: &InstallJournal,
        affected: &BTreeSet<OwnerId>,
    ) -> Result<ReceiptIndex, InstallError> {
        let installer = &self.installer;
        let mut after = journal.old_index.clone();
        let fingerprints: BTreeSet<_> = affected
            .iter()
            .map(OwnerId::fingerprint)
            .collect::<Result<_, _>>()?;
        after
            .receipts
            .retain(|owner, _| !fingerprints.contains(owner));
        after.paths.retain(|_, owner| !fingerprints.contains(owner));
        for (owner, item) in &self.items {
            let fingerprint = owner.fingerprint()?;
            let mut files = vec![];
            for desired in self.desired.values().filter(|file| &file.owner == owner) {
                let observation = installer
                    .fs
                    .observe(&desired.install_path)?
                    .ok_or_else(|| recovery("installed file missing before receipt publication"))?;
                let entry = journal
                    .entries
                    .iter()
                    .find(|e| e.destination == desired.install_path)
                    .unwrap();
                if !entry
                    .staged
                    .as_ref()
                    .is_some_and(|expected| expected.same_payload(&observation))
                    || observation.size != desired.stored.size
                    || observation.mode != desired.stored.mode
                {
                    return Err(recovery(
                        "installed file changed before receipt publication",
                    ));
                }
                files.push(ReceiptFile {
                    output_path: desired.output_path.clone(),
                    install_path: desired.install_path.clone(),
                    digest: desired.stored.digest.clone(),
                    size: desired.stored.size,
                    mode: desired.stored.mode,
                    observation,
                });
                if after
                    .paths
                    .insert(folded(&desired.install_path), fingerprint.clone())
                    .is_some()
                {
                    return Err(recovery("receipt path ownership collision"));
                }
            }
            let receipt = ItemReceipt {
                version: RECEIPT_VERSION,
                owner: owner.clone(),
                logical_path: item.logical_path.clone(),
                class: item.class.clone(),
                result_key: self.result.result.key.clone(),
                files,
            };
            let payload = bytes(&receipt)?;
            let id = sha256(&payload);
            let path = format!("{INSTALL_METADATA}/receipts/{id}.json");
            match installer.fs.publish_metadata(&path, &payload) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                    if installer.fs.read(&path)? != payload {
                        return Err(recovery("immutable receipt winner differs"));
                    }
                }
                Err(error) => return Err(error.into()),
            }
            after.receipts.insert(fingerprint, id);
        }
        Ok(after)
    }
}

fn decode<T: serde::de::DeserializeOwned>(bytes: &[u8]) -> Result<T, InstallError> {
    if bytes.iter().find(|byte| !byte.is_ascii_whitespace()) != Some(&b'{') {
        return Err(recovery("install metadata must be an object"));
    }
    serde_json::from_slice(bytes).map_err(|error| recovery(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn scope_allocator_preserves_occupied_transaction_and_quarantine_names() {
        let mut suffix = 0;
        let root = loop {
            let path = std::env::temp_dir()
                .join(format!("atelier-v2-scope-{}-{suffix}", std::process::id()));
            suffix += 1;
            match fs::create_dir(&path) {
                Ok(()) => break path,
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => panic!("{error}"),
            }
        };
        struct OwnedWorkspace(std::path::PathBuf);
        impl Drop for OwnedWorkspace {
            fn drop(&mut self) {
                fs::remove_dir_all(&self.0).unwrap();
            }
        }
        let workspace = OwnedWorkspace(root);
        let installer = CheckoutInstaller::open(
            &workspace.0,
            workspace.0.join("cache"),
            InstallPolicy {
                project: ProjectNamespace::new("fixture").unwrap(),
                allowed_install_roots: vec!["Content".into()],
            },
        )
        .unwrap();
        let name = |folder: &str, n: u64| {
            workspace.0.join(format!(
                "{INSTALL_METADATA}/{folder}/{}-{n}",
                std::process::id()
            ))
        };
        fs::create_dir(name("quarantine", 0)).unwrap();
        fs::write(name("quarantine", 0).join("keep"), b"old evidence").unwrap();
        std::os::unix::fs::symlink("absent", name("quarantine", 1)).unwrap();
        fs::write(name("quarantine", 2), b"foreign namespace").unwrap();
        fs::create_dir(name("transactions", 3)).unwrap();
        fs::write(name("transactions", 3).join("keep"), b"another scope").unwrap();
        let mut candidate = 0;
        let (scope, identity) = installer
            .reserve_scope(|| {
                let n = candidate;
                candidate += 1;
                n
            })
            .unwrap();
        assert_eq!(
            scope,
            format!("{INSTALL_METADATA}/transactions/{}-4", std::process::id())
        );
        assert_eq!(identity.path, scope);
        assert!(workspace.0.join(scope).is_dir());
        assert_eq!(
            fs::read(name("quarantine", 0).join("keep")).unwrap(),
            b"old evidence"
        );
        assert!(
            fs::symlink_metadata(name("quarantine", 1))
                .unwrap()
                .file_type()
                .is_symlink()
        );
        assert_eq!(
            fs::read(name("quarantine", 2)).unwrap(),
            b"foreign namespace"
        );
        assert_eq!(
            fs::read(name("transactions", 3).join("keep")).unwrap(),
            b"another scope"
        );
    }
}
