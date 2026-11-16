# The Golden Hour: Bluepoint Homes Outbound Lead-Qualification Voice Agent

> **CallKaro Agent ID:** `6afae6648efa21df5367c3e0` · **Published Version:** `v12-token-filter` · **Persona:** Ananya (Multilingual: Hinglish / English / Hindi)

In residential real estate, the **first five minutes after an enquiry ("The Golden Hour")** determine whether a lead converts or goes cold. This project implements an outbound voice AI agent for **Bluepoint Homes** on CallKaro that dials a property lead within minutes of their portal, WhatsApp, or missed-call enquiry.

Already knowing the exact property and stated budget from the CRM payload, the agent:
1. **Confirms fit** without re-asking what the lead already submitted on the form.
2. **Pitches in the lead's preferred language** (Hinglish, English, or Hindi) and adapts to their buying purpose (family self-use vs. investment).
3. **Handles pushback and objections strictly from verified facts**—never inventing amenities, discounts, or artificial scarcity.
4. **Checks live inventory and books a real site visit** into a capacity-checked database with an atomic booking reference (`BV-XXXX`).
5. **Produces a structured 20-field post-call handoff and deterministic lead score** so a human closer can act immediately without listening to the call recording.

---

## Quick Links & Submission Artifacts

| Artifact | Path / Details |
|---|---|
| **Re-importable Agent Export (`v12`)** | [`submission/submission.json`](submission/submission.json) |
| **Recording 1 (Pune · Hinglish · Booked `BV-8CB7`)** | [`submission/recordings/recording-1_pune_hinglish_visit-booked_BV-8CB7.mp3`](submission/recordings/recording-1_pune_hinglish_visit-booked_BV-8CB7.mp3) |
| **Recording 2 (Bengaluru · English · Booked `BV-AAB4`)** | [`submission/recordings/recording-2_bengaluru_english_visit-booked_BV-AAB4.mp3`](submission/recordings/recording-2_bengaluru_english_visit-booked_BV-AAB4.mp3) |
| **System Architecture & Design Doc** | [`docs/DESIGN.md`](docs/DESIGN.md) |
| **16-Scenario Test Suite & 12-Version Iteration Log** | [`docs/TEST-REPORT.md`](docs/TEST-REPORT.md) |
| **Live Role-Play Recording Scripts** | [`docs/RECORDING-SCRIPTS.md`](docs/RECORDING-SCRIPTS.md) |

---

## 1. End-to-End Architecture

```text
 Enquiry (99acres / WhatsApp / Web)
   │
   ▼
 scripts/dispatch.py
   ├── 1. Validates property JSON has all 16 required factual fields (refuses gaps)
   ├── 2. Checks Bluepoint Sales Desk Do-Not-Call list via Supabase RPC (is_dnd)
   └── 3. Dispatches call via `ck calls make --var ...` with raw lead + property facts
   │
   ▼
 ┌──────────────────────── CallKaro Agent (Advanced Mode) ────────────────────────┐
 │                                                                                │
 │  [PRE-CALL] prepare_call_context.py (Python)                                   │
 │   • Converts raw INR ints → speakable Indian currency ("₹92 lakh to ₹1.04 Cr") │
 │   • Computes per-unit budget fit & exact gap in code (LLM never does math)     │
 │   • Derives enquiry recency ("about 4 minutes ago") & IST time greeting        │
 │   • Validates offer expiry; maps empty offer/scarcity to literal `NONE`        │
 │   • Marks any missing optional metadata as literal `NOT AVAILABLE`             │
 │                                                                                │
 │  [CONVERSATION] Single Cached Context (callkaro/arjuna-2.5, temp 0.3)          │
 │   • Modular prompt: role · goal · 6-step call flow + 4 branches                │
 │   • 13 objection playbooks · strict factual & privacy guardrails               │
 │   • Dynamic `CALL DATA` block placed at the very end for prefix caching        │
 │                                                                                │
 │  [IN-CALL TOOLS]                                                               │
 │   • check_visit_slots ──► Supabase RPC `get_visit_slots` (live open slots)     │
 │   • book_site_visit   ──► Supabase RPC `book_site_visit` (atomic, idempotent,  │
 │                           capacity-checked, returns `BV-XXXX` + spoken ref)    │
 │   • end_call          ──► Clean call termination after closing summary/opt-out │
 │                                                                                │
 │  [POST-CALL] 20-Field Extractor (`krishna-2.5`) + handoff_to_closer.js (JS)    │
 │   • Normalizes booking ref (`BV8CB7` → `BV-8CB7`)                              │
 │   • Computes deterministic lead_score (0–100), temperature, and P1/P2/P3       │
 │   • Sets CallKaro disposition_reason & conversion_status                       │
 │   • Writes closer card to Supabase `record_handoff` RPC & DND on opt-out       │
 └────────────────────────────────────────────────────────────────────────────────┘
   │
   ▼
 Bluepoint Sales Desk (Supabase · ap-south-1)
   • Tables: `visit_slots`, `site_visits`, `lead_handoffs`, `do_not_call`
   • View:   `closer_queue` (prioritized action queue for human sales managers)
   • Security: Row-Level Security (RLS) enabled; tables locked behind `SECURITY DEFINER` RPCs
```

---

## 2. Core Engineering Principles

### A. Zero Property Hardcoding (100% Swappable Listing Data)
The agent prompt contains **zero hardcoded facts** about any property. Every project attribute—name, locality, RERA ID, unit configurations, carpet vs. built-up area, price range, construction status, possession date, payment plan, loan partners, offers, and inventory scarcity—is injected at call time.

To prove swappability, the **exact same published agent version** (`v12-token-filter`) powers two completely different properties:
1. **Bluepoint Skyline Residences (`BP-PUN-SKY`, Kharadi, Pune):** Under-construction 2 & 3 BHK apartments (Dec 2027 possession), carpet area pricing, **no active offer (`NONE`)**, **no scarcity figure (`NONE`)**, pitched in **Hinglish**.
2. **Bluepoint Palm Grove Villas (`BP-BLR-PALM`, Sarjapur Road, Bengaluru):** Ready-to-move 3 & 4 BHK gated villas (OC received), built-up area pricing, **active stamp-duty offer**, **real scarcity (`6 of 48 villas unsold`)**, pitched in **English**.

Pointing `dispatch.py` at a different property JSON switches vocabulary, language, valid offers, sales manager name, and live slot inventory without touching the agent prompt.

### B. Code Does the Math, Never the LLM
LLMs frequently misread multi-digit Indian rupee figures (`9200000` vs `10400000`) or hallucinate whether a ₹1 Cr budget fits a ₹92L–₹1.04Cr unit.
In this architecture, `prepare_call_context.py` pre-computes:
- `units_spoken`: `"2 BHK (780 sq ft carpet): ₹92 lakh to ₹1.04 crore; 3 BHK (1,080 sq ft carpet): ₹1.28 crore to ₹1.42 crore"`
- `budget_fit`: `"fits"` | `"stretch"` | `"below_range"` | `"unknown"`
- `budget_fit_note`: `"Budget ₹1 crore. 2 BHK fits at the lower end of its range (starts at ₹92 lakh; the top of the range is about ₹4 lakh above budget); 3 BHK starts about ₹28 lakh above budget."`
- `booking_ref_spoken`: Returned by `book_site_visit.py` as `"B V, 8 C B 7"` so TTS never misreads alphanumeric codes.

### C. Explicit Absence (`NONE` and `NOT AVAILABLE`)
When a property has no discount offer or no inventory count (or when `offer_valid_till` is in the past), `prepare_call_context.py` sets `offer_line = "NONE"` and `scarcity_line = "NONE"`. Even under repeated caller pressure (*"Koi discount chal raha hai? Kitne flats bache hain?"*), the agent has no numbers to exaggerate and is bound by guardrails to state plainly that no offer or unit-count figure is on record.

### D. Prompt Prefix Caching for Sub-Second Latency
CallKaro caches the static prompt prefix up to the first `{{variable}}`. `scripts/build_agent.py` enforces a build-time invariant: the prose uses `<placeholder>` tags (`<property_name>`, `<budget_fit_note>`), and all 29 `{{variable}}` bindings are emitted in a single `CALL DATA` block at the very end of the prompt. Combined with `callkaro/arjuna-2.5` and ElevenLabs Flash v2.5, live calls achieved an average turn latency of **0.77s** (0.50s EOS + 0.15s LLM TTFT + 0.12s TTS).

---

## 3. Conversation Design & Guardrails

### 6-Step Main Flow
1. **STEP 1 — Open:** Greet by name in `<opening_language>`, identify as Ananya from Bluepoint Homes, reference `<property_name>` and `<enquiry_recency>`, and check if the lead has two minutes.
2. **STEP 2 — Qualify (Confirm, Don't Re-Ask):** Acknowledge known form data (`<lead_config_pref>`, `<lead_budget_spoken>`, `<lead_note>`) and ask only for missing qualification signals (self-use vs. investment, timeline, configuration/budget confirmation).
3. **STEP 3 — Confirm Fit Honestly:** Relay `<budget_fit_note>` transparently—distinguishing between full fit, lower-end fit, a <10% stretch, or below-range without pushing out-of-budget buyers.
4. **STEP 4 — Tailored Pitch:** Share 1–2 relevant facts matched to buyer purpose (schools/commute/amenities for families; connectivity facts for investors without inventing rental yield or appreciation percentages).
5. **STEP 5 — Next Step (Site Visit Booking):** Ask for a preferred day → call `check_visit_slots` → offer two concrete slots → ask visitor headcount → call `book_site_visit` → read out `booking_ref_spoken` clearly.
6. **STEP 6 — Close:** Summarize the outcome (slot + booking reference + sales manager name, or callback time) and invoke `end_call` in the same turn.

### 4 Dedicated Branches
- **BRANCH A (Busy / Callback):** Ask when to call back, **wait for the lead's answer**, repeat the time, and close.
- **BRANCH B (Speak to Human / Sales Manager):** Explain honestly that live call transfer isn't available, log their preferred callback time and specific questions for `<sales_manager_name>`, and close.
- **BRANCH C (Wrong Person / Third Party):** Never disclose property details, configurations, or prices to anyone other than `<lead_name>`. Apologize or note a callback time if it is a family member, then close.
- **BRANCH D (Opt-Out / Do Not Call):** Highest priority. Acknowledge immediately in one polite sentence, call `end_call`, and let `handoff_to_closer` permanently record the number in the DND table.

### 13 Objection Playbooks
Located in [`agent/prompt/rebuttals.md`](agent/prompt/rebuttals.md), covering:
1. Price too high / above budget
2. Cheaper competitor project nearby
3. Under-construction / possession delay fear (cites RERA ID + actual construction status)
4. RERA / legal / title questions
5. Location / distance / traffic concerns
6. "Just browsing / researching"
7. "Just WhatsApp / email me the brochure" (honestly states it cannot send messages; offers sales manager follow-up)
8. "I'm busy / in a meeting"
9. "How did you get my number?"
10. Asking for a discount or special deal
11. Asking how many units are left or if prices will increase
12. "Are you an AI / bot?" (answers honestly: AI assistant calling on behalf of Bluepoint Homes)
13. Already bought elsewhere / no longer looking

---

## 4. Post-Call Extraction & Deterministic Closer Handoff

After every call, CallKaro's `krishna-2.5` extracts **20 structured fields** defined in [`agent/config.json`](agent/config.json):
- **Disposition & Routing:** `outcome`, `opted_out`, `site_visit_booking_ref`, `site_visit_slot`, `callback_time`, `language_used`
- **Qualification Profile:** `budget_confirmed`, `budget_fit`, `config_interest`, `buyer_purpose`, `purchase_timeline`, `home_loan`
- **Sales Intelligence:** `objections_raised`, `unanswered_questions`, `competitors_mentioned`, `closer_summary`, `next_best_action`

Then [`agent/functions/handoff_to_closer.js`](agent/functions/handoff_to_closer.js) runs automatically to compute a **deterministic 0–100 lead score** (identical answers always produce the exact same score):

| Dimension | Scoring Breakdown |
|---|---|
| **Outcome (max 40)** | `site_visit_booked`: +40 · `human_callback_requested`: +30 · `callback_scheduled`: +20 · `nurture_follow_up`: +10 |
| **Budget Fit (max 20)** | `fits`: +20 · `stretch`: +12 · `unknown`: +5 · `below_range`: 0 |
| **Timeline (max 20)** | `0_3_months`: +20 · `3_6_months`: +14 · `6_12_months`: +7 · `over_12_months`: +2 · `unknown`: +3 |
| **Purpose (max 10)** | `self_use` / `both`: +10 · `investment`: +8 · `unknown`: +3 |
| **Home Loan (max 10)** | `not_needed`: +10 · `needed`: +7 · `undecided`: +4 · `unknown`: +3 |
| **Disqualifiers** | `opted_out`, `not_interested`, `wrong_person`, `no_conversation` → forced to `0` |

- **Temperature:** `hot` ($\ge 70$), `warm` ($45\text{–}69$), `cold` ($< 45$), `do_not_call`, or `disqualified`.
- **Priority:** `P1` (hot or site visit booked), `P2` (warm), `P3` (cold), `none` (opted out).
- **Conversion Status:** Set to `true` **only** when `outcome == "site_visit_booked"` and a valid `booking_ref` exists.

---

## 5. Testing & 12-Version Iteration Summary

The test suite in [`tests/suite.py`](tests/suite.py) defines **16 simulation scenarios** across four priority tiers, complete with realistic tool mocks (`slot_id=99`, `BV-ZZ9X` sentinels) and pre-computed call variables:

- **P0 Integrity (7 tests):** `P0_URGENCY_TRAP` (3x pressure for discount/scarcity on a property with `NONE`), `P0_MISSING_FACTS` (5 out-of-data questions: vastu, floor rise, maintenance, exact floor availability, school distance), `P0_OPT_OUT`, `P0_BOOKING_ERROR`, `P0_HESITATION_NO_BOOK`, `P0_WRONG_PERSON` (father answers), `P0_INJECTION_BOT` (prompt injection + bot check).
- **P1 Structure (4 tests):** `P1_BELOW_BUDGET` (₹55L budget vs ₹92L start), `P1_NO_SLOTS_DAY`, `P1_LANG_SWITCH` (Hinglish to English mid-call), `P1_BUSY_CALLBACK`.
- **P2 Pushback (3 tests):** `P2_COMPETITOR_DELAY` (₹85L competitor + cousin's 3-year delay), `P2_WHATSAPP_STALL`, `P2_NRI_INVESTOR` (unscripted Dubai NRI asking for rental yield & brother proxy visit).
- **P3 Happy Paths (2 tests):** `P3_HAPPY_PUNE_HINGLISH` and `P3_HAPPY_BLR_SWAP` (same agent version tested on Bengaluru villas in English).

### Key Milestones Across 12 Versions (`v1` → `v12-token-filter`)
- **`v1` → `v2-promptfix`:** Jumped simulation pass rate from **6/16 to 12/16** by adding headcount check before booking, waiting for callback time before ending, and stripping leaked turn markers.
- **`v3-gpt41` (A/B Test):** Tested `gpt-4.1` against `callkaro/arjuna-2.5`; rejected `gpt-4.1` (7/16 vs 12/16) due to repeated closing paragraphs and higher latency/cost.
- **`v4` → `v6-scarcity-fact`:** Banned manufactured urgency phrases (`"construction tezi se chal raha hai"`, `"before they are all gone"`), protected privacy on wrong-person calls (`v5`), and calibrated neutral reporting of real inventory facts (`v6`).
- **`v7` → `v10-no-ask-and-hangup`:** Enforced truthful closing states on failed bookings (`v7`), added `booking_ref_spoken` in code (`v8`), capped repeated brochure stalls (`v9`), and enforced the global rule that a turn containing a question never calls `end_call` (`v10`).
- **`v11-ref-normalise` & `v12-token-filter` (From Live Call Verification):** Normalised extracted booking references (`BV8CB7` → `BV-8CB7`) so the closer queue links bookings to phone numbers reliably, and filtered leaked internal reasoning tokens (`decomposition`, `<|"|>thought`) from TTS output.

Full transcript analyses and live call metrics are documented in [`docs/TEST-REPORT.md`](docs/TEST-REPORT.md).

---

## 6. Repository Layout

```text
├── agent/
│   ├── config.json                     # Voice (ElevenLabs/Sarvam), STT (Soniox/Azure), LLM, 20-field post-call schema
│   ├── functions/
│   │   ├── prepare_call_context.py     # Pre-call: INR formatting, budget fit math, recency, NONE/NOT AVAILABLE guards
│   │   ├── check_visit_slots.py        # In-call: queries open site-visit slots via Supabase RPC
│   │   ├── book_site_visit.py          # In-call: atomic slot booking via Supabase RPC + spoken reference formatting
│   │   └── handoff_to_closer.js        # Post-call: deterministic scoring, ref normalization, closer card & DND write
│   └── prompt/
│       ├── role.md                     # Persona (Ananya), tone, language adaptation, phonetic pronunciation rules
│       ├── goal.md                     # Primary objective & non-negotiable constraints
│       ├── call_flow.md                # 6-step conversation flow + 4 specialized branches
│       ├── instructions.md             # Turn-taking, function-calling rules, spoken format guidelines
│       ├── guardrails.md               # 10 strict safety, privacy, and anti-hallucination guardrails
│       └── rebuttals.md                # 13 structured objection-handling playbooks
├── data/
│   ├── leads/
│   │   ├── rohan-pune.json             # 99acres lead for Pune apartments (₹1 Cr budget, 2 BHK, Hinglish)
│   │   └── priya-bengaluru.json        # WhatsApp lead for Bengaluru villas (₹2.5 Cr budget, 3 BHK, English)
│   └── properties/
│       ├── BP-PUN-SKY.json             # Bluepoint Skyline Residences, Kharadi, Pune (under construction, no offer)
│       └── BP-BLR-PALM.json            # Bluepoint Palm Grove Villas, Sarjapur Rd, Bengaluru (ready, offer + scarcity)
├── scripts/
│   ├── build_agent.py                  # Compiles agent/ sources into build/agent.json & build/patch.json
│   ├── callctx.py                      # Runs prepare_call_context.py locally to preview derived variables
│   ├── ckrun.py                        # Wrapper for invoking the CallKaro (`ck`) CLI cleanly on Windows/POSIX
│   ├── dispatch.py                     # Validates property data, checks Supabase DND, and places outbound call
│   └── sim.py                          # Syncs 16 test scenarios to CallKaro, triggers runs, and writes reports
├── tests/
│   ├── suite.py                        # 16 P0–P3 simulation scenarios, caller personas, mocks, and grading criteria
│   ├── sim_ids.json                    # CallKaro simulation test ID mapping
│   └── results/                        # Raw JSON outputs and readable markdown transcripts for every test run
├── submission/
│   ├── submission.json                 # Re-importable CallKaro export of published v12-token-filter
│   └── recordings/                     # Final MP3 call recordings (Pune Hinglish & Bengaluru English)
├── docs/
│   ├── DESIGN.md                       # Architectural decisions, variable design, and conversation flow
│   ├── TEST-REPORT.md                  # Iteration history (v1–v12), defect log, and live call verification
│   └── RECORDING-SCRIPTS.md            # Role-play scripts used for live test calls
└── build/                              # Compiled agent payloads and version snapshots (v1–v12)
```

---

## 7. Setup & Usage Commands

### Prerequisites
1. **Python 3.10+** (with `pytz` installed for local pre-call simulation).
2. **CallKaro CLI (`ck`)** installed and authenticated (`ck auth login`).
3. **Environment Variable (`.env`):** Create a git-ignored `.env` file in the project root containing the Supabase publishable key for pre-call DND checks:
   ```ini
   BLUEPOINT_DESK_KEY=sb_publishable_...
   ```
   *(Inside CallKaro's cloud runtime, this same key is stored in the organization secret store as `BLUEPOINT_DESK_KEY`.)*

### Common Workflows

```bash
# 1. Assemble build/agent.json and build/patch.json from agent/ source files
python scripts/build_agent.py v12-token-filter

# 2. Preview what the pre-call Python function derives for a lead + property locally
python scripts/callctx.py data/leads/rohan-pune.json
python scripts/callctx.py data/leads/priya-bengaluru.json

# 3. Place an outbound test call (validates property fields & checks DND list first)
python scripts/dispatch.py data/leads/rohan-pune.json --to 91XXXXXXXXXX
python scripts/dispatch.py data/leads/priya-bengaluru.json --to 91XXXXXXXXXX

# 4. Demonstrate property swappability (call Rohan's lead file but pitch Bengaluru villas)
python scripts/dispatch.py data/leads/rohan-pune.json --property BP-BLR-PALM --to 91XXXXXXXXXX

# 5. Dry-run a dispatch command without dialing
python scripts/dispatch.py data/leads/rohan-pune.json --to 919876543210 --dry-run

# 6. Sync all 16 simulation tests to CallKaro, run the suite, and fetch transcripts
python scripts/sim.py sync
python scripts/sim.py run <versionId> all
python scripts/sim.py results <runId>
```

---

## 8. Backend & Security (`bluepoint-sales-desk`)

The backend runs on **Supabase (`ap-south-1`)**. Direct table access is blocked via Row-Level Security (RLS); the agent and dispatcher interact exclusively through four `SECURITY DEFINER` Postgres RPCs using `BLUEPOINT_DESK_KEY`:

| RPC Function | Called By | Purpose |
|---|---|---|
| `is_dnd(p_phone)` | `scripts/dispatch.py` | Blocks outbound dialing if the phone number has previously opted out. |
| `get_visit_slots(p_property_id, p_day)` | `check_visit_slots.py` | Returns open, future site-visit slots with remaining capacity for the given property. |
| `book_site_visit(...)` | `book_site_visit.py` | Atomically verifies slot capacity, increments headcount, and returns an idempotent `BV-XXXX` booking reference. |
| `record_handoff(p)` | `handoff_to_closer.js` | Writes the 20 extracted fields + deterministic lead score to `lead_handoffs`, links the caller's phone number to `site_visits`, and inserts into `do_not_call` if `opted_out = true`. |
