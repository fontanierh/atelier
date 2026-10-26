//! Shapes meshes are built from: tubes along a line of points, boxes and square cards. Each adds triangles to a
//! mesh, taking positions in a frame with z up, in metres, and storing them in glTF's.

use std::f64::consts::TAU;

use glam::{DMat3, DVec2, DVec3};

use crate::glb::{Mesh, y_up};

/// Adds one vertex and returns its index. `colour` is linear; none leaves the mesh without vertex colours.
pub fn vertex(mesh: &mut Mesh, at: DVec3, normal: DVec3, uv: DVec2, colour: Option<[f64; 4]>) -> u32 {
    mesh.positions.push(y_up(at).as_vec3().to_array());
    mesh.normals.push(y_up(normal.normalize()).as_vec3().to_array());
    mesh.uvs.push(uv.as_vec2().to_array());
    if let Some(colour) = colour {
        mesh.colours.push(colour.map(|c| c as f32));
    }
    (mesh.positions.len() - 1) as u32
}

/// A closed tube through `points`, each a position and the tube's radius there, with `sides` faces around, smooth
/// around and capped at both ends. At each inner point the ring of the tube turns halfway between the pieces it
/// joins, so they meet with no gap. Its texture wraps once around and repeats every `texture_m` along it.
pub fn tube(mesh: &mut Mesh, points: &[(DVec3, f64)], sides: usize, texture_m: f64) {
    let directions: Vec<DVec3> = (0..points.len())
        .map(|k| {
            let before = points[k.saturating_sub(1)].0;
            let after = points[(k + 1).min(points.len() - 1)].0;
            (after - before).normalize()
        })
        .collect();
    let mut along = 0.0;
    let mut rings: Vec<Vec<u32>> = Vec::new();
    for (k, &(at, radius)) in points.iter().enumerate() {
        if k > 0 {
            along += at.distance(points[k - 1].0);
        }
        let (x, y) = across(directions[k]);
        // The radius narrows along the tube, so its sides lean in: their normals tilt toward the narrow end.
        let lean = if k + 1 < points.len() {
            (radius - points[k + 1].1) / at.distance(points[k + 1].0)
        } else {
            (points[k - 1].1 - radius) / at.distance(points[k - 1].0)
        };
        let ring = (0..=sides)
            .map(|i| {
                let angle = TAU * i as f64 / sides as f64;
                let out = x * angle.cos() + y * angle.sin();
                let uv = DVec2::new(i as f64 / sides as f64, along / texture_m);
                vertex(mesh, at + out * radius, out + directions[k] * lean, uv, None)
            })
            .collect();
        rings.push(ring);
    }
    for pair in rings.windows(2) {
        for i in 0..sides {
            let (a, b, c, d) = (pair[0][i], pair[0][i + 1], pair[1][i + 1], pair[1][i]);
            mesh.indices.extend([a, b, c, a, c, d]);
        }
    }
    let ends = [(0, -directions[0]), (points.len() - 1, directions[points.len() - 1])];
    for (k, facing) in ends {
        let (at, radius) = points[k];
        let (x, y) = across(directions[k]);
        let centre = vertex(mesh, at, facing, DVec2::splat(0.5), None);
        let rim: Vec<u32> = (0..sides)
            .map(|i| {
                let angle = TAU * i as f64 / sides as f64;
                let out = x * angle.cos() + y * angle.sin();
                vertex(mesh, at + out * radius, facing, DVec2::new(0.5, 0.5) + out.truncate() * 0.5, None)
            })
            .collect();
        for i in 0..sides {
            let (a, b) = (rim[i], rim[(i + 1) % sides]);
            // Counter-clockwise seen from outside: the rings turn counter-clockwise seen from the tube's end.
            mesh.indices.extend(if k == 0 { [centre, b, a] } else { [centre, a, b] });
        }
    }
}

/// Two directions square to `direction` and to each other, turning counter-clockwise around it.
fn across(direction: DVec3) -> (DVec3, DVec3) {
    let up = if direction.z.abs() < 0.99 { DVec3::Z } else { DVec3::X };
    let x = up.cross(direction).normalize();
    (x, direction.cross(x))
}

/// A box centred on `centre`, `size` long along x, y and z, with flat faces.
pub fn cuboid(mesh: &mut Mesh, centre: DVec3, size: DVec3) {
    for axis in 0..3 {
        for sign in [-1.0, 1.0] {
            let mut normal = DVec3::ZERO;
            normal[axis] = sign;
            let (u, v) = (DVec3::from_array(cycle(axis, 1)), DVec3::from_array(cycle(axis, 2)));
            let (u, v) = if sign > 0.0 { (u, v) } else { (v, u) };
            let corner = |s: f64, t: f64| centre + (normal + u * s + v * t) * size / 2.0;
            let quad = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
                .map(|(s, t)| vertex(mesh, corner(s, t), normal, DVec2::new(s + 1.0, t + 1.0) / 2.0, None));
            mesh.indices.extend([quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]]);
        }
    }
}

/// The unit vector along the axis `shift` places after `axis`.
fn cycle(axis: usize, shift: usize) -> [f64; 3] {
    let mut v = [0.0; 3];
    v[(axis + shift) % 3] = 1.0;
    v
}

/// A square card `size` wide centred on `centre`, turned by `turn` from standing in the x-z plane. Each corner takes
/// its normal from `normal`, its texture position from the square `cell` (its lower-left corner and side in the
/// texture), and its colour from `shade`.
pub fn card(
    mesh: &mut Mesh,
    centre: DVec3,
    size: f64,
    turn: DMat3,
    normal: impl Fn(DVec3) -> DVec3,
    cell: (DVec2, f64),
    shade: f64,
) {
    let (low, side) = cell;
    let corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)].map(|(s, t)| {
        let at = centre + turn * DVec3::new((s - 0.5) * size, 0.0, (t - 0.5) * size);
        vertex(mesh, at, normal(at), low + DVec2::new(s, t) * side, Some([shade, shade, shade, 1.0]))
    });
    mesh.indices.extend([corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]]);
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The signed volume a closed mesh encloses, positive when its triangles face out.
    fn volume(mesh: &Mesh) -> f64 {
        mesh.indices
            .chunks(3)
            .map(|t| {
                let [a, b, c] = [0, 1, 2].map(|k| DVec3::from_array(mesh.positions[t[k] as usize].map(f64::from)));
                a.dot(b.cross(c)) / 6.0
            })
            .sum()
    }

    /// A box and a tube are closed and face outward: the volume they enclose is positive and close to their own.
    #[test]
    fn shapes_are_closed_and_face_out() {
        let mut mesh = Mesh::default();
        cuboid(&mut mesh, DVec3::new(1.0, 2.0, 3.0), DVec3::new(1.0, 2.0, 3.0));
        assert!((volume(&mesh) - 6.0).abs() < 1e-5);
        let mut mesh = Mesh::default();
        tube(&mut mesh, &[(DVec3::ZERO, 1.0), (DVec3::new(0.0, 0.0, 2.0), 1.0)], 64, 1.0);
        assert!((volume(&mesh) - std::f64::consts::PI * 2.0).abs() < 0.05);
    }
}
