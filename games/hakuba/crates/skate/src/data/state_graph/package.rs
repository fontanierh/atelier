//! ATGRPH01 reader. Attribute words, duplicate names and preorder are not normalized.
use super::{GraphAttribute, GraphElement, StateGraph};
use crate::data::AssetError;
use hakuba_skate_schema::{Error, Reader};

impl StateGraph {
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, AssetError> {
        decode(bytes).map_err(|e| AssetError(e.to_string()))
    }
}
fn decode(bytes: &[u8]) -> Result<StateGraph, Error> {
    let mut r = Reader::new(bytes, b"ATGRPH01")?;
    let strings = r.word()? as usize;
    let count = r.word()? as usize;
    if strings > r.remaining() / 4 || count == 0 || count > r.remaining() / 16 {
        return Err(Error("invalid graph counts".into()));
    }
    let strings = (0..strings).map(|_| r.string().map(str::to_owned)).collect::<Result<Vec<_>, _>>()?;
    let string = |r: &mut Reader<'_>| -> Result<String, Error> {
        strings.get(r.word()? as usize).cloned().ok_or_else(|| Error("graph string index out of range".into()))
    };
    let mut elements = Vec::with_capacity(count);
    let mut parents = vec![None; count];
    for index in 0..count {
        let source_offset = r.word()? as usize;
        let tag = string(&mut r)?;
        let attributes = r.word()? as usize;
        let children = r.word()? as usize;
        if attributes > r.remaining() / 16 || children > r.remaining() / 4 {
            return Err(Error("truncated graph element".into()));
        }
        let mut element =
            GraphElement { source_offset, tag, attributes: Vec::with_capacity(attributes), children: Vec::new() };
        for _ in 0..attributes {
            let name = string(&mut r)?;
            let text = string(&mut r)?;
            let float_bits = r.word()?;
            let boolean_byte = u8::try_from(r.word()?).map_err(|_| Error("graph boolean exceeds one byte".into()))?;
            element.attributes.push(GraphAttribute { name, text, float_bits, boolean_byte });
        }
        if children > r.remaining() / 4 {
            return Err(Error("truncated graph children".into()));
        }
        for _ in 0..children {
            let child = r.word()? as usize;
            if child <= index || child >= count || parents[child].is_some() {
                return Err(Error("graph child must have one earlier parent".into()));
            }
            parents[child] = Some(index);
            element.children.push(child);
        }
        if index != 0 && parents[index].is_none() {
            return Err(Error("unreachable graph element".into()));
        }
        elements.push(element);
    }
    r.end()?;
    let mut pending = vec![0];
    let mut next = 0;
    while let Some(index) = pending.pop() {
        if index != next {
            return Err(Error("graph arena is not preorder".into()));
        }
        next += 1;
        pending.extend(elements[index].children.iter().rev().copied());
    }
    if next != count {
        return Err(Error("unreachable graph element".into()));
    }
    Ok(StateGraph { elements })
}
