//! Actual locked serde_json scalar visitor; libc formatting matches UE %.17g.
use std::{ffi::{c_char,c_int},io::{self,Read,Write}};

unsafe extern "C" {
    fn snprintf(buffer:*mut c_char,size:usize,format:*const c_char,...)->c_int;
}
struct Input { bytes:Vec<u8>,at:usize }
impl Input {
    fn word(&mut self)->u32 {
        let bytes:&[u8;4]=self.bytes[self.at..self.at+4].try_into().unwrap();
        self.at+=4;u32::from_le_bytes(*bytes)
    }
    fn double(&mut self)->f64 { let low=self.word() as u64;f64::from_bits(low|((self.word() as u64)<<32)) }
    fn text(&mut self)->String {
        let size=self.word() as usize;let result=String::from_utf8(self.bytes[self.at..self.at+size].to_vec()).unwrap();
        self.at+=size;result
    }
}
fn word(output:&mut Vec<u8>,value:u32){output.extend(value.to_le_bytes());}
fn text(output:&mut Vec<u8>,value:&str){word(output,value.len() as u32);output.extend(value.as_bytes());}
fn format(number:f64)->String {
    let mut buffer=[0u8;64];
    let length=unsafe{snprintf(buffer.as_mut_ptr().cast(),buffer.len(),c"%.17g".as_ptr(),number)};
    assert!(length>0&&(length as usize)<buffer.len());
    String::from_utf8(buffer[..length as usize].to_vec()).unwrap()
}
fn main()->Result<(),Box<dyn std::error::Error>> {
    let mut bytes=vec![];io::stdin().read_to_end(&mut bytes)?;
    let mut input=Input{bytes,at:0};let count=input.word();let mut output=vec![];word(&mut output,count);
    for index in 0..count {
        let operation=input.word();
        let (token,direct)=match operation {
            0=>(input.text(),0),
            1|2=>{let mut number=input.double();if operation==2{number*=0.01;}(format(number),if number.is_finite(){(number as f32).to_bits()}else{0})},
            _=>panic!("Unknown transport operation"),
        };
        // No copied number algorithm: this invokes the exact actual dependency.
        let (okay,value,error)=match serde_json::from_str::<f32>(&token) {
            Ok(value)=>(true,value,String::new()),
            Err(error)=>(false,-151.375f32,error.to_string()),
        };
        word(&mut output,index);word(&mut output,operation);text(&mut output,&token);
        word(&mut output,u32::from(okay));word(&mut output,value.to_bits());text(&mut output,&error);word(&mut output,direct);
    }
    assert_eq!(input.at,input.bytes.len());io::stdout().write_all(&output)?;Ok(())
}
