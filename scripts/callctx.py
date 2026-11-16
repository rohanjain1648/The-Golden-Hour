"""Build call metadata from a lead + property file, and run the agent's real pre-call code locally.

The same agent/functions/prepare_call_context.py that runs on CallKaro is executed here with the
same pre-imported names (json, datetime, pytz-compatible tz, logger), so the derived values used
in simulations are exactly what a live call would get.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RAW_PROPERTY_KEYS = ["property_id", "property_name", "property_type", "city", "locality", "units_json", "price_basis",
                     "construction_status", "possession", "rera_id", "amenities", "location_highlights",
                     "payment_plan", "loan_partners", "current_offer", "offer_valid_till", "inventory_fact",
                     "site_address", "sales_manager_name"]
RAW_LEAD_KEYS = ["lead_name", "enquiry_source", "enquiry_at", "lead_budget_inr", "lead_config_pref",
                 "lead_language", "lead_note"]


class _Ist(tzinfo):
    """Fixed +05:30 zone with pytz's localize(); India has no DST."""
    def utcoffset(self, dt):
        return timedelta(hours=5, minutes=30)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "IST"

    def localize(self, dt):
        return dt.replace(tzinfo=self)


class _PytzShim:
    """Minimal stand-in for pytz.timezone('Asia/Kolkata')."""
    def timezone(self, name):
        assert name == "Asia/Kolkata"
        return _Ist()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def property_path(pid):
    return ROOT / "data" / "properties" / ("%s.json" % pid)


def raw_metadata(lead, prop):
    """The exact key/value strings the dialer sends as --var (all strings, units_json as JSON text)."""
    md = {}
    for k in RAW_LEAD_KEYS:
        v = lead.get(k, "")
        if k == "enquiry_at" and v in ("", "auto"):
            v = (datetime.now(timezone(timedelta(hours=5, minutes=30))) - timedelta(minutes=4)).isoformat(timespec="minutes")
        md[k] = "" if v is None else str(v)
    for k in RAW_PROPERTY_KEYS:
        v = prop.get(k, "")
        md[k] = json.dumps(v, ensure_ascii=False, separators=(",", ":")) if k == "units_json" else ("" if v is None else str(v))
    return md


def run_precall(metadata):
    src = (ROOT / "agent" / "functions" / "prepare_call_context.py").read_text(encoding="utf-8")
    env = {"json": json, "datetime": datetime, "timedelta": timedelta, "pytz": _PytzShim(),
           "logger": logging.getLogger("precall")}
    exec(src, env)
    call_data = {"metadata": dict(metadata)}
    asyncio.run(env["prepare_call_context"](call_data))
    return call_data["metadata"]


def full_context(lead_file, property_id=None):
    lead = load_json(lead_file)
    prop = load_json(property_path(property_id or lead["property_id"]))
    return run_precall(raw_metadata(lead, prop))


if __name__ == "__main__":
    import sys
    ctx = full_context(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    for k in ["units_spoken", "lead_budget_spoken", "budget_fit", "budget_fit_note", "enquiry_recency", "time_greeting",
              "offer_line", "scarcity_line", "opening_language", "missing_facts"]:
        print("%-20s %s" % (k, ctx.get(k)))
