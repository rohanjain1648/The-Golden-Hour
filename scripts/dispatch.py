"""Golden Hour dispatcher: turn an enquiry into a test call within minutes.

  python scripts/dispatch.py data/leads/rohan-pune.json --to 91XXXXXXXXXX [--property BP-BLR-PALM]
                             [--version <versionId>] [--real] [--dry-run]

1. Loads the lead and the property it enquired about (or --property to point the SAME agent at another listing).
2. Validates the property has every fact the agent may be asked about (refuses to dial with gaps).
3. Checks the Bluepoint Sales Desk do-not-call list (filled automatically by the agent on opt-outs).
4. Places the call with every raw field as --var. Always --test unless --real is passed explicitly.
The agent's pre-call function derives speakable prices, budget fit, recency and offer/scarcity flags.
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ckrun import ck  # noqa: E402
from callctx import load_json, property_path, raw_metadata, run_precall  # noqa: E402

AGENT_ID = "6afae6648efa21df5367c3e0"
DESK = "https://xtvqhihnoxuyfwpylrtj.supabase.co/rest/v1/rpc/is_dnd"

def _load_env():
    """Read KEY=VALUE lines from a local, git-ignored .env file into os.environ (if present)."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()
DESK_PUBLISHABLE_KEY = os.environ.get("BLUEPOINT_DESK_KEY", "")  # Supabase publishable key; never commit it
REQUIRED = ["property_id", "property_name", "property_type", "city", "locality", "units_json", "price_basis",
            "construction_status", "possession", "rera_id", "amenities", "location_highlights", "payment_plan",
            "loan_partners", "site_address", "sales_manager_name"]


def is_dnd(phone):
    if not DESK_PUBLISHABLE_KEY:
        sys.exit("Set BLUEPOINT_DESK_KEY (in .env or the environment) so the do-not-call list can be checked before dialing.")
    req = urllib.request.Request(DESK, data=json.dumps({"p_phone": phone}).encode(),
                                 headers={"apikey": DESK_PUBLISHABLE_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()) is True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lead")
    ap.add_argument("--to", required=True, help="number with country code, e.g. 9198XXXXXXXX")
    ap.add_argument("--property")
    ap.add_argument("--version")
    ap.add_argument("--real", action="store_true", help="place a REAL (non-test) call")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    lead = load_json(a.lead)
    pid = a.property or lead["property_id"]
    prop = load_json(property_path(pid))
    missing = [k for k in REQUIRED if not prop.get(k)]
    if missing:
        sys.exit("Refusing to dial: property %s is missing %s" % (pid, missing))
    phone = a.to.lstrip("+").replace(" ", "")
    if is_dnd(phone):
        sys.exit("Refusing to dial: %s is on the do-not-call list" % phone)

    md = raw_metadata(lead, prop)
    preview = run_precall(md)
    print("Pre-call preview:\n  units: %s\n  fit:   %s\n  offer: %s | scarcity: %s"
          % (preview["units_spoken"], preview["budget_fit_note"], preview["offer_line"], preview["scarcity_line"]))
    args = ["calls", "make", "--agent", AGENT_ID, "--to", phone]
    if not a.real:
        args.append("--test")
    if a.version:
        args += ["--versions", a.version]
    for k, v in md.items():
        args += ["--var", "%s=%s" % (k, v)]
    if a.dry_run:
        print("DRY RUN: ck " + " ".join(x if " " not in x else '"%s"' % x for x in args))
        return
    print(ck(*args))


if __name__ == "__main__":
    main()
