//! Shared, versioned wire schemas. Strings containing paths or digests are untrusted
//! until the consuming validator checks them; these types do not compute keys.
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const SCHEMA_VERSION: u32 = 1;
pub type Params = BTreeMap<String, serde_json::Value>;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Declaration {
    pub schema_version: u32,
    pub cache_version: String,
    pub units: Vec<Unit>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Op {
    pub kind: String,
    pub version: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Unit {
    pub id: String,
    pub op: Op,
    /// Project-relative script and explicit project code closure (including script).
    pub script: String,
    pub code: Vec<String>,
    #[serde(default)]
    pub inputs: Vec<Input>,
    #[serde(default)]
    pub params: Params,
    pub outputs: Vec<Item>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub conditional: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "role", rename_all = "snake_case", deny_unknown_fields)]
pub enum Input {
    Content {
        name: String,
        source: ContentSource,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        whole: Option<String>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        conditional: Option<String>,
    },
    Reference {
        name: String,
        logical_path: String,
        class: String,
        /// Test identifier proving bytes do not affect the consumer's output.
        proof: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        producer: Option<ItemRef>,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ContentSource {
    File {
        path: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        selector: Option<String>,
        #[serde(default)]
        optional: bool,
    },
    Item {
        unit: String,
        item: String,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ItemRef {
    pub unit: String,
    pub item: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Item {
    pub id: String,
    pub logical_path: String,
    pub class: String,
    /// Complete permitted output set, including explicitly optional sidecars.
    pub files: Vec<OutputFile>,
    pub destination: Destination,
}

fn required_by_default() -> bool {
    true
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OutputFile {
    /// Relative to the job output directory.
    pub path: String,
    /// Relative to checkout root; required for checkout-owned outputs by A2.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub install_path: Option<String>,
    #[serde(default = "required_by_default")]
    pub required: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
pub enum ContentIdentity {
    Absent,
    Digest { digest: String },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Destination {
    Store,
    Checkout,
    /// E.g. Zen-owned cooked data; its adapter defines the locator format.
    External,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResultRecord {
    pub schema_version: u32,
    pub unit: String,
    pub key: String,
    pub ingredients: IdentityIngredients,
    pub outputs: Vec<StoredItem>,
    pub provenance: Provenance,
}

/// Project identities only. Installed tools and dependency lockfiles are not
/// automatic ingredients. Platform invalidation uses explicit cache/op versions.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IdentityIngredients {
    pub cache_version: String,
    pub op: Op,
    pub code: BTreeMap<String, String>,
    pub worker_version: String,
    pub worker_digest: String,
    pub validator_version: String,
    pub validator_digest: String,
    pub params: Params,
    pub content: BTreeMap<String, ContentIdentity>,
    pub references: BTreeMap<String, ReferenceIdentity>,
    pub logical_outputs: Vec<Item>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReferenceIdentity {
    pub logical_path: String,
    pub class: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StoredItem {
    pub item: Item,
    pub files: Vec<StoredFile>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub external_locator: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StoredFile {
    pub path: String,
    pub digest: String,
    pub size: u64,
}

/// Human evidence only; MUST NOT be included in key computation.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    pub checkout: String,
    pub branch: String,
    pub commit: String,
    pub dirty: bool,
    pub built_at: String,
}

pub fn parse_declaration(source: &str) -> Result<Declaration, toml::de::Error> {
    toml::from_str(source)
}
