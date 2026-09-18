# Generated canonical schemas

The Pydantic models in `src/ragged_claws/models/` are the only schema authority. Files ending in
`.schema.json` in this directory are generated artifacts and must not be edited by hand.

Regenerate all schemas from the repository root:

```text
uv run python -m ragged_claws.schema_generation
```

Check that committed schemas exactly match the authoritative models without changing files:

```text
uv run python -m ragged_claws.schema_generation --check
```

Generation uses sorted JSON keys and stable filenames. The test suite and CI run the drift check.

Canonical identity fields are opaque UUIDs assigned by a future resolution/canonicalization layer.
They are not derived from names, aliases, normalized text, or ticker symbols.

`SourceObservation` records captured source-native material. `Provenance` records how canonical
records were derived from observations. `EventEvidence` associates one canonical event with one or
more observations that support it; multiple observations therefore need not become duplicate
events.
