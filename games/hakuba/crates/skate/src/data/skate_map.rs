//! Owned collision geometry supplied by the host world, in simulation metres.
#[derive(Debug, PartialEq)]
pub struct SkateMap {
    pub version: u8,
    pub name: String,
    pub spawn: [f32; 3],
    pub heading: f32,
    /// Authored environment fields in wire order (12, 14, or 45 floats).
    pub environment: Vec<f32>,
    pub materials: Vec<Material>,
    pub textures: Vec<Texture>,
    pub geometry: Geometry,
    pub rails: Vec<Rail>,
    pub doors: Vec<Door>,
    pub lights: Vec<Light>,
    pub routes: Vec<Route>,
    pub extensions: Vec<Extension>,
}
#[derive(Debug, PartialEq)]
pub struct Material {
    pub name: String,
    pub flags: u32,
    pub friction: f32,
    pub restitution: f32,
    pub color: [f32; 3],
    pub roughness: f32,
    pub emissive: f32,
    /// Albedo, indirect, normal, ORM, emissive. One-based, zero absent.
    pub textures: [u32; 5],
    pub indirect_strength: f32,
    pub alpha_mode: u32,
    pub alpha_cutoff: f32,
    pub audio: u32,
    pub physics: u32,
    pub pattern: u32,
    pub depth_layer: Option<u32>,
    /// Complete v12+ retail definition bytes; distinct from portable PBR fields.
    pub retail_definition: Option<Vec<u8>>,
}
#[derive(Debug, PartialEq)]
pub struct Texture {
    pub name: String,
    pub width: u32,
    pub height: u32,
    pub color_space: u32,
    pub rgba: Vec<u8>,
}
#[derive(Debug, Clone, PartialEq)]
pub struct Vertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub uv: [f32; 2],
    pub lightmap_uv: [f32; 2],
    pub material: u32,
    pub decal_uv: Option<[f32; 2]>,
    pub tangent_frame: Option<[u8; 4]>,
}
#[derive(Debug, PartialEq)]
pub struct Collision {
    pub points: [[f32; 3]; 3],
    pub surface: u32,
    pub material: u32,
    pub native_edges: Option<[u8; 3]>,
}
#[derive(Debug, PartialEq)]
pub struct Geometry {
    pub vertices: Vec<Vertex>,
    pub indices: Vec<u32>,
    pub collision: Vec<Collision>,
}
#[derive(Debug, PartialEq)]
pub struct Rail {
    pub name: String,
    pub closed: bool,
    pub points: Vec<[f32; 3]>,
    pub native: Option<Vec<u8>>,
}
#[derive(Debug, PartialEq)]
pub struct Door {
    pub name: String,
    /// Hinge position/axis, closed width/depth axes, local min/max.
    pub frame: [[f32; 3]; 6],
    /// Minimum/maximum/initial angle, mass, damping.
    pub motion: [f32; 5],
    /// Spring, max angular speed, contact impulse scale (absent in v4).
    pub response: Option<[f32; 3]>,
    pub friction: f32,
    pub restitution: f32,
    pub surface: u32,
    pub geometry: Geometry,
}
#[derive(Debug, PartialEq)]
pub struct Light {
    pub name: String,
    pub kind: u32,
    pub position: [f32; 3],
    pub direction: [f32; 3],
    pub color: [f32; 3],
    pub intensity: f32,
    pub range: f32,
    pub radius: f32,
    pub inner_cos: f32,
    pub outer_cos: f32,
}
#[derive(Debug, PartialEq)]
pub struct Route {
    pub rail: Rail,
    pub skaters: u32,
    pub speed: f32,
    pub spacing: f32,
}
#[derive(Debug, PartialEq)]
pub struct Extension {
    pub tag: [u8; 4],
    pub schema: u32,
    pub payload: Vec<u8>,
}
