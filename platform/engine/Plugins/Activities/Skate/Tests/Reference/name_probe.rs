//! Temporary migration oracle for original record/name identities.
#[path = "../../ThirdParty/skate-runtime/crates/skate-data/src/attrib_hash.rs"]
mod reference;
use std::io::{BufRead, Write};

fn main() {
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    for line in std::io::stdin().lock().lines() {
        let name = line.unwrap();
        writeln!(out,"{:016x} {}",reference::hash(&name),&reference::numeric_name(&name)[5..].to_lowercase()).unwrap();
    }
}
