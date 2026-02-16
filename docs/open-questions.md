# Open Questions

These are intentional decisions that may be re-evaluated after initial integration:

## 1) Socket path strictness

Current state:

- daemon config requires explicit `HERZEN_WAKEWORD_SOCKET`
- dev script supplies a default for convenience

Question:

- should daemon itself also support a default path to mirror Herzen client behavior?

## 2) Sample rate hard enforcement

Current state:

- `HERZEN_WAKEWORD_SAMPLE_RATE` is currently enforced to `16000`

Question:

- keep hard lock for MVP simplicity or allow alternate sample rates with resampling?

## 3) Client concurrency policy

Current state:

- additional clients are rejected with `CLIENT_BUSY`

Question:

- keep reject policy or prefer replacing existing client when Herzen restarts?

## 4) Model asset strategy

Current state:

- model binaries are not committed
- setup uses runtime download into `models/`

Question:

- keep download-at-setup workflow or introduce release-managed model packaging?

## 5) End-to-end integration coverage

Current state:

- config/protocol unit tests exist
- no automated full integration test against live Herzen process

Question:

- add a small automated reconnect smoke suite once main repo integration stabilizes?
