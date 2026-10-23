//! Shared conservative relative-path and normalized namespace ownership checks.
use std::collections::BTreeMap;
use unicode_casefold::UnicodeCaseFold;
use unicode_normalization::UnicodeNormalization;

/// @cc [owner:fontanierh,label:correctness] declared-path-policy
/// Relative paths MUST reject controls, backslash/colon, empty/dot/traversal
/// components and trailing dot/space. Ownership claims MUST refuse exact, ancestor,
/// NFD/full-casefold aliases without rewriting the declared path. This conservative
/// policy MUST NOT claim complete filesystem Unicode equivalence. See tests below
/// and tests/validation.rs; source path observation remains caller-owned.
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn path_policy_refuses_mutations_and_normalized_owner_aliases() {
        for invalid in [
            "",
            "/absolute",
            "trailing/",
            "a//b",
            ".",
            "..",
            "a/./b",
            "a/../b",
            "a\\b",
            "C:drive",
            "a\u{0}/b",
            "a\n/b",
            "trailing.",
            "trailing ",
        ] {
            assert!(relative_path(invalid, true).is_err(), "{invalid:?}");
            assert!(relative_path(invalid, false).is_err(), "{invalid:?}");
        }
        for valid in [
            "assets/模型.glb",
            "Café/mesh.npz",
            "folder/file name",
            "a..b/file",
        ] {
            relative_path(valid, true).unwrap();
            relative_path(valid, false).unwrap();
        }
        assert!(logical_path("relative").is_err());
        logical_path("/Game/模型").unwrap();
        for (first, second) in [
            ("Case/Mesh", "case/mesh"),
            ("Café/mesh", "Cafe\u{301}/mesh"),
            ("Straße/mesh", "STRASSE/mesh"),
            ("root", "root/child"),
            ("root/child", "root"),
        ] {
            let mut claims = Claims::new();
            claim(&mut claims, first, "first").unwrap();
            assert!(
                claim(&mut claims, second, "second").is_err(),
                "{first} vs {second}"
            );
        }
        let mut claims = Claims::new();
        claim(&mut claims, "root/a", "first").unwrap();
        claim(&mut claims, "root/b", "sibling").unwrap();
        assert_eq!(claims[&folded("root/a")].0, "root/a");
    }
}
