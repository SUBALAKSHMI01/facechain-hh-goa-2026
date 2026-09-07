# `examples/`

Reference input / output layout from the spec's "Recommended
Directory Structure". Drop your own test image at
`examples/input/person.jpg` (or any other filename) and run:

```bash
python main.py analyze examples/input/person.jpg
# writes: artifacts/evidence/evidence.json
```

`examples/output/` is reserved for evidence or verification files
you generate as part of a demo; it is git-ignored.
