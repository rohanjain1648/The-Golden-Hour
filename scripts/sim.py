"""Manage the simulation suite on CallKaro.

  python scripts/sim.py sync                      create/update every test in tests/suite.py
  python scripts/sim.py run <versionId> [KEY,...|all] [--epoch N] [--name NAME]
  python scripts/sim.py results <runId>           save raw results + print a triage table
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from ckrun import ck  # noqa: E402
from callctx import load_json, property_path, raw_metadata, run_precall, ROOT  # noqa: E402
import suite  # noqa: E402

AGENT_ID = "6afae6648efa21df5367c3e0"
IDS_FILE = ROOT / "tests" / "sim_ids.json"
RESULTS = ROOT / "tests" / "results"


def variables_for(test):
    lead = load_json(ROOT / "data" / "leads" / ("%s.json" % test["lead"]))
    prop = load_json(property_path(lead["property_id"]))
    md = raw_metadata(lead, prop)
    md.update(test.get("overrides", {}))
    md = run_precall(md)
    return {k: str(v) for k, v in md.items()}


def sync():
    ids = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}
    tmp = Path(tempfile.mkdtemp())
    for t in suite.TESTS:
        vfile = tmp / ("%s_vars.json" % t["key"])
        ffile = tmp / ("%s_fns.json" % t["key"])
        vfile.write_text(json.dumps(variables_for(t), ensure_ascii=False), encoding="utf-8")
        ffile.write_text(json.dumps(t["functions"], ensure_ascii=False), encoding="utf-8")
        args = ["--name", t["name"], "--persona", t["persona"], "--prompt", t["prompt"], "--criteria", t["criteria"],
                "--variables", "@%s" % vfile, "--functions", "@%s" % ffile]
        if t["key"] in ids:
            ck("sim", "update", ids[t["key"]], *args)
            print("updated", t["key"], ids[t["key"]])
        else:
            out = ck("sim", "create", AGENT_ID, *args)
            tid = next((w for w in out.replace(":", " ").split() if len(w) == 24 and all(c in "0123456789abcdef" for c in w)), None)
            if not tid:
                raise RuntimeError("could not parse test id from: %s" % out)
            ids[t["key"]] = tid
            IDS_FILE.write_text(json.dumps(ids, indent=2))
            print("created", t["key"], tid)
    IDS_FILE.write_text(json.dumps(ids, indent=2))


def run(version, keys="all", epoch=1, name=None):
    ids = json.loads(IDS_FILE.read_text())
    sel = list(ids) if keys == "all" else keys.split(",")
    test_ids = ",".join(ids[k] for k in sel)
    name = name or "golden-hour %s %s" % (version[-6:], "+".join(sel) if len(sel) < 3 else "%d tests" % len(sel))
    print(ck("sim", "run", AGENT_ID, "--tests", test_ids, "--versions", version, "--epoch", str(epoch), "--name", name))


def results(run_id):
    data = ck("sim", "results", run_id, "--json", json_out=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / ("%s.json" % run_id)).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    items = data if isinstance(data, list) else data.get("results") or data.get("data") or []
    print("results:", len(items), "| saved tests/results/%s.json" % run_id)
    for r in items:
        name = (r.get("testcaseName") or (r.get("testCase") or {}).get("testcaseName") or r.get("testId") or "?")
        print("%-5s %-7s turns=%-3s ended=%-12s %s" % (
            "PASS" if r.get("isTestSucceed") else "FAIL", r.get("analysisStatus", "?"), r.get("total_turns", "?"),
            r.get("ended_by", "?"), str(name)[:90]))
        summ = (r.get("testResultSummary") or "").replace("\n", " ")
        print("      ", summ[:400])
        pc = r.get("post_call") or {}
        if isinstance(pc, dict) and pc:
            keep = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in pc.items()
                    if k in ("outcome", "site_visit_booking_ref", "callback_time", "budget_fit", "opted_out", "language_used")}
            print("       post_call:", json.dumps(keep, ensure_ascii=False))


def report(run_id, label=""):
    """Write tests/results/<run>.md: verdict table + full transcripts with function calls and post-call."""
    data = json.loads((RESULTS / ("%s.json" % run_id)).read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("results") or data.get("data") or []
    ids = json.loads(IDS_FILE.read_text())
    by_id = {v: k for k, v in ids.items()}
    names = {t["key"]: t["name"] for t in suite.TESTS}
    rows, body = [], []
    total = 0.0

    def tid(r):
        t = r.get("testcaseId")
        return t.get("_id") if isinstance(t, dict) else t

    def vid(r):
        v = r.get("versionId")
        return (v.get("versionName") or v.get("_id")) if isinstance(v, dict) else str(v)[-6:]

    for r in sorted(items, key=lambda r: (vid(r), by_id.get(tid(r), ""))):
        key = "%s @ %s" % (by_id.get(tid(r), tid(r)), vid(r))
        verdict = "PASS" if r.get("isTestSucceed") else ("INVALID" if r.get("analysisStatus") == "failed" else "FAIL")
        total += float(r.get("total_cost") or 0)
        rows.append("| %s | %s | %s | %s |" % (key, verdict, r.get("total_turns"), (r.get("post_call") or {}).get("outcome", {}).get("value", "") if isinstance((r.get("post_call") or {}).get("outcome"), dict) else ""))
        body.append("\n## %s — %s\n\n%s\n\nGrader: %s\n" % (key, verdict, names.get(key, ""), (r.get("testResultSummary") or "").strip()))
        for t in r.get("transcript", []):
            line = "- **%s**: %s" % (t.get("role"), (t.get("content") or "").replace("\n", " "))
            for fc in t.get("function_calls") or []:
                line += "\n  - `%s(%s)` -> `%s`" % (fc.get("name"), json.dumps(fc.get("arguments"), ensure_ascii=False),
                                                    json.dumps(fc.get("result"), ensure_ascii=False)[:300])
            body.append(line)
        pc = r.get("post_call") or {}
        body.append("\nPost-call: " + json.dumps({k: (v.get("value") if isinstance(v, dict) else v) for k, v in pc.items()}, ensure_ascii=False))
    passed = sum(1 for x in rows if "| PASS |" in x)
    head = ["# Simulation run %s %s" % (run_id, label), "",
            "Passed %d/%d · cost %.1f credits" % (passed, len(rows), total), "",
            "| Test | Verdict | Turns | Outcome |", "|---|---|---|---|"] + rows
    out = RESULTS / ("%s.md" % run_id)
    out.write_text("\n".join(head + body), encoding="utf-8")
    print("\n".join(head))
    print("wrote", out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sync":
        sync()
    elif cmd == "run":
        a = sys.argv[2:]
        ep = int(a[a.index("--epoch") + 1]) if "--epoch" in a else 1
        nm = a[a.index("--name") + 1] if "--name" in a else None
        run(a[0], a[1] if len(a) > 1 and not a[1].startswith("--") else "all", ep, nm)
    elif cmd == "results":
        results(sys.argv[2])
        report(sys.argv[2], " ".join(sys.argv[3:]))
