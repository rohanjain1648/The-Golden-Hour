async def book_site_visit(ctx: RunContext, property_id: str, slot_id: int, visitor_name: str, visitors: int, notes: str) -> dict:
    """Book one site-visit slot in the Bluepoint Sales Desk and return a booking reference.

    Args:
        ctx: run context
        property_id: str — the property id from the call data
        slot_id: int — a slot_id returned by check_visit_slots in THIS call and chosen by the lead
        visitor_name: str — the lead's name as they want it on the booking
        visitors: int — number of people coming (1-10)
        notes: str — short notes for the sales manager (preferences, questions), or ""

    Returns:
        dict: {status: "success", booking_ref, slot_label, visitors} or
              {status: "slot_full" | "error", message}
    """
    pid = (property_id or "").strip().upper()
    name = (visitor_name or "").strip()
    if not pid or not slot_id or int(slot_id) <= 0:
        return {"status": "error", "message": "property_id and a slot_id from check_visit_slots are required"}
    if not name or name.upper() == "NOT AVAILABLE":
        return {"status": "error", "message": "Ask the lead for the name to put on the booking first"}
    try:
        count = int(visitors) if visitors else 1
    except Exception:
        count = 1
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://xtvqhihnoxuyfwpylrtj.supabase.co/rest/v1/rpc/book_site_visit",
                headers={"apikey": x_secrets["BLUEPOINT_DESK_KEY"], "Content-Type": "application/json"},
                json={"p_property_id": pid, "p_slot_id": int(slot_id), "p_lead_name": name,
                      "p_visitors": max(1, min(count, 10)), "p_notes": (notes or "")[:500]},
            )
    except httpx.RequestError as e:
        return {"status": "error", "message": "Booking system unreachable: %s" % e}
    if resp.status_code >= 300:
        return {"status": "error", "message": "Booking system error %s" % resp.status_code}
    try:
        data = resp.json()
    except Exception:
        return {"status": "error", "message": "Booking system returned an unreadable response"}
    if data.get("status") == "success":
        ref = str(data.get("booking_ref") or "")
        # Spell it out for TTS so the reference is never garbled ("BV-7Q2K" -> "B V 7 Q 2 K").
        spoken = " ".join(ch for ch in ref.upper() if ch.isalnum())
        return {"status": "success", "booking_ref": ref, "booking_ref_spoken": spoken,
                "slot_label": data.get("slot_label"), "visitors": data.get("visitors")}
    return {"status": data.get("status", "error"), "message": data.get("message", "booking failed")}
