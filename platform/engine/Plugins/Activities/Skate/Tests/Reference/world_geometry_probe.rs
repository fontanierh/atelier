//! Public BoardWorld oracle; numerical modules are unmodified frozen sources.
use std::io::{Read,Write};
use math::{Basis3,Vector3};
use physics::{
    board_world::{BoardWorld,WorldTriangle,WorldLineHit},
    board_world::query_metadata::{Bounds,QueryMetadata,QueryMesh,QueryPool,EdgeSegment},
    contact::RetailContactMaterial,
    drive_frames::RetailAffineTransform,
    world_contact::triangle_from_volume,
};
struct Reader { bytes:Vec<u8>,at:usize }
impl Reader {
    fn word(&mut self)->u32 { let value=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;value }
    fn scalar(&mut self)->f32 { f32::from_bits(self.word()) }
    fn vector(&mut self)->Vector3 { Vector3::new(self.scalar(),self.scalar(),self.scalar()) }
    fn bounds(&mut self)->Bounds { Bounds{min:self.vector(),max:self.vector()} }
    fn transform(&mut self)->RetailAffineTransform {
        RetailAffineTransform{basis:Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.scalar()))},translation:self.vector()}
    }
}
struct Writer { words:Vec<u32> }
impl Writer {
    fn word(&mut self,value:u32) { self.words.push(value); }
    fn scalar(&mut self,value:f32) { self.word(value.to_bits()); }
    fn vector(&mut self,value:Vector3) { self.scalar(value.x);self.scalar(value.y);self.scalar(value.z); }
    fn bounds(&mut self,value:Bounds) { self.vector(value.min);self.vector(value.max); }
    fn optional_bounds(&mut self,value:Option<Bounds>) {
        self.word(u32::from(value.is_some()));self.bounds(value.unwrap_or(Bounds{min:Vector3::ZERO,max:Vector3::ZERO}));
    }
    fn error(&mut self,error:Option<&str>) {
        let bytes=error.unwrap_or("").as_bytes();self.word(bytes.len() as u32);for &byte in bytes {self.word(byte as u32);}
    }
    fn transform(&mut self,value:RetailAffineTransform) {
        for column in value.basis.columns {for lane in column {self.scalar(lane);}}self.vector(value.translation);
    }
    fn triangle(&mut self,value:WorldTriangle) {
        let triangle=value.triangle;
        for vertex in triangle.vertices {self.vector(vertex);}
        self.vector(triangle.feature.normal);
        for edge in triangle.feature.edges {self.vector(edge);}
        self.word(triangle.feature.flags);
        for cosine in triangle.feature.edge_cosines {self.scalar(cosine);}
        for length in triangle.edge_lengths {self.scalar(length);}
        self.scalar(triangle.fatness);self.scalar(value.material.static_friction);
        self.scalar(value.material.dynamic_friction);self.scalar(value.material.restitution);self.word(value.tag);
    }
    fn metadata(&mut self,value:&QueryMetadata) {
        self.word(value.packed_surfaces.len() as u32);for &surface in &value.packed_surfaces {self.word(surface as u32);}
        self.word(value.meshes.len() as u32);
        for mesh in &value.meshes {
            self.word(mesh.triangle_range.start as u32);self.word(mesh.triangle_range.end as u32);
            self.transform(mesh.local_to_world);self.transform(mesh.world_to_local);self.bounds(mesh.local_bounds);
            self.word(mesh.matching_group as u32);self.word(mesh.rejection_flags);self.word(mesh.geometry);
            self.word(match mesh.pool {QueryPool::Ground=>0,QueryPool::Island=>1,QueryPool::Conditional=>2});
        }
        self.word(value.static_edges.len() as u32);
        for edge in &value.static_edges {self.vector(edge.start);self.vector(edge.end);self.bounds(edge.local_bounds);}
        self.word(value.island_flags);
    }
    fn hit(&mut self,value:Result<Option<WorldLineHit>,&str>) {
        let hit=match value {Ok(hit)=>{self.error(None);hit},Err(error)=>{self.error(Some(error));None}};
        self.word(u32::from(hit.is_some()));self.word(hit.map_or(0,|h|h.tag));
        if let Some(hit)=hit {
            self.vector(hit.geometry.position);self.vector(hit.geometry.normal);self.scalar(hit.geometry.fraction);
            for lane in hit.geometry.volume_parameter {self.scalar(lane);}
        } else {for _ in 0..10 {self.word(0);}}
    }
}
struct TriangleInput {
    vertices:[Vector3;3],fatness:f32,edge_cosines:[f32;3],flags:u32,material:RetailContactMaterial,tag:u32,
}
fn triangle(reader:&mut Reader)->TriangleInput {
    let vertices=std::array::from_fn(|_|reader.vector());let fatness=reader.scalar();
    let edge_cosines=std::array::from_fn(|_|reader.scalar());let flags=reader.word();
    let material=RetailContactMaterial{static_friction:reader.scalar(),dynamic_friction:reader.scalar(),restitution:reader.scalar()};
    TriangleInput{vertices,fatness,edge_cosines,flags,material,tag:reader.word()}
}
fn cached(input:TriangleInput)->WorldTriangle {
    WorldTriangle{triangle:triangle_from_volume(input.vertices,input.fatness,input.edge_cosines,input.flags),material:input.material,tag:input.tag}
}
fn metadata(reader:&mut Reader)->QueryMetadata {
    let surfaces=reader.word();let packed_surfaces=(0..surfaces).map(|_|reader.word() as u16).collect();
    let count=reader.word();let meshes=(0..count).map(|_| {
        let triangle_range=reader.word() as usize..reader.word() as usize;
        let local_to_world=reader.transform();let world_to_local=reader.transform();let local_bounds=reader.bounds();
        let matching_group=reader.word() as i32;let rejection_flags=reader.word();let geometry=reader.word();
        let pool=match reader.word() {0=>QueryPool::Ground,1=>QueryPool::Island,2=>QueryPool::Conditional,_=>panic!("Invalid query pool")};
        QueryMesh{triangle_range,local_to_world,world_to_local,local_bounds,matching_group,rejection_flags,geometry,pool}
    }).collect();
    let count=reader.word();let static_edges=(0..count).map(|_|EdgeSegment{start:reader.vector(),end:reader.vector(),local_bounds:reader.bounds()}).collect();
    QueryMetadata{packed_surfaces,meshes,static_edges,island_flags:reader.word()}
}
struct Query {start:Vector3,end:Vector3,radius:f32,bounds:Option<Bounds>}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};
    let count=reader.word();let mut output=Vec::new();
    for index in 0..count {
        let operation=reader.word();let mut out=Writer{words:Vec::new()};
        match operation {
            0=>{
                let input=triangle(&mut reader);
                let result=WorldTriangle::from_vertices(input.vertices,input.material,input.tag,input.flags,input.edge_cosines,input.fatness);
                out.word(u32::from(result.is_some()));
                if let Some(result)=result {out.triangle(result);} else {for _ in 0..33 {out.word(0);}}
            },
            1=>{
                let count=reader.word();let points:Vec<_>=(0..count).map(|_|reader.vector()).collect();
                let padding=reader.scalar();let other=reader.bounds();let bounds=Bounds::from_points(points);
                out.optional_bounds(bounds);out.bounds(bounds.map_or(Bounds{min:Vector3::ZERO,max:Vector3::ZERO},|b|b.expanded(padding)));
                out.word(u32::from(bounds.is_some_and(|b|b.overlaps(other))));
            },
            2=>{
                let count=reader.word();let triangles=(0..count).map(|_|cached(triangle(&mut reader))).collect();
                let with_metadata=reader.word()!=0;let metadata=metadata(&mut reader);let query_count=reader.word();
                let queries:Vec<_>=(0..query_count).map(|_|{
                    let start=reader.vector();let end=reader.vector();let radius=reader.scalar();
                    let has_bounds=reader.word()!=0;let bounds=reader.bounds();
                    Query{start,end,radius,bounds:has_bounds.then_some(bounds)}
                }).collect();
                let world=if with_metadata {BoardWorld::with_query_metadata(triangles,metadata)} else {Ok(BoardWorld::new(triangles))};
                match world {
                    Err(error)=>out.error(Some(error)),
                    Ok(world)=>{
                        out.error(None);out.word(world.triangles().len() as u32);for &entry in world.triangles() {out.triangle(entry);}
                        match world.query_metadata() {Ok(metadata)=>{out.error(None);out.word(1);out.metadata(metadata);},Err(error)=>{out.error(Some(error));out.word(0);}}
                        out.word(query_count);
                        for query in queries {
                            out.optional_bounds(world.line_candidate_bounds(query.start,query.end,query.radius));
                            let ranges=world.candidate_ranges(query.bounds);out.word(ranges.len() as u32);
                            for range in ranges {out.word(range.start as u32);out.word(range.end as u32);}
                            let candidates:Vec<_>=world.line_candidates(query.start,query.end,query.radius).map(|(i,_)|i).collect();
                            out.word(candidates.len() as u32);for i in candidates {out.word(i as u32);}
                            match world.candidate_mesh_indices(query.bounds) {
                                Ok(meshes)=>{out.error(None);out.word(meshes.len() as u32);for i in meshes {out.word(i as u32);}},
                                Err(error)=>{out.error(Some(error));out.word(0);},
                            }
                            out.hit(world.query_thin_line(query.start,query.end));out.hit(world.query_swept_line(query.start,query.end,query.radius));
                        }
                    },
                }
            },
            _=>panic!("Invalid world geometry operation"),
        }
        output.extend([index,operation,out.words.len() as u32]);output.extend(out.words);
    }
    assert_eq!(reader.at,reader.bytes.len());
    std::io::stdout().write_all(&output.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
