// Included after the complete original camera/runtime.rs prefix. All camera
// execution calls below enter the original production methods without wrappers.
use skate_core::migration_camera_observer::{Observe,ReadValue,Input};
use skate_core::{math::Vector3,physics::{board_world::WorldTriangle,world_contact::triangle_from_volume,
    contact::RetailContactMaterial},camera::{FatLine,PathObstacle,TrajectoryQuery}};

struct MovingPublication {
    obstacles:Vec<PathObstacle>,
    calls:Vec<([f32;4],[f32;4],f32,u32)>,
}
impl MovingObstacleProvider for MovingPublication {
    fn collect(&mut self,position:[f32;4],velocity:[f32;4],radius:f32,output:&mut [PathObstacle;50])->usize {
        assert!(self.obstacles.len()<=50);
        for (destination,value) in output.iter_mut().zip(&self.obstacles) {*destination=*value;}
        self.calls.push((position,velocity,radius,self.obstacles.len() as u32));
        self.obstacles.len()
    }
}
fn status(output:&mut Vec<u8>,result:Result<(),String>) {
    match result {Ok(())=>1u32.observe(output),Err(error)=>{0u32.observe(output);error.observe(output);}}
}
fn read_world(input:&mut Input)->BoardWorld {
    let triangles=(0..input.word()).map(|_| {
        let vertices=core::array::from_fn(|_|Vector3::new(input.float(),input.float(),input.float()));
        let fatness=input.float();let edge_cosines=ReadValue::read(input);let flags=input.word();
        let material=RetailContactMaterial{static_friction:input.float(),dynamic_friction:input.float(),restitution:input.float()};
        WorldTriangle{triangle:triangle_from_volume(vertices,fatness,edge_cosines,flags),material,tag:input.word()}
    }).collect();
    BoardWorld::new(triangles)
}
fn observe_runtime(runtime:&CameraRuntime,output:&mut Vec<u8>,log:&crate::LogSink) {
    runtime.manager.observe(output);runtime.subject.observe(output);
    runtime.graph.migration_observe(output);runtime.trajectories.observe(output);
    runtime.frame.observe(output);runtime.latest_subject.observe(output);
    runtime.simulation_rate_requests.observe(output);
    let raw=log.0.lock().unwrap();let text=std::str::from_utf8(&raw).unwrap();
    let messages:Vec<_>=text.lines().filter_map(|line|line.find("Stock camera graph: ").map(|at|line[at..].to_owned())).collect();
    messages.observe(output);
}
pub(super) fn migration_run(root:&Path,input:&mut Input,output:&mut Vec<u8>,log:&crate::LogSink)->Result<(),String> {
    let count=input.word();count.observe(output);
    for _ in 0..count {
        let id=input.word();id.observe(output);let world=read_world(input);
        let folder=root.join(format!("case-{id}"));
        let loaded=CameraRuntime::load(&folder);let rows=input.word();rows.observe(output);
        match loaded {
            Err(error)=>{status(output,Err(error));assert_eq!(rows,0);continue;},
            Ok(mut runtime)=>{
                status(output,Ok(()));runtime.settings.observe(output);runtime.compass_settings.observe(output);
                runtime.graph.migration_settings().observe(output);runtime.shots.observe(output);runtime.shakes.observe(output);
                observe_runtime(&runtime,output,log);
                for _ in 0..rows {
                    let operation=input.word();operation.observe(output);
                    let mut moving=MovingPublication{obstacles:Vec::new(),calls:Vec::new()};
                    match operation {
                        0=>{
                            let dt=input.float();let snapshot=ReadValue::read(input);let gravity=ReadValue::read(input);
                            let environment=ReadValue::read(input);moving.obstacles=ReadValue::read(input);
                            let result=runtime.advance(dt,snapshot,&world,gravity,&environment,&mut moving);
                            match result {Ok(frame)=>{status(output,Ok(()));frame.observe(output);},Err(error)=>status(output,Err(error))}
                        },
                        1=>{runtime.set_aspect_ratio(input.float());status(output,Ok(()));},
                        2=>{runtime.simulation_rate_requests.clear();status(output,Ok(()));},
                        3=>{
                            let name=input.string();let force=input.boolean();let subject=ReadValue::read(input);
                            match runtime.manager.set_shot(&name,force,&subject,&runtime.shots) {
                                Ok(changed)=>{status(output,Ok(()));changed.observe(output);},Err(error)=>status(output,Err(error))}
                        },
                        4=>{
                            let subject=ReadValue::read(input);let physical=ReadValue::read(input);let environment=ReadValue::read(input);
                            status(output,Ok(()));runtime.graph.migration_conditions(&runtime.manager,&subject,physical,&environment).observe(output);
                        },
                        5=>{
                            let line:FatLine=ReadValue::read(input);
                            match super::world_query::line(&world,line.start,line.end,line.radius) {
                                Ok(result)=>{status(output,Ok(()));result.observe(output);},Err(error)=>status(output,Err(error))}
                        },
                        6=>{
                            let query:TrajectoryQuery=ReadValue::read(input);
                            match query.collision_time(|start,end,radius| {
                                let hit=super::world_query::line(&world,start,end,radius)?;
                                Ok((hit.hit!=0).then_some(hit.position))
                            }) {Ok(time)=>{status(output,Ok(()));time.observe(output);},Err(error)=>status(output,Err(error))}
                        },
                        7=>{
                            let class=input.string();let key=input.string();let name=input.string();let count=input.word();
                            let data=skate_data::collections::Collections::load(&folder)?;
                            let values=match count {
                                0=>data.words::<0>(&class,&key,&name).map(|v|v.to_vec()),
                                1=>data.words::<1>(&class,&key,&name).map(|v|v.to_vec()),
                                3=>data.words::<3>(&class,&key,&name).map(|v|v.to_vec()),
                                8=>data.words::<8>(&class,&key,&name).map(|v|v.to_vec()),
                                16=>data.words::<16>(&class,&key,&name).map(|v|v.to_vec()),
                                20=>data.words::<20>(&class,&key,&name).map(|v|v.to_vec()),
                                32=>data.words::<32>(&class,&key,&name).map(|v|v.to_vec()),
                                _=>return Err("Invalid settings word probe count".into()),
                            };
                            match values {Ok(values)=>{status(output,Ok(()));values.observe(output);},Err(error)=>status(output,Err(error))}
                        },
                        _=>return Err("Invalid camera probe operation".into()),
                    }
                    moving.calls.len().observe(output);
                    for (position,velocity,radius,count) in &moving.calls {position.observe(output);velocity.observe(output);radius.observe(output);count.observe(output);}
                    observe_runtime(&runtime,output,log);
                }
            }
        }
        log.0.lock().unwrap().clear();
    }
    Ok(())
}
