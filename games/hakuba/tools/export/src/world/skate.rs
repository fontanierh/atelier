//! Index-only skating metadata. Region choices never enter tile geometry or its input fingerprint.
use super::regions;
use crate::glb::Glb;
use anyhow::{Result, bail};

pub(super) fn write(index: &mut Glb) -> Result<()> {
    let mut skate = hakuba_world_skate_schema::Metadata::default();
    for region in regions::REGIONS {
        let metadata = region.skate();
        metadata.validate().map_err(anyhow::Error::msg)?;
        for mut rail in metadata.rails {
            rail.id = format!("{}/{}", region.name(), rail.id);
            skate.rails.push(rail);
        }
        for mut zone in metadata.assist_zones {
            zone.id = format!("{}/{}", region.name(), zone.id);
            skate.assist_zones.push(zone);
        }
        for mut zone in metadata.boost_zones {
            zone.id = format!("{}/{}", region.name(), zone.id);
            skate.boost_zones.push(zone);
        }
        for material in metadata.materials {
            if let Some(existing) = skate.materials.iter().find(|m| m.material == material.material) {
                if existing != &material {
                    bail!("conflicting physical surface for {}", material.material);
                }
            } else {
                skate.materials.push(material);
            }
        }
    }
    skate.rails.sort_by(|a, b| a.id.cmp(&b.id));
    skate.assist_zones.sort_by(|a, b| a.id.cmp(&b.id));
    skate.boost_zones.sort_by(|a, b| a.id.cmp(&b.id));
    skate.materials.sort_by(|a, b| a.material.cmp(&b.material));
    skate.validate().map_err(anyhow::Error::msg)?;
    index.add_data("skate world", serde_json::to_value(&skate)?);
    Ok(())
}
