//! A zip of files stored as they are, uncompressed: the screenshots are compressed already, and the notes are small.

/// The zip of `files`, each a name and its contents.
pub fn stored(files: &[(String, Vec<u8>)]) -> Vec<u8> {
    let mut zip = Vec::new();
    let mut directory = Vec::new();
    for (name, data) in files {
        let offset = zip.len() as u32;
        let crc = crc32fast::hash(data);
        let (name, size) = (name.as_bytes(), data.len() as u32);
        // The local header: signature, version 2.0, no flags, stored, no time or date, the checksum and both sizes.
        zip.extend(0x0403_4b50u32.to_le_bytes());
        zip.extend([20, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        for field in [crc, size, size] {
            zip.extend(field.to_le_bytes());
        }
        zip.extend((name.len() as u16).to_le_bytes());
        zip.extend(0u16.to_le_bytes());
        zip.extend(name);
        zip.extend(data);
        // Its entry in the central directory: the same, with where the local header starts.
        directory.extend(0x0201_4b50u32.to_le_bytes());
        directory.extend([20, 0, 20, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        for field in [crc, size, size] {
            directory.extend(field.to_le_bytes());
        }
        directory.extend((name.len() as u16).to_le_bytes());
        // No extra field, comment, disk number or attributes.
        directory.extend([0; 12]);
        directory.extend(offset.to_le_bytes());
        directory.extend(name);
    }
    let (start, count) = (zip.len() as u32, files.len() as u16);
    zip.extend(&directory);
    // The end of the central directory: on one disk, with every entry, its size and where it starts.
    zip.extend(0x0605_4b50u32.to_le_bytes());
    zip.extend([0; 4]);
    zip.extend(count.to_le_bytes());
    zip.extend(count.to_le_bytes());
    zip.extend((directory.len() as u32).to_le_bytes());
    zip.extend(start.to_le_bytes());
    zip.extend(0u16.to_le_bytes());
    zip
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The zip lists every file at its offset, and each holds its contents under its name.
    #[test]
    fn every_file_is_where_the_directory_says() {
        let files = vec![("notes.md".to_owned(), b"# Notes\n".to_vec()), ("note-01.png".to_owned(), vec![7; 300])];
        let zip = stored(&files);
        let u16_at = |at: usize| u16::from_le_bytes([zip[at], zip[at + 1]]) as usize;
        let u32_at = |at: usize| u32::from_le_bytes(zip[at..at + 4].try_into().unwrap()) as usize;
        let end = zip.len() - 22;
        assert_eq!(u32_at(end), 0x0605_4b50);
        assert_eq!(u16_at(end + 10), files.len());
        let mut entry = u32_at(end + 16);
        for (name, data) in &files {
            assert_eq!(u32_at(entry), 0x0201_4b50);
            let name_length = u16_at(entry + 28);
            assert_eq!(&zip[entry + 46..entry + 46 + name_length], name.as_bytes());
            assert_eq!(u32_at(entry + 16), crc32fast::hash(data) as usize);
            let local = u32_at(entry + 42);
            assert_eq!(u32_at(local), 0x0403_4b50);
            let start = local + 30 + u16_at(local + 26);
            assert_eq!(&zip[start..start + u32_at(local + 22)], &data[..]);
            entry += 46 + name_length;
        }
        assert_eq!(entry, end);
    }
}
