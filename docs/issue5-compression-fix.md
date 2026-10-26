# Issue #5: compression portability

v0.2.6 shipped a Python 3.13 executable using zlib 1.3.1, while the pinned
translation output hashes were generated with Python 3.14 / zlib-ng. Both
compressors produce valid streams with identical decompressed data, but their
output bytes differ. The installer incorrectly rejected those byte differences.
Renaming a mod only causes its recipe to be skipped; it does not fix the error.

Reproduction on the pinned BattensWrecks.esm input:

- Input SHA-256: `71e26c630480e1688cfc9ccdd1d4e6f8f7d3a857b9ae16358530a2afaad63bd6`
- 72 translations applied with either runtime.
- Python 3.14 / zlib-ng output: `8bafc69b2da9439990d63205a51a211d38c12ff13d216965a0e9b8767338e956`
- Python 3.13 / zlib output: `cb7148c7c4bee43f0cc887d459a0a2a6add004b9b54e18159389002577a1cf65`

v0.2.7 adds pinned content hashes for all 138 plugin recipes and four SWF
font/HUD recipes. Metadata generation requires each output to first match the
existing release's exact byte hash. The original output hashes remain unchanged.

For plugins the v1 content hash decompresses record bodies and recalculates only
record and enclosing group lengths. It preserves every other byte, including
record order, flags, headers, FormIDs, unknown fields and untranslated data.
For SWFs the v1 content hash preserves the entire original eight-byte header and
decompressed body. Both reject truncated streams, extra compressed trailing data
and incorrect declared sizes.

When the release byte hash differs, generation requires the matching pinned
content hash. It then records the actual output byte hash in prepared.json and
the backup journal. Apply, staging tamper detection and restore continue to use
exact byte hashes. Missing or incorrect content metadata still stops generation.
Other operation types retain their existing exact output check.

To reproduce the read-only full recipe check on clean Genesis 8.8.4 originals:

```powershell
python scripts/validate_plugin_outputs.py --game 'D:\Star Wars Genesis\Game'
```

Run under both Python 3.13 and 3.14. `--write-metadata` is only for maintainers
using the original reference compressor: it refuses to pin any output that does
not match the historical release byte hash. No game files are written.

The release candidate builder runs the unit tests, checks the embedded payload,
launches the frozen EXE to initialize its real Tk widgets, and verifies the ZIP
and its SHA-256. CI also tests the source under both Python versions. This work
does not establish in-game playthrough coverage.
