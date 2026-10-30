//! Compact skating pages in the shared settings panel. Numeric rows come from their preference declarations.
use super::{next, row, stepped};
use crate::skate::{SKATE_KNOBS, SkateKnob};
use crate::{Settings, SkateDifficulty, SkateMode, SkatePreferences};
use bevy::prelude::*;
use bevy::ui_widgets::{Activate, ScrollArea, observe};
use hakuba_screens::{button, text};

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum Row {
    Mode,
    Difficulty,
    Goofy,
    AutoPush,
    AssistedAir,
    TightFlicks,
    Flick120Hz,
    Drift,
    Soften,
    Knob(usize),
}
impl Row {
    pub(super) fn name(self) -> &'static str {
        match self {
            Self::Mode => "Skating mode",
            Self::Difficulty => "Custom base difficulty",
            Self::Goofy => "Stance",
            Self::AutoPush => "Auto push",
            Self::AssistedAir => "Assisted spins and flips",
            Self::TightFlicks => "Tight hardflips / inwards",
            Self::Flick120Hz => "120 Hz flick reading",
            Self::Drift => "Drift powerslides",
            Self::Soften => "Soften skate sounds",
            Self::Knob(i) => SKATE_KNOBS[i].label,
        }
    }
    pub(super) fn always(self) -> bool {
        match self {
            Self::Difficulty | Self::AutoPush | Self::AssistedAir => false,
            Self::Knob(i) => SKATE_KNOBS[i].always,
            _ => true,
        }
    }
    pub(super) fn value(self, p: &SkatePreferences) -> String {
        match self {
            Self::Mode => format!("{:?}", p.mode),
            Self::Difficulty => format!("{:?}", p.difficulty),
            Self::Goofy => if p.goofy { "Goofy" } else { "Regular" }.into(),
            Self::AutoPush => choice(p.auto_push).into(),
            Self::AssistedAir => choice(p.assisted_air).into(),
            Self::TightFlicks => on(p.tight_flicks).into(),
            Self::Flick120Hz => on(p.flick_120hz).into(),
            Self::Drift => on(p.drift_powerslide).into(),
            Self::Soften => on(p.soften).into(),
            Self::Knob(i) => {
                let knob = &SKATE_KNOBS[i];
                let value = (knob.get)(p);
                if knob.label == "Camera FOV offset" { format!("{value:+.0}°") } else { format!("{value:.2}") }
            }
        }
    }
    pub(super) fn step(self, p: &mut SkatePreferences, by: i32) {
        if p.mode != SkateMode::Custom && !self.always() {
            return;
        }
        match self {
            Self::Mode => p.mode = next(&SkateMode::ALL, p.mode, by),
            Self::Difficulty => p.difficulty = next(&SkateDifficulty::ALL, p.difficulty, by),
            Self::Goofy => p.goofy = by > 0,
            Self::AutoPush => p.auto_push = next(&[None, Some(false), Some(true)], p.auto_push, by),
            Self::AssistedAir => p.assisted_air = next(&[None, Some(false), Some(true)], p.assisted_air, by),
            Self::TightFlicks => p.tight_flicks = by > 0,
            Self::Flick120Hz => p.flick_120hz = by > 0,
            Self::Drift => p.drift_powerslide = by > 0,
            Self::Soften => p.soften = by > 0,
            Self::Knob(i) => {
                let SkateKnob { low, high, step, get, set, .. } = SKATE_KNOBS[i];
                set(p, stepped(get(p), by as f32 * step, low, high));
                p.sanitize();
            }
        }
    }
}
fn choice(value: Option<bool>) -> &'static str {
    match value {
        None => "Difficulty",
        Some(false) => "Off",
        Some(true) => "On",
    }
}
fn on(value: bool) -> &'static str {
    if value { "On" } else { "Off" }
}

/// The page selection belongs to each panel, never to saved gameplay preferences.
#[derive(Component, Default)]
pub(super) struct Page(usize);
#[derive(Component)]
pub(super) struct PageBody;

const GROUPS: &[&str] =
    &["General", "Base", "Flick-It", "Air", "Rails", "Rolling", "Turning", "Balance", "Controls", "Camera", "Audio"];

pub(super) fn panel() -> impl Bundle {
    (
        Page::default(),
        Node {
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            max_height: vh(65),
            max_width: vw(98),
            row_gap: px(8),
            ..default()
        },
        children![
            (
                Node { column_gap: px(12), ..default() },
                children![
                    (
                        button("General"),
                        observe(|event: On<Activate>, parents: Query<&ChildOf>, mut pages: Query<&mut Page>| {
                            select(event.entity, 0, &parents, &mut pages);
                        })
                    ),
                    (
                        button("Skating"),
                        observe(|event: On<Activate>, parents: Query<&ChildOf>, mut pages: Query<&mut Page>| {
                            select(event.entity, 1, &parents, &mut pages);
                        })
                    ),
                ],
            ),
            (
                PageBody,
                ScrollArea,
                Node {
                    flex_direction: FlexDirection::Column,
                    min_height: px(0),
                    overflow: Overflow::scroll_y(),
                    max_width: percent(100),
                    row_gap: px(8),
                    ..default()
                }
            ),
        ],
    )
}
fn select(entity: Entity, page: usize, parents: &Query<&ChildOf>, pages: &mut Query<&mut Page>) {
    for ancestor in parents.iter_ancestors(entity) {
        if let Ok(mut current) = pages.get_mut(ancestor) {
            current.0 = page;
            return;
        }
    }
}
fn change_page(by: i32) -> impl Fn(On<Activate>, Query<&ChildOf>, Query<&mut Page>) {
    move |event: On<Activate>, parents: Query<&ChildOf>, mut pages: Query<&mut Page>| {
        for ancestor in parents.iter_ancestors(event.entity) {
            if let Ok(mut current) = pages.get_mut(ancestor) {
                current.0 = (current.0 as i32 + by).clamp(1, GROUPS.len() as i32 - 1) as usize;
                return;
            }
        }
    }
}
pub(super) fn show_pages(
    mut commands: Commands,
    pages: Query<(&Page, &Children), Changed<Page>>,
    bodies: Query<(), With<PageBody>>,
) {
    for (page, children) in &pages {
        let Some(body) = children.iter().find(|child| bodies.contains(*child)) else { continue };
        let mut body = commands.entity(body);
        body.despawn_children();
        body.with_children(|parent| {
            if page.0 == 0 {
                for general in super::Row::ALL {
                    parent.spawn(row(general));
                }
                return;
            }
            parent.spawn((
                Node { align_items: AlignItems::Center, justify_content: JustifyContent::SpaceBetween, ..default() },
                children![
                    (button("<"), observe(change_page(-1))),
                    text(format!("{} · {}/{}", GROUPS[page.0], page.0, GROUPS.len() - 1), 22.0),
                    (button(">"), observe(change_page(1))),
                ],
            ));
            parent.spawn(row(super::Row::Skate(Row::Mode)));
            let extra: &[Row] = match GROUPS[page.0] {
                "Base" => &[Row::Difficulty, Row::Goofy],
                "Air" => &[Row::AssistedAir],
                "Rolling" => &[Row::AutoPush],
                "Turning" => &[Row::Drift],
                "Controls" => &[Row::TightFlicks, Row::Flick120Hz],
                "Audio" => &[Row::Soften],
                _ => &[],
            };
            for &extra in extra {
                parent.spawn(row(super::Row::Skate(extra)));
            }
            for (i, _) in SKATE_KNOBS.iter().enumerate().filter(|(_, k)| k.group == GROUPS[page.0]) {
                parent.spawn(row(super::Row::Skate(Row::Knob(i))));
            }
            if page.0 == 1 {
                parent.spawn((
                    button("Reset custom values"),
                    observe(|_: On<Activate>, mut settings: ResMut<Settings>| {
                        let p = &mut settings.skate;
                        let defaults = SkatePreferences::default();
                        for knob in SKATE_KNOBS.iter().filter(|k| !k.always) {
                            (knob.set)(p, (knob.get)(&defaults));
                        }
                        p.difficulty = defaults.difficulty;
                        p.auto_push = defaults.auto_push;
                        p.assisted_air = defaults.assisted_air;
                    }),
                ));
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn every_numeric_knob_has_a_visible_page_and_bounded_steps() {
        let mut prefs = SkatePreferences::default();
        for (i, knob) in SKATE_KNOBS.iter().enumerate() {
            assert!(GROUPS.contains(&knob.group));
            for _ in 0..500 {
                Row::Knob(i).step(&mut prefs, 1);
            }
            assert!((knob.get)(&prefs) <= knob.high);
            for _ in 0..500 {
                Row::Knob(i).step(&mut prefs, -1);
            }
            assert!((knob.get)(&prefs) >= knob.low);
            assert!(prefs.validate().is_ok());
        }
    }
    #[test]
    fn preset_rows_do_not_destroy_custom_edits() {
        let mut prefs = SkatePreferences { mode: SkateMode::Normal, pop: 1.8, ..Default::default() };
        let pop = SKATE_KNOBS.iter().position(|k| k.label == "Ollie pop").unwrap();
        Row::Knob(pop).step(&mut prefs, -1);
        assert_eq!(prefs.pop, 1.8);
        Row::Mode.step(&mut prefs, 10);
        Row::Knob(pop).step(&mut prefs, -1);
        assert_eq!(prefs.pop, 1.75);
    }
}
