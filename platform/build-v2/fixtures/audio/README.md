# Audio source fixtures (H4b)

Two tiny mono PCM16 WAV files for build-v2 audio sources, with a manifest of the exact expected
samples. They are source data only: this is not native import, cook or runtime proof.

- **base-mono-pcm16-100ms.wav**: 8000 Hz, mono, 16-bit, 800 frames (100 ms), 1644 bytes.
- **variant-mono-pcm16-100ms.wav**: byte-identical except frames 400-439, which hold a different
  integer cycle. 1644 bytes.
- **manifest.json**: the header fields, the sample segments for the base file, the changed segment
  for the variant, and the SHA-256 and size of both files.

The manifest's signal_rule defines every sample: each segment covers [start_frame, start_frame +
frames) and repeats its integer values from the segment's first frame. Segments are contiguous and
cover all 800 frames, so the expected samples are stated in full without depending on the WAV
bytes. The manifest digests pin the files, so an accidental regeneration cannot pass silently.

The files were written once with the Python standard library wave module from those integer tables.
No floating-point synthesis, codec or native tool is involved. The focused test is
platform/studio/tests/test_build_v2_audio_fixtures.py; it reads the files with wave and compares
them against the manifest. H4b covers source fixtures only; H4 stays open for the native work.
