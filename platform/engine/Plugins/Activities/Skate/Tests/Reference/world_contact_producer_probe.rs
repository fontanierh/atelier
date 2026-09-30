//! Complete original BoardWorld.query_primitives; seed records reconstructed from public contacts.
use std::io::{Read,Write};
use math::{Vector3,Basis3};
use physics::{board_world::{BoardWorld,WorldTriangle,BoardWorldVolume,ContactRetentionSettings},
    board_world::query_metadata::{QueryMetadata,QueryMesh,QueryPool,Bounds},board_step::CollisionBody,
    drive_frames::RetailAffineTransform,contact::RetailContactMaterial,collision::{Triangle,Sphere,WorldContactSettings},
    world_contact::{ContactPrimitive,triangle_from_volume,transform_triangle_volume}};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->Vector3 {Vector3::new(self.scalar(),self.scalar(),self.scalar())}
    fn basis(&mut self)->Basis3 {Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.scalar()))}}
    fn material(&mut self)->RetailContactMaterial {RetailContactMaterial{static_friction:self.scalar(),dynamic_friction:self.scalar(),restitution:self.scalar()}}
    fn triangle(&mut self,transformed:bool)->Triangle {
        let vertices=std::array::from_fn(|_|self.vector());let fatness=self.scalar();let cosines=std::array::from_fn(|_|self.scalar());let flags=self.word();
        if transformed {let basis=self.basis();let translation=self.vector();transform_triangle_volume(vertices,fatness,cosines,flags,basis,translation)}else{triangle_from_volume(vertices,fatness,cosines,flags)}
    }
    fn primitive(&mut self)->ContactPrimitive {
        match self.word() {
            0=>ContactPrimitive::Sphere(Sphere{center:self.vector(),radius:self.scalar()}),
            1=>ContactPrimitive::Capsule{center:self.vector(),axis:self.vector(),half_length:self.scalar(),radius:self.scalar()},
            2=>ContactPrimitive::Triangle(self.triangle(true)),
            3=>ContactPrimitive::RoundedBox{center:self.vector(),basis:self.basis(),half_extents:self.vector(),radius:self.scalar()},
            _=>panic!("Invalid world contact primitive"),
        }
    }
    fn metadata(&mut self)->QueryMetadata {
        let n=self.word();let packed_surfaces=(0..n).map(|_|self.word() as u16).collect();let n=self.word();
        let meshes=(0..n).map(|_|{
            let start=self.word() as usize;let end=self.word() as usize;let local_bounds=Bounds{min:self.vector(),max:self.vector()};
            let matching_group=self.word() as i32;let rejection_flags=self.word();let geometry=self.word();let pool=match self.word(){0=>QueryPool::Ground,1=>QueryPool::Island,2=>QueryPool::Conditional,_=>panic!("Invalid pool")};
            QueryMesh{triangle_range:start..end,local_to_world:RetailAffineTransform::IDENTITY,world_to_local:RetailAffineTransform::IDENTITY,local_bounds,matching_group,rejection_flags,geometry,pool}
        }).collect();QueryMetadata{packed_surfaces,meshes,static_edges:Vec::new(),island_flags:self.word()}
    }
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let count=reader.word();let mut result=Vec::new();
    for index in 0..count {
        let n=reader.word();let triangles=(0..n).map(|_|{let triangle=reader.triangle(false);let material=reader.material();WorldTriangle{triangle,material,tag:reader.word()}}).collect();
        let authored=reader.word()!=0;let metadata=reader.metadata();let seams=reader.word()!=0;
        let mut world=if authored{BoardWorld::with_query_metadata(triangles,metadata).unwrap()}else{BoardWorld::new(triangles)};if seams{world.enable_imported_floor_seams();}
        let frames=reader.word();let mut out=vec![frames];
        for _ in 0..frames {
            let n=reader.word();let volumes:Vec<_>=(0..n).map(|_|BoardWorldVolume{body:CollisionBody::from_contact_id(reader.word()),primitive:reader.primitive(),linear_velocity:reader.vector(),material:reader.material()}).collect();
            let query=WorldContactSettings{volume_padding:reader.scalar(),maximum_separating_distance:reader.scalar(),edge_cos_bend_normal_threshold:reader.scalar(),convexity_epsilon:reader.scalar(),is_object:reader.word()!=0};
            let retention=ContactRetentionSettings{capacity:reader.word(),duplicate_distance_squared:reader.scalar(),deferred_reduction:reader.word()!=0};
            let contacts=world.query_primitives(&volumes,query,retention).to_vec();out.extend([world.dropped_contacts(),contacts.len() as u32]);
            for collision in contacts {
                let c=collision.contact;let mut row=[0;64];for (offset,v) in [(0,c.position_on_a),(4,c.position_on_b),(8,c.normal)]{row[offset..offset+3].copy_from_slice(&[v.x.to_bits(),v.y.to_bits(),v.z.to_bits()]);}
                row[3]=collision.body_a.contact_id();row[7]=collision.body_b.contact_id();row[11]=c.restitution.to_bits();row[15]=c.static_friction.to_bits();row[19]=c.dynamic_friction.to_bits();row[23]=c.tag;out.extend(row);
            }
        }
        result.extend([index,out.len() as u32]);result.extend(out);
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&result.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
