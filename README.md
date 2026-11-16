# The Golden Hour: Bluepoint Homes lead-qualification voice agent (CallKaro)

An outbound AI agent that calls a property lead within minutes of their enquiry. It confirms fit for the exact property they asked about, pitches in their language, answers pushback from facts, **books a real site visit**, and leaves a written outcome that a human closer can act on without listening to the recording.

- **Agent:** `6afae6648efa21df5367c3e0`. Published version `v12-token-filter`; 12 versions of iteration history.
- **Submission:** [submission/submission.json](submission/submission.json) (re-importable export of v12) and two recordings in [submission/recordings/](submission/recordings/):
  - `recording-1_pune_hinglish_visit-booked_BV-8CB7.mp3`
  - `recording-2_bengaluru_english_visit-booked_BV-AAB4.mp3`
- **Design:** [docs/DESIGN.md](docs/DESIGN.md) · **Testing and iteration:** [docs/TEST-REPORT.md](docs/TEST-REPORT.md) · **Recording scripts:** [docs/RECORDING-SCRIPTS.md](docs/RECORDING-SCRIPTS.md)

## Layout
| Path | What |
|---|---|
| `agent/prompt/*.md` | role, goal, call flow, instructions, guardrails, rebuttals (editable source) |
| `agent/functions/` | `prepare_call_context.py` (pre-call), `check_visit_slots.py` and `book_site_visit.py` (in-call), `handoff_to_closer.js` (post-call) |
| `agent/config.json` | voice, transcriber, LLM, call settings, 20-field post-call schema |
| `data/properties/` | two invented properties (Pune apartments, Bengaluru villas) |
| `data/leads/` | sample enquiries |
| `tests/suite.py` | 16 simulation scenarios (P0–P3) with mocks and strict criteria |
| `tests/results/` | raw JSON and readable transcripts for every simulation run |
| `scripts/` | `build_agent.py`, `sim.py` (sync/run/results), `dispatch.py` (DND check + test call), `callctx.py` (runs the real pre-call code locally) |

## Common commands
```bash
python scripts/build_agent.py vN                     # assemble build/agent.json + build/patch.json
python scripts/sim.py sync                           # create/update all tests on CallKaro
python scripts/sim.py run <versionId> all            # run the suite
python scripts/sim.py results <runId>                # save + summarise results
python scripts/callctx.py data/leads/rohan-pune.json # preview what the pre-call code derives
python scripts/dispatch.py data/leads/priya-bengaluru.json --to 91XXXXXXXXXX   # test call
python scripts/dispatch.py data/leads/rohan-pune.json --property BP-BLR-PALM --to …  # same lead, other property
```

## Backend
The Supabase project `bluepoint-sales-desk` (ap-south-1) holds visit slots, bookings, closer handoffs and the do-not-call list. Tables are locked by row-level security and reached only through four RPCs. The agent authenticates with the CallKaro secret `BLUEPOINT_DESK_KEY` (a publishable key).
