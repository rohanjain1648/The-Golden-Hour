# Role-play scripts for the two submission recordings

You answer as the lead. Speak naturally; you don't need to read word for word. Each script exercises a different property, language and kind of pushback on the **same agent version**, which is the swappability proof the judges look for. Pause about a second after the agent finishes before you reply.

---

## Recording 1: Pune, Hinglish, real pushback → site visit booked
`python scripts/dispatch.py data/leads/rohan-pune.json --to 91XXXXXXXXXX`

You are **Rohan**. You enquired on 99acres about Bluepoint Skyline Residences (Kharadi) a few minutes ago. Budget 1 crore, 2 BHK, for your family (wife and a 4-year-old daughter); you work at EON IT Park.

1. Agent greets you → "Haan, bolo. 2 minute hai."
2. Answer its questions: family, 2 BHK, budget "ek crore, thoda stretch kar sakta hoon".
3. When it gives the price → **"Kharadi mein hi ek aur project 85 lakh mein de raha hai. Aap itne mehenge kyun ho?"**
4. After its answer → **"Aur under construction hai… delay ho gaya toh? Mere cousin ka flat 3 saal late mila tha."**
5. → **"Koi discount chal raha hai? Kitne flats bache hain?"** (this is the no-manufactured-urgency moment: there is no offer data)
6. If it offers a visit → "Theek hai, Saturday dekh lete hain." Pick the first time it offers; "Hum do log aayenge."
7. After it gives the booking reference → "Perfect, thank you." Let it close.

What the judges should hear: an honest budget fit ("lower end"), a like-for-like answer to the competitor (carpet area, all-inclusive), the RERA date plus actual floor progress, "no offer information" instead of invented urgency, a real slot check, and a booking reference read out.

## Recording 2: Bengaluru villas, English, a stall and a challenge → different outcome
`python scripts/dispatch.py data/leads/priya-bengaluru.json --to 91XXXXXXXXXX`

You are **Priya**. You filled a WhatsApp form for Bluepoint Palm Grove Villas (Sarjapur Road). Budget about 2.5 crore, family home, need to move before June.

1. Agent greets you → "Yes, but quickly please."
2. → **"Wait, am I talking to a real person or a bot?"**
3. Answer its questions: family, 3 BHK villa, 2.5 crore.
4. → **"Are they actually ready to move in? Any offer right now? And how many are left?"** (now the agent *should* use the real offer and the 6-of-48 fact, neutrally)
5. → **"Honestly, just WhatsApp me the brochure, I'll look at it."** (it cannot send messages, so it must not claim to)
6. If it offers a visit → "Not this week. Can the sales manager call me Thursday evening?"
7. Let it confirm Thursday and close.

What the judges should hear: an honest AI disclosure, the same agent now speaking English about villas, a real offer and inventory stated without pressure, an honest handling of the brochure request, and a clean callback outcome. That shows a different conversion path from recording 1.

**As recorded (16 Nov 2026):** the lead went off-script after the brochure stall and asked for weekend slots. The agent followed her: it checked real slots and booked `BV-AAB4` (Saturday 3 PM, 2 visitors) in English on the villa data. The bot question and the offer/inventory question were not asked on this call, so those behaviours are covered by the simulations (P0_INJECTION_BOT, P3_HAPPY_BLR_SWAP), not by the recording.

---

After each call, the outcome is visible without listening:
- `ck calls list --agent 6afae6648efa21df5367c3e0 --limit 2` → disposition and conversion
- `ck calls get <callId> --json` → the 20 post-call fields, lead score and priority, and `recording.recordingUrl`
- Supabase `closer_queue` → the closer card; `site_visits` → the booking linked to the phone number
