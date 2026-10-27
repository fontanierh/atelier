//! Named parameter domains and the intervals regions leave open on them.

use std::collections::BTreeSet;

use anyhow::{Result, bail};

/// A published path parameter domain, including both endpoints.
pub struct Domain {
    pub id: &'static str,
    pub from: f64,
    pub to: f64,
}

/// A closed interval that another region leaves open on a published domain.
pub struct Opening {
    pub id: &'static str,
    pub from: f64,
    pub to: f64,
}

/// @cc [owner:fontanierh,label:correctness] openings-use-published-domains
/// An opening MUST name exactly one finite published domain, stay within it, and use a finite ordered interval.
/// Domain IDs MUST be unique; boundaries belong to the opening.
pub fn check(domains: &[Domain], openings: &[Opening]) -> Result<()> {
    let mut ids = BTreeSet::new();
    for domain in domains {
        if domain.id.is_empty() || !domain.from.is_finite() || !domain.to.is_finite() || domain.from >= domain.to {
            bail!("invalid path domain {:?}", domain.id);
        }
        if !ids.insert(domain.id) {
            bail!("duplicate path domain {:?}", domain.id);
        }
    }
    for opening in openings {
        let Some(domain) = domains.iter().find(|domain| domain.id == opening.id) else {
            bail!("opening refers to unknown path {:?}", opening.id);
        };
        if !opening.from.is_finite()
            || !opening.to.is_finite()
            || opening.from > opening.to
            || opening.from < domain.from
            || opening.to > domain.to
        {
            bail!("opening on {:?} lies outside its domain", opening.id);
        }
    }
    Ok(())
}

/// Whether a parameter lies in a declared closed opening, or None when the path or parameter is invalid.
pub fn is_open(domains: &[Domain], openings: &[Opening], id: &str, at: f64) -> Option<bool> {
    let domain = domains.iter().find(|domain| domain.id == id)?;
    if !at.is_finite() || at < domain.from || at > domain.to {
        return None;
    }
    Some(openings.iter().any(|opening| opening.id == id && opening.from <= at && at <= opening.to))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_domains_and_closed_openings() {
        let domain = || Domain { id: "edge", from: 0.0, to: 200.0 };
        let opening = || Opening { id: "edge", from: 86.2, to: 105.9 };
        check(&[domain()], &[opening()]).unwrap();
        let open: Vec<usize> =
            (0..=200).filter(|&k| is_open(&[domain()], &[opening()], "edge", k as f64).unwrap()).collect();
        assert_eq!(open, (87..=105).collect::<Vec<_>>());
        assert_eq!(is_open(&[domain()], &[opening()], "edge", 86.2), Some(true));
        assert_eq!(is_open(&[domain()], &[], "edge", 96.0), Some(false));
        assert_eq!(is_open(&[domain()], &[], "missing", 96.0), None);
        assert_eq!(is_open(&[domain()], &[], "edge", f64::NAN), None);
        assert!(check(&[domain(), domain()], &[]).is_err());
        assert!(check(&[domain()], &[Opening { id: "missing", ..opening() }]).is_err());
        assert!(check(&[domain()], &[Opening { from: 105.9, to: 86.2, ..opening() }]).is_err());
        assert!(check(&[domain()], &[Opening { from: -1.0, ..opening() }]).is_err());
        assert!(check(&[domain()], &[Opening { to: f64::INFINITY, ..opening() }]).is_err());
    }
}
