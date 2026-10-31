//! Native wheel surface vote82C08818 on live wheel lines and contact reports.
use super::super::riding_outputs::RidingOutputs;
use crate::core::physics::{board_runtime::BoardRuntime, contact_feedback::choose_surface};

/// Dominant wheel surface for presentation; physics keeps its existing vote owner.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct GroundSurfaceReport {
    pub sound: u32,
    pub physics: u32,
    pub wheels: u32,
}

pub(crate) fn report(riding: &RidingOutputs) -> GroundSurfaceReport {
    wheel_surface_report(
        riding.wheel_lines.physics_surfaces,
        riding.wheel_lines.sound_surfaces,
        std::array::from_fn(|i| riding.ground.parts[i].in_contact),
    )
}

fn wheel_surface_report(physics: [u32; 4], sounds: [u32; 4], contacts: [bool; 4]) -> GroundSurfaceReport {
    let mut report = GroundSurfaceReport { physics: choose_surface(physics, contacts, false), ..Default::default() };
    let mut votes = [0; 128];
    let mut best = 0;
    for (i, contact) in contacts.into_iter().enumerate() {
        report.wheels += u32::from(contact);
        let sound = (sounds[i] & 0x7f) as usize;
        if sound != 0 {
            votes[sound] += if contact { 4 } else { 1 };
            if votes[sound] > best {
                best = votes[sound];
                report.sound = sound as u32;
            }
        }
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn imported_profiles_report_smooth_rough_slow_and_grass_without_replacing_physics() {
        for (packed, physics, sound, key) in [
            (129, 1, 1, "smooth"),
            (130, 1, 2, "smooth"),
            (131, 1, 3, "smooth"),
            (260, 2, 4, "rough"),
            (261, 2, 5, "rough"),
            (390, 3, 6, "slow"),
            (647, 5, 7, "veryslow"),
            (648, 5, 8, "veryslow"),
        ] {
            let report = wheel_surface_report([(packed >> 7) & 31; 4], [packed & 127; 4], [true; 4]);
            assert_eq!(report, GroundSurfaceReport { sound, physics, wheels: 4 });
            assert_eq!(surface_key(report.physics).unwrap(), key);
        }
    }
    #[test]
    fn actual_contacts_outvote_queries_and_sound_ties_keep_first_wheel() {
        let report = wheel_surface_report([2, 5, 5, 5], [4, 7, 7, 7], [true, false, false, false]);
        assert_eq!(report, GroundSurfaceReport { sound: 4, physics: 2, wheels: 1 });
        let report = wheel_surface_report([2, 1, 0, 0], [4, 2, 0, 0], [true, true, false, false]);
        assert_eq!(report, GroundSurfaceReport { sound: 4, physics: 1, wheels: 2 });
        assert_eq!(
            wheel_surface_report([0; 4], [0; 4], [false; 4]),
            GroundSurfaceReport { sound: 0, physics: 1, wheels: 0 }
        );
    }
}

/// Wheel surface IDs come from line queries. The report loop82C08198 updates
/// only truck/deck material slots, so wheel contacts contribute vote weights
/// without replacing the query-owned material ID.
pub(crate) fn active_surface(riding: &RidingOutputs, board: &BoardRuntime) -> u32 {
    let contacts = std::array::from_fn(|i| riding.ground.parts[i].in_contact);
    let forced = board.contact_reports().iter().any(|r| r.other_surface & 0x0f80 == 0x0600);
    choose_surface(riding.wheel_lines.physics_surfaces, contacts, forced)
}

/// SurfacePhysics constructor82D85D08 binds these exact five collection keys
/// at24/40/56/72/88. Lookup8 hashes independently match the native immediates.
/// The selector's mode normalization lives in the processed-input producer.
pub(crate) fn surface_key(mode: u32) -> Result<&'static str, String> {
    match mode {
        1 => Ok("smooth"),
        2 => Ok("rough"),
        3 => Ok("slow"),
        4 => Ok("slippery"),
        5 => Ok("veryslow"),
        _ => Err(format!("Processed surface mode {mode} was not normalized by SurfacePhysics")),
    }
}
