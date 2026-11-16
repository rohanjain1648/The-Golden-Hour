async def prepare_call_context(call_data: dict):
    """Pre-call: turn raw lead + property data into speakable, pre-computed facts.

    Reads call metadata supplied at call time (lead_* and property fields, units_json as a
    JSON string or list) and ADDS derived keys used by the prompt:
      units_spoken, lead_budget_spoken, budget_fit, budget_fit_note, enquiry_recency,
      time_greeting, offer_line, scarcity_line, opening_language, missing_facts.
    The LLM never does arithmetic: every comparison and amount is computed here.
    Never raises: on any error the prompt falls back to its missing-data rules.
    """
    metadata = call_data.setdefault("metadata", {})

    def s(key):
        v = metadata.get(key)
        return "" if v is None else str(v).strip()

    def inr(amount):
        a = float(amount)
        if a >= 10000000:
            v = round(a / 10000000, 2)
            return "₹" + ("%g" % v) + " crore"
        v = round(a / 100000, 1)
        return "₹" + ("%g" % v) + " lakh"

    def gap(amount):
        return inr(amount).replace("₹", "about ₹", 1)

    try:
        # ---------- units ----------
        raw_units = metadata.get("units_json")
        units = []
        if isinstance(raw_units, list):
            units = raw_units
        elif raw_units:
            try:
                units = json.loads(str(raw_units))
            except Exception:
                units = []
        clean = []
        for u in units:
            try:
                clean.append({
                    "config": str(u["config"]).strip(),
                    "area": int(float(u.get("carpet_sqft") or 0)),
                    "area_type": str(u.get("area_type") or "carpet").strip(),
                    "lo": float(u["price_min_inr"]),
                    "hi": float(u["price_max_inr"]),
                })
            except Exception:
                continue
        clean.sort(key=lambda x: x["lo"])
        if clean:
            parts = []
            for u in clean:
                area = ("%s sq ft %s" % (format(u["area"], ","), u["area_type"])) if u["area"] else ""
                price = inr(u["lo"]) if u["lo"] == u["hi"] else "%s to %s" % (inr(u["lo"]), inr(u["hi"]))
                parts.append("%s%s: %s" % (u["config"], (" (" + area + ")") if area else "", price))
            metadata["units_spoken"] = "; ".join(parts)
        else:
            metadata["units_spoken"] = "NOT AVAILABLE"

        # ---------- budget fit ----------
        budget = None
        b_raw = s("lead_budget_inr").replace(",", "")
        if b_raw:
            try:
                budget = float(b_raw)
                if budget <= 0:
                    budget = None
            except Exception:
                budget = None
        metadata["lead_budget_spoken"] = inr(budget) if budget else "not stated"

        if budget is None or not clean:
            metadata["budget_fit"] = "unknown"
            metadata["budget_fit_note"] = ("The lead's budget is not known. Ask for it; do not judge fit yourself."
                                           if clean else "Unit prices are not available. Do not discuss prices.")
        else:
            notes = []
            any_fit = False
            any_stretch = False
            for u in clean:
                if u["hi"] <= budget:
                    any_fit = True
                    notes.append("%s fits fully within the budget" % u["config"])
                elif u["lo"] <= budget:
                    any_fit = True
                    notes.append("%s fits at the lower end of its range (starts at %s; the top of the range is %s above budget)"
                                 % (u["config"], inr(u["lo"]), gap(u["hi"] - budget)))
                elif u["lo"] <= budget * 1.10:
                    any_stretch = True
                    notes.append("%s starts %s above budget, a stretch of under 10 percent" % (u["config"], gap(u["lo"] - budget)))
                else:
                    notes.append("%s starts %s above budget" % (u["config"], gap(u["lo"] - budget)))
            metadata["budget_fit"] = "fits" if any_fit else ("stretch" if any_stretch else "below_range")
            if not any_fit and not any_stretch:
                notes.append("no configuration here fits this budget; be honest and do not push")
            metadata["budget_fit_note"] = "Budget %s. " % inr(budget) + "; ".join(notes) + "."

        # ---------- time ----------
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)
        h = now.hour
        metadata["time_greeting"] = "good morning" if h < 12 else ("good afternoon" if h < 17 else "good evening")
        enq = s("enquiry_at")
        recency = "recently"
        if enq and enq.lower() != "auto":
            try:
                t = datetime.fromisoformat(enq.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = tz.localize(t)
                mins = int((now - t).total_seconds() // 60)
                if mins < 2:
                    recency = "just a minute ago"
                elif mins < 60:
                    recency = "about %d minutes ago" % mins
                elif mins < 180:
                    recency = "a little while ago today"
                else:
                    recency = "earlier"
            except Exception:
                recency = "recently"
        elif enq.lower() == "auto":
            recency = "a few minutes ago"
        metadata["enquiry_recency"] = recency

        # ---------- offer & scarcity: only real facts, else an explicit NONE ----------
        offer = s("current_offer")
        valid = s("offer_valid_till")
        if offer and valid:
            try:
                if datetime.strptime(valid, "%Y-%m-%d").date() < now.date():
                    offer = ""
            except Exception:
                pass
        metadata["offer_line"] = offer if offer else "NONE"
        inv = s("inventory_fact")
        metadata["scarcity_line"] = inv if inv else "NONE"

        # ---------- language ----------
        lang = s("lead_language").lower()
        metadata["opening_language"] = {"english": "English", "hindi": "Hindi", "hinglish": "Hinglish"}.get(lang, "Hinglish")

        # ---------- missing facts the agent must not improvise ----------
        required = ["property_name", "city", "locality", "possession", "rera_id", "price_basis",
                    "amenities", "location_highlights", "payment_plan", "loan_partners", "site_address"]
        missing = [k for k in required if not s(k)]
        for k in missing:
            metadata[k] = "NOT AVAILABLE"
        metadata["missing_facts"] = ", ".join(missing) if missing else "none"
        for k in ["lead_name", "enquiry_source", "lead_config_pref", "lead_note", "sales_manager_name",
                  "construction_status", "property_type"]:
            if not s(k):
                metadata[k] = "NOT AVAILABLE"
    except Exception as error:
        logger.warning("prepare_call_context failed: %s", error)

    call_data["metadata"] = metadata
