//! Exported graph records. Attributes retain text, float words and boolean bytes in authored order.

pub mod attributes;
pub mod binding;
mod package;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GraphAttribute {
    pub name: String,
    pub text: String,
    pub float_bits: u32,
    pub boolean_byte: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GraphElement {
    /// Byte offset of the tag in the original file, for binding diagnostics.
    pub source_offset: usize,
    pub tag: String,
    /// File order, including duplicate names. Native hash-map binding is a
    /// separate operation; the decoder must not silently discard attributes.
    pub attributes: Vec<GraphAttribute>,
    /// Indices into StateGraph::elements, in original child order.
    pub children: Vec<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StateGraph {
    /// Preorder arena. Element zero is the single file root.
    pub elements: Vec<GraphElement>,
}
