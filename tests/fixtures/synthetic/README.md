# Synthetic source-shape fixtures

These files are invented test data. They are not copied source or vendor payloads, do not describe
real people or transactions, and are not intended to document or guarantee any provider contract.

They exist only to prove that future adapters can map representative SEC-, normalized-vendor-, and
LittleSis-like semantics into the canonical models. The test-only mapping code is deliberately not
a production adapter.


`persistence_event_v1.json` and `persistence_event_v2.json` are the deliberately tiny M0
`SyntheticAdapter` inputs. They share an invented source-native ID but have different exact bytes
and disclosed amounts so append-only source-version behavior can be tested without implying that
production canonical correction/reconciliation is solved.
