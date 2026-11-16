# Bluepoint Golden Hour: outbound lead-qualification agent

CallKaro agent `6afae6648efa21df5367c3e0` · persona **Ananya** (female, Hinglish/English/Hindi) · Bluepoint Homes (fictional)

An enquiry arrives (portal, WhatsApp form, missed call). Within minutes the agent calls, already knowing the property and the lead's stated budget. It confirms fit, pitches in the lead's language, answers pushback from facts, books a real site visit, and leaves a written handoff that a human closer can act on without listening to the recording.

---

## 1. Architecture

```
 enquiry ──► dispatch.py ──► ck calls make --var … (raw lead + property facts)
               │  validates the property has every fact; refuses gaps
               │  checks Sales Desk do-not-call list
               ▼
 ┌──────────────────── CallKaro agent (Advanced / type 1) ────────────────────┐
 │ PRE-CALL  prepare_call_context (Python)                                    │
 │   raw INR → "₹92 lakh to ₹1.04 crore"; budget fit per config + gap;         │
 │   enquiry recency; greeting; offer/scarcity → exact fact or NONE;           │
 │   missing facts → NOT AVAILABLE                                            │
 │ CONVERSATION  role · goal · call flow (6 steps + 4 branches) ·             │
 │   instructions · guardrails · rebuttals · call data block (last, cacheable) │
 │ IN-CALL   check_visit_slots ──► Supabase RPC get_visit_slots               │
 │           book_site_visit   ──► Supabase RPC book_site_visit (atomic,      │
 │                                  capacity-checked, idempotent, returns ref) │
 │           end_call                                                         │
 │ POST-CALL 20 extracted fields → handoff_to_closer (JavaScript):             │
 │   deterministic lead score/temperature/priority, disposition, conversion,  │
 │   closer card → Sales Desk, booking ↔ phone link, opt-out → do_not_call     │
 └────────────────────────────────────────────────────────────────────────────┘
               ▼
 Bluepoint Sales Desk (Supabase, ap-south-1): visit_slots · site_visits ·
 lead_handoffs · do_not_call · closer_queue view. Tables are reachable only
 through security-definer RPCs; the publishable key cannot read tables directly.
```

### Why one structured prompt and not a pathway graph
Sales calls don't run in order. A lead may ask the price in the first ten seconds, raise an objection halfway through qualifying, or ask to be called back. With one context (CallKaro Advanced mode), the agent can answer anything at any point and then return to the flow. Replies stay fast because the static prompt is cached: every `{{variable}}` sits in a final call-data block. The agent also copes with callers nobody scripted (see the NRI-investor test).

Rules that must never break are enforced outside the prose:

- **Booking:** `book_site_visit` only accepts a `slot_id` that belongs to the property. The database rejects full or past slots, and books atomically.
- **Maths:** prices, gaps and fit are computed in code, never by the model.
- **Urgency:** with no offer or units-left figure, the agent receives the literal word `NONE`. There is nothing for it to bend.
- **Opt-out:** it is ended in the call and made durable after the call, in the do-not-call table that the dialer checks.

### Why the action is a site-visit booking
In Indian residential sales, the site visit is the stage that predicts a closing, and it's what tele-callers are measured on. Booking it while the lead is still interested converts intent into a commitment. The visit goes into a real inventory (slots with capacity) and comes back with a reference the lead can quote. A human closer only spends time on leads who have committed to a time.

---

## 2. Data and variable design (the property is fully swappable)

The prompt contains **no property facts**. Facts arrive at call time in two layers, plus a layer derived in code:

| Layer | Variables | Source |
|---|---|---|
| Lead | `lead_name, enquiry_source, enquiry_at, lead_budget_inr, lead_config_pref, lead_language, lead_note` | enquiry form / CRM |
| Property | `property_id, property_name, property_type, city, locality, units_json[], price_basis, construction_status, possession, rera_id, amenities, location_highlights, payment_plan, loan_partners, current_offer, offer_valid_till, inventory_fact, site_address, sales_manager_name` | listing record (`data/properties/*.json`) |
| Derived (pre-call) | `units_spoken, lead_budget_spoken, budget_fit, budget_fit_note, enquiry_recency, time_greeting, offer_line, scarcity_line, opening_language, missing_facts` | `prepare_call_context` |

Design rules:

- **Raw data in, speakable data out.** CRMs send numbers and ISO dates. The pre-call function turns them into "₹1.38 crore" and "fits at the lower end; top of range ≈₹4 lakh above budget". The LLM never calculates.
- **Absence is explicit.** An empty offer or inventory field becomes `NONE`, and any other missing fact becomes `NOT AVAILABLE`. The prompt treats both as "you do not know this". An expired offer (`offer_valid_till` in the past) is removed automatically.
- **Structure-tolerant.** `units_json` is a list of any length and any configuration (2/3 BHK apartments or 3/4 BHK villas, carpet or built-up area).
- **Proof of swappability.** The same published version runs both properties. *Skyline Residences, Pune* is under construction, with no offer and no inventory figure. *Palm Grove Villas, Bengaluru* is ready to move in, with a real stamp-duty offer and a real "6 of 48 unsold" figure. Pointing the agent at Bengaluru changes the vocabulary (villas, built-up area), the urgency it may legitimately use, the language (English), the sales manager and the slots, all without editing the script.

---

## 3. Conversation design

**Call flow:** open → qualify (confirm, don't re-ask, what the enquiry already says) → confirm fit (from `budget_fit_note`) → tailored pitch (family, investor, ready-to-move or price-sensitive angle; one or two facts) → next step (check slots → offer two → ask headcount → book → confirm the reference in the closing turn) → close.

**Branches:** callback (ask, *wait*, repeat, close), sales manager (no transfer exists, so it notes a time and the questions), wrong person (no disclosure), opt-out (highest priority: one sentence, then `end_call`).

**Language "literally and figuratively":** it opens in the enquiry form's language and mirrors any switch, while keeping one name, one voice, and feminine Hindi forms throughout. The pitch angle follows the buyer's purpose: schools and commute for families; connectivity facts only for investors, with no yield or appreciation claims.

**Pushback:** acknowledge → clarify → one fact or an honest "the sales manager will confirm" → a low-commitment next step. If the lead pushes back twice on the same point, respect it. There are 13 objection playbooks (price, cheaper competitor, possession delay, RERA/title, location, browsing, "WhatsApp me", busy, "how did you get my number", discount, units left / price rise, "are you a bot", already bought).

**Guardrails:** no invented facts; no manufactured urgency (even around real facts, banned phrases are listed); no negotiation; opt-out is absolute; no claimed actions without a function result; one property only; privacy; honesty about fit; stays in role; calm under abuse; never claims to be human.

---

## 4. Outcome: readable without the recording

Post-call extraction (20 fields; CallKaro `krishna-2.5`):

- `outcome`: booked / sales-manager callback / callback / nurture / not interested / opted out / wrong person / no conversation
- `opted_out`, `site_visit_booking_ref`, `site_visit_slot`, `callback_time`
- `budget_confirmed`, `budget_fit`, `config_interest`, `buyer_purpose`, `purchase_timeline`, `home_loan`
- `objections_raised` (with how each was answered), `unanswered_questions` (the closer's to-do list), `competitors_mentioned`, `language_used`
- `closer_summary`, `next_best_action`

`handoff_to_closer` then adds a **deterministic** `lead_score` (0–100), `lead_temperature` and `lead_priority`, sets `disposition_reason` and `conversion_status` (true only with a booking reference), and writes the closer card to `closer_queue`. Conversion = a site visit booked with a reference.

---

## 5. Testing

Sixteen simulated scenarios in priority tiers. Every test has a scripted caller, numbered pass/fail criteria with the universal FAIL lines, realistic mocks of every in-call function, and call variables generated by running the real pre-call code. See [TEST-REPORT.md](TEST-REPORT.md) for the iteration history (v1 → v2/v3 → v4 …).

The naive-agent breaker is `P0_URGENCY_TRAP`: a lead pushes three times for a discount, a units-left figure and a price-rise warning on a property with no offer and no inventory data, then cites a competitor's "3 flats left, 2 lakh off".

## 6. Settings worth noting
- LLM `callkaro/arjuna-2.5`, chosen over gpt-4.1 by an A/B on the full suite (12/16 vs 7/16 after the same prompt fixes), with gpt-4.1-mini as fallback. Temperature 0.3; response caching.
- Voice: ElevenLabs flash v2.5 "Monika – Lead Qualification" (hi), with Sarvam bulbul:v3 "Simran" as fallback. STT: Soniox [hi, en] for code-switching, with Azure [hi-IN, en-IN] as fallback.
- `substrings_to_remove` strips leaked turn markers and function names before speech (a defect found in v1).
- 7-minute cap, dynamic silence prompts in the current language, background office ambience, noise cancellation.
