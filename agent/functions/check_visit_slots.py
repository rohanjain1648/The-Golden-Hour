async def check_visit_slots(ctx: RunContext, property_id: str, preferred_day: str) -> dict:
    """Fetch open site-visit slots for this property from the Bluepoint Sales Desk.

    Args:
        ctx: run context
        property_id: str — the property id from the call data, e.g. BP-PUN-SKY
        preferred_day: str — "today", "tomorrow", a weekday name ("saturday"), "weekend",
            "weekday", or "" for the earliest slots

    Returns:
        dict: {status: "success", slots: [{slot_id, label}], note} or
              {status: "error", message}
    """
    pid = (property_id or "").strip().upper()
    if not pid:
        return {"status": "error", "message": "property_id is required"}
    day = (preferred_day or "").strip().lower()
    allowed = {"", "any", "today", "tomorrow", "weekend", "weekday", "monday", "tuesday", "wednesday",
               "thursday", "friday", "saturday", "sunday"}
    if day not in allowed:
        day = ""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://xtvqhihnoxuyfwpylrtj.supabase.co/rest/v1/rpc/get_visit_slots",
                headers={"apikey": x_secrets["BLUEPOINT_DESK_KEY"], "Content-Type": "application/json"},
                json={"p_property_id": pid, "p_preferred_day": day, "p_limit": 3},
            )
    except httpx.RequestError as e:
        return {"status": "error", "message": "Scheduling system unreachable: %s" % e}
    if resp.status_code >= 300:
        return {"status": "error", "message": "Scheduling system error %s" % resp.status_code}
    try:
        data = resp.json()
    except Exception:
        return {"status": "error", "message": "Scheduling system returned an unreadable response"}
    if data.get("status") != "success":
        return {"status": "error", "message": data.get("message", "unknown error")}
    return {"status": "success", "slots": data.get("slots", []), "note": data.get("note", "")}
