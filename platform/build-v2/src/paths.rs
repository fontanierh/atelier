//! Shared conservative relative-path and normalized namespace ownership checks.
use std::collections::BTreeMap;
use unicode_casefold::UnicodeCaseFold;
use unicode_normalization::UnicodeNormalization;

pub(crate) fn relative_path(value: &str, owned: bool) -> Result<(), String> {
    if value.is_empty()
        || value
            .chars()
            .any(|c| c.is_control() || c == '\\' || c == ':')
        || value.split('/').any(|part| {
            part.is_empty() || part == "." || part == ".." || part.ends_with(['.', ' '])
        })
    {
        return Err(format!(
            "invalid {} path: {value:?}",
            if owned { "owned" } else { "source" }
        ));
    }
    Ok(())
}

pub(crate) fn logical_path(value: &str) -> Result<(), String> {
    let path = value
        .strip_prefix('/')
        .ok_or_else(|| String::from("logical path must start with /"))?;
    relative_path(path, true)
}

pub(crate) fn folded(path: &str) -> String {
    // Canonical decomposition + full non-Turkic folding conservatively rejects
    // ambiguous aliases. This is not an emulator of every APFS Unicode revision.
    path.nfd().case_fold().nfd().collect()
}

pub(crate) type Claims = BTreeMap<String, (String, String)>;

pub(crate) fn conflict<'a>(claims: &'a Claims, path: &str) -> Option<&'a (String, String)> {
    let key = folded(path);
    if let Some(owner) = claims.get(&key) {
        return Some(owner);
    }
    for (index, _) in key.match_indices('/') {
        if let Some(owner) = claims.get(&key[..index]) {
            return Some(owner);
        }
    }
    let prefix = key + "/";
    if let Some((next, owner)) = claims.range(prefix.clone()..).next() {
        if next.starts_with(&prefix) {
            return Some(owner);
        }
    }
    None
}

pub(crate) fn claim(claims: &mut Claims, path: &str, owner: &str) -> Result<(), String> {
    if let Some((old, previous)) = conflict(claims, path) {
        return Err(format!(
            "overlapping output owners {previous} ({old}) and {owner} ({path})"
        ));
    }
    claims.insert(folded(path), (path.into(), owner.into()));
    Ok(())
}
