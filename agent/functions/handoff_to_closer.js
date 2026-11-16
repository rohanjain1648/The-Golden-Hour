async function handoff_to_closer(context) {
  const pc = context.post_call || {};
  const md = context.call_metadata || {};
  const get = (k) => (pc[k] !== undefined && pc[k] !== null ? String(pc[k]).trim() : "");
  const outcome = get("outcome") || "no_conversation";
  // Normalise the extracted booking reference ("BV8CB7", "bv 8cb7" -> "BV-8CB7") so it matches the Sales Desk record.
  let bookingRef = get("site_visit_booking_ref").toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (/^BV[A-Z0-9]{4}$/.test(bookingRef)) bookingRef = "BV-" + bookingRef.slice(2);
  if (bookingRef) pc.site_visit_booking_ref = bookingRef;
  const optedOut = pc.opted_out === true || String(pc.opted_out).toLowerCase() === "true" || outcome === "opted_out";

  // Deterministic lead score (0-100): the same answers always give the same score.
  const outcomePts = { site_visit_booked: 40, human_callback_requested: 30, callback_scheduled: 20, nurture_follow_up: 10 };
  const fitPts = { fits: 20, stretch: 12, unknown: 5, below_range: 0 };
  const timelinePts = { "0_3_months": 20, "3_6_months": 14, "6_12_months": 7, over_12_months: 2, unknown: 3 };
  const purposePts = { self_use: 10, both: 10, investment: 8, unknown: 3 };
  const loanPts = { not_needed: 10, needed: 7, undecided: 4, unknown: 3 };
  let score = (outcomePts[outcome] || 0) + (fitPts[get("budget_fit")] ?? 3) + (timelinePts[get("purchase_timeline")] ?? 3)
            + (purposePts[get("buyer_purpose")] ?? 3) + (loanPts[get("home_loan")] ?? 3);
  if (["not_interested", "wrong_person", "no_conversation"].includes(outcome) || optedOut) score = 0;
  score = Math.max(0, Math.min(100, score));

  let temperature = score >= 70 ? "hot" : score >= 45 ? "warm" : "cold";
  if (optedOut) temperature = "do_not_call";
  else if (outcome === "wrong_person") temperature = "disqualified";
  let priority = optedOut ? "none" : (temperature === "hot" || outcome === "site_visit_booked") ? "P1" : temperature === "warm" ? "P2" : "P3";

  const dispositions = {
    site_visit_booked: "Site visit booked",
    human_callback_requested: "Wants a call from the sales manager",
    callback_scheduled: "Busy, asked for a callback",
    nurture_follow_up: "Interested later, nurture",
    not_interested: "Not interested",
    opted_out: "Opted out, do not call",
    wrong_person: "Wrong person",
    no_conversation: "No conversation"
  };

  pc.lead_score = score;
  pc.lead_temperature = temperature;
  pc.lead_priority = priority;
  context.disposition_reason = dispositions[outcome] || outcome;
  context.conversion_status = outcome === "site_visit_booked" && bookingRef !== "";

  const payload = {
    call_sid: context.callSid ?? null,
    property_id: md.property_id ?? null,
    lead_name: md.lead_name ?? null,
    lead_phone: context.user_phone_number ?? null,
    outcome,
    opted_out: optedOut,
    lead_temperature: temperature,
    lead_score: score,
    priority,
    booking_ref: bookingRef,
    site_visit_slot: get("site_visit_slot"),
    callback_time: get("callback_time"),
    budget_confirmed: get("budget_confirmed"),
    budget_fit: get("budget_fit"),
    config_interest: get("config_interest"),
    buyer_purpose: get("buyer_purpose"),
    purchase_timeline: get("purchase_timeline"),
    home_loan: get("home_loan"),
    objections: get("objections_raised"),
    unanswered_questions: get("unanswered_questions"),
    competitors_mentioned: get("competitors_mentioned"),
    language_used: get("language_used"),
    closer_summary: get("closer_summary"),
    next_best_action: get("next_best_action"),
    call_duration: context.call_duration ?? null,
    recording_url: context.recordingUrl ?? null
  };

  const functionLog = {
    name: "handoff_to_closer",
    parameters: { call_sid: payload.call_sid, outcome, lead_score: score, priority },
    success: false,
    response: null,
    timestamp: new Date().toISOString()
  };
  try {
    const res = await axios({
      method: "POST",
      url: "https://xtvqhihnoxuyfwpylrtj.supabase.co/rest/v1/rpc/record_handoff",
      headers: { apikey: x_secrets["BLUEPOINT_DESK_KEY"], "Content-Type": "application/json" },
      data: { p: payload },
      timeout: 10000
    });
    functionLog.success = res.status >= 200 && res.status < 300;
    functionLog.response = res.data;
  } catch (error) {
    functionLog.response = error.message;
  } finally {
    context.functions_called.push(functionLog);
  }
}
