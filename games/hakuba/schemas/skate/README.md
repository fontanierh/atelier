# Simulation byte formats

`src/lib.rs` reads the little-endian simulation formats and their indexed archive. It has no Bevy or filesystem dependency.
The archive keeps payloads intact, so a runtime can borrow compact constant/sample tracks from one immutable allocation.
`Package::parse` checks safe sorted names, contiguous offsets, complete byte coverage and each payload checksum.
`encode` writes the same format in sorted name order. `Reader` checks every byte range and UTF-8 string.
