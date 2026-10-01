// SPDX-License-Identifier: Apache-2.0
// Independent oracle: actual pinned Rust 1.97.1 std formatter, not table copies.
use std::io::{self, Read, Write};

struct Input { bytes: Vec<u8>, at: usize }
impl Input {
    fn word(&mut self) -> u32 {
        let result = u32::from_le_bytes(self.bytes[self.at..self.at + 4].try_into().unwrap());
        self.at += 4;
        result
    }
    fn text(&mut self) -> &[u8] {
        let count = self.word() as usize;
        let begin = self.at;
        self.at += count;
        &self.bytes[begin..self.at]
    }
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self, value: u32) { self.0.extend(value.to_le_bytes()); }
    fn text(&mut self, value: &str) {
        self.word(value.len() as u32);
        self.0.extend(value.as_bytes());
    }
}
fn main() {
    let mut bytes = Vec::new();
    io::stdin().read_to_end(&mut bytes).unwrap();
    let mut input = Input { bytes, at: 0 };
    let mut output = Output(Vec::new());
    let commands = input.word();
    output.word(commands);
    let mut retained = String::from("retained\0output");
    for _ in 0..commands {
        let op = input.word();
        output.word(op);
        if op == 0 {
            output.word(0x110000 - 0x800);
            for scalar in 0..0x110000 {
                let Some(c) = char::from_u32(scalar) else { continue };
                let mut buffer = [0; 4];
                let text = c.encode_utf8(&mut buffer);
                output.word(scalar);
                output.text(&format!("{text:?}"));
            }
        } else if op == 1 || op == 2 {
            // Invalid bytes have no str/formatter equivalent. This branch only
            // specifies native rejection and retained-output policy separately.
            match std::str::from_utf8(input.text()) {
                Ok(text) => {
                    retained = format!("{text:?}");
                    output.word(1);
                    output.text("");
                }
                Err(error) => {
                    output.word(0);
                    output.text(&format!("Invalid UTF-8 at byte {}", error.valid_up_to()));
                }
            }
            output.text(&retained);
        } else { panic!("Unknown opcode {op}"); }
    }
    assert_eq!(input.at, input.bytes.len());
    io::stdout().write_all(&output.0).unwrap();
}
