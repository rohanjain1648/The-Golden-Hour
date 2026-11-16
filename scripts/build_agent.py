"""Assemble the CallKaro agent JSON from editable sources.

agent/config.json        settings, voice, transcriber, post-call schema
agent/prompt/*.md        role, goal, call_flow (text); instructions, guardrails, rebuttals ("- " items)
agent/functions/*        pre-call / in-call Python, post-call JavaScript

Outputs:
  build/agent.json   full create payload (ck agents create --file build/agent.json)
  build/patch.json   version-level fields only (ck agents update <id> --versions <vid> --set @build/patch.json)

The "Call data" block (every {{variable}}) is appended as the LAST rebuttals item so the
static prompt prefix stays cacheable (CallKaro caches up to the first {{variable}}).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agent"
BUILD = ROOT / "build"

# Every call-time variable the prompt may use. Raw = supplied by the dialer; derived = added by prepare_call_context.
CALL_VARIABLES = [
    ("lead_name", "raw"), ("enquiry_source", "raw"), ("enquiry_recency", "derived"), ("time_greeting", "derived"),
    ("opening_language", "derived"), ("lead_budget_spoken", "derived"), ("lead_config_pref", "raw"), ("lead_note", "raw"),
    ("property_id", "raw"), ("property_name", "raw"), ("property_type", "raw"), ("city", "raw"), ("locality", "raw"),
    ("units_spoken", "derived"), ("price_basis", "raw"), ("budget_fit", "derived"), ("budget_fit_note", "derived"),
    ("construction_status", "raw"), ("possession", "raw"), ("rera_id", "raw"), ("amenities", "raw"),
    ("location_highlights", "raw"), ("payment_plan", "raw"), ("loan_partners", "raw"), ("offer_line", "derived"),
    ("scarcity_line", "derived"), ("site_address", "raw"), ("sales_manager_name", "raw"), ("missing_facts", "derived"),
]


def items(md_text):
    """Split a markdown file into '- ' items (an item may span lines)."""
    out, cur = [], []
    for line in md_text.splitlines():
        if line.startswith("- "):
            if cur:
                out.append(" ".join(cur).strip())
            cur = [line[2:].strip()]
        elif line.strip() and cur:
            cur.append(line.strip())
    if cur:
        out.append(" ".join(cur).strip())
    return out


def read(p):
    return (AGENT / p).read_text(encoding="utf-8").strip()


def call_data_block():
    lines = ["CALL DATA (values for the <placeholders> used above; kept last so the prompt prefix is cacheable). "
             "A value of NOT AVAILABLE or NONE means you do not have that fact: never fill it in yourself."]
    for name, _ in CALL_VARIABLES:
        lines.append("<%s> = {{%s}}" % (name, name))
    return "\n".join(lines)


def functions():
    pre = read("functions/prepare_call_context.py")
    slots = read("functions/check_visit_slots.py")
    book = read("functions/book_site_visit.py")
    handoff = read("functions/handoff_to_closer.js")
    return [
        {"type": "end", "name": "end_call",
         "description": "End the call. Call it in the same turn as your goodbye after summarising the next step; "
                        "immediately after confirming an opt-out; or after apologising to a wrong person."},
        {"type": "custom_pre_call", "name": "prepare_call_context",
         "description": "Before dialing: converts raw lead and property data into speakable amounts, budget fit, "
                        "enquiry recency, greeting, offer/scarcity flags and missing-fact markers.",
         "source_code": pre, "update_call_data": True},
        {"type": "custom_in_call", "name": "check_visit_slots",
         "description": "Call this when the lead agrees to a site visit (or asks when they can see the property) and "
                        "has told you a preferred day, or says any day is fine. Returns the real open visit slots. "
                        "Never offer a visit time that did not come from this function.",
         "msg_while_executing_type": "dynamic", "msg_while_executing": [],
         "parameters": [
             {"key_name": "property_id", "type": "string", "description": "The property id from the call data"},
             {"key_name": "preferred_day", "type": "string", "description": "today, tomorrow, a weekday name in English (e.g. saturday), weekend, weekday, or empty for earliest"}],
         "source_code": slots, "update_call_data": False, "execute_while_switching": False},
        {"type": "custom_in_call", "name": "book_site_visit",
         "description": "Call this only after the lead has clearly chosen one slot that check_visit_slots returned in "
                        "this call, and you know the name for the booking. Books the visit and returns a booking "
                        "reference. Call it once per chosen slot; never call it if the lead hesitates or changes their mind.",
         "msg_while_executing_type": "dynamic", "msg_while_executing": [],
         "parameters": [
             {"key_name": "property_id", "type": "string", "description": "The property id from the call data"},
             {"key_name": "slot_id", "type": "number", "description": "slot_id of the slot the lead chose, from check_visit_slots"},
             {"key_name": "visitor_name", "type": "string", "description": "Name of the lead for the booking"},
             {"key_name": "visitors", "type": "number", "description": "How many people will come (default 1)"},
             {"key_name": "notes", "type": "string", "description": "Short notes for the sales manager: configuration, budget, purpose, open questions"}],
         "source_code": book, "update_call_data": False, "execute_while_switching": False},
        {"type": "custom_post_call", "name": "handoff_to_closer",
         "description": "After the call: computes a deterministic lead score, temperature and priority, sets the "
                        "disposition and conversion, writes the closer card to the Bluepoint Sales Desk, links the "
                        "booking to the caller's number, and adds opt-outs to the do-not-call list.",
         "source_code": handoff,
         "conditions": [{"id": "calltype_1763280000000_a1b2c3", "source": "call_type", "key": "all"}]},
    ]


def build():
    cfg = json.loads((AGENT / "config.json").read_text(encoding="utf-8"))
    rebuttals = items(read("prompt/rebuttals.md")) + [call_data_block()]
    script = {
        "systemprompt": "",
        "role": read("prompt/role.md"),
        "goal": read("prompt/goal.md"),
        "callFlow": read("prompt/call_flow.md"),
        "instructions": items(read("prompt/instructions.md")),
        "guardrails": items(read("prompt/guardrails.md")),
        "rebuttals": rebuttals,
        "functions": functions(),
    }
    # sanity: every <placeholder> used in the prose must exist in the call data block
    prose = "\n".join([script["role"], script["goal"], script["callFlow"]] + script["instructions"]
                      + script["guardrails"] + rebuttals[:-1])
    used = set(re.findall(r"<([a-z_]+)>", prose))
    known = {n for n, _ in CALL_VARIABLES}
    unknown = sorted(used - known)
    if unknown:
        sys.exit("Unknown placeholders in prompt: %s" % unknown)
    if "{{" in prose:
        sys.exit("Use <name> in prose; {{name}} belongs only in the call data block")

    full = dict(cfg)
    full["versionName"] = sys.argv[1] if len(sys.argv) > 1 else "v1"
    full.update(script)
    agent_level = {"name", "default_agent_language", "agentStatus", "systempromptType"}
    patch = {k: v for k, v in full.items() if k not in agent_level and k != "versionName"}
    BUILD.mkdir(exist_ok=True)
    (BUILD / "agent.json").write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    (BUILD / "patch.json").write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    size = sum(len(x) for x in [script["role"], script["goal"], script["callFlow"]] + script["instructions"]
               + script["guardrails"] + rebuttals)
    print("built %s: %d prompt chars, %d functions, %d post-call fields, placeholders used: %d"
          % (full["versionName"], size, len(script["functions"]), len(cfg["postcall"]), len(used)))


if __name__ == "__main__":
    build()
