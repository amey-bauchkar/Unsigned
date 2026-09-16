# Unsigned — The Six-Minute Pitch & Judge Defense

Present mode (`/present`) drives every slide live directly from the local models.  
*Rehearse at least three times. Team hand-offs marked with ▶.*

---

## The Pitch Script (Timed to 6:00)

### 0:00 — Title (Slide 1)
"Good morning, judges. We are presenting **Unsigned** — privacy-preserving institutional intelligence for college anti-ragging cells. Our mandate is simple: **the committee sees the danger, never the student.**"

### 0:15 — Which Two? (Slide 2)
"Three real complaints. No names, no roll numbers, no emails. Two of these were written by the exact same student. Take five seconds — which two?"  
*(Allow 5–8 seconds of complete silence. Let the judges scan the screen and guess.)*

### 0:45 — The Attacker Unmasked (Slide 3)
"Our built-in stylometry model — an attacker using punctuation cadence, emoji habits, vernacular slang, and sentence rhythm — links #1 and #3 with **81% confidence**. The next closest pair is 2%.  
Any warden with a laptop, past assignment submissions, and standard python packages can do this.  
**Deleting the name is not anonymity.** That is the problem statement’s twist, and it is the entire reason Unsigned exists."

### 1:30 — Through Unsigned (Slide 4)   ▶ Hand-off
"Now watch the exact same three complaints pass through Unsigned. The student's text is not stored, paraphrased, or de-stylized. It is converted into a **closed-vocabulary fact graph** — acts, banded numbers, and consequences — and regenerated from our own **176-word lexicon**.  
Notice the audit line below each account: **0 of the student's words.**  
Not stripped. Never copied. Same facts, but in the system's words, never theirs."

### 2:15 — The Attacker Defeated (Slide 5)
"Now we run the exact same stylometry attacker on the generated accounts.  
On the raw text, one pair stood out at 81%. On the generated accounts, attribution collapses below random chance. Its highest guess drops from 81% down to a coin toss, and links by *location*, not *author*.  
The linguistic identity has been completely destroyed; the actionable facts remain."

### 2:45 — Live Audience Test (Slide 6)   ▶ Hand-off
"Don't take our word for it. Judges, please scan the QR code on the screen with your phone. Type anything you want — mixed Hinglish, Marathi, slang, emojis, or shorthand. Tap *Show me the card first.*  
*(When the card lands on the projector screen)*  
That card is what the committee reads. Here is what the attacker would have extracted from your raw text — and here is what it gets from the card. Your raw text was unlinked in memory within milliseconds. It no longer exists anywhere on this machine."

### 3:50 — The Killer Proposition: Institutional Intelligence (Slide 7)
"Now look at what this enables. Most tools ask: *'How do we handle one complaint?'*  
Unsigned asks: **'How do we stop systemic abuse without tracking individual students?'**  
Look at the console: our Poisson anomaly detector flags **Hostel B, night hours, coercion** — 12 distinct cards this week against an expected baseline of 1.  
The anti-ragging squad doesn't need to know who complained. They double night patrols at Hostel B, intervene at the root cause, and stop the abuse. **The threat is neutralized, and the student's safety is absolute.**"

### 4:35 — Empirical & Adversarial Validation (Slide 8)   ▶ Hand-off
"We don't ask you to take privacy on faith. We stress-tested our own system:
1. **Three thousand adversarial fuzzed inputs** with planted canary words, script injections, and slang salads — zero canaries reached a stored card or released account.
2. **One incident written in seven divergent styles** — from SMS slang to Marathi to native Devanagari — collapsed into the exact same account, every single time.
3. Our transparent decision rules layer dropped false alerts on mundane mess and Wi-Fi complaints from 35% down to **10%**."

### 5:25 — Close (Slide 9)
"Mandated by UGC regulations in every higher education institution across India. Runs 100% offline on a single laptop. Delivers institutional intelligence without surveillance.  
We are Unsigned. We are ready for your questions."

---

## The Defensible Judge Defense (30 Seconds Each)

### Q1: "Is this a mathematical proof of anonymity? Nothing in computer science is truly provable."
> "We agree completely, and we do not claim absolute mathematical anonymity across all domains. Our claim is scoped and defensible:
> 1. Release privacy is enforced by construction: raw text is never stored in persistent state, and the account channel is bounded to a closed 176-word lexicon with a runtime invariant check.
> 2. For the residual stylometric channel, we empirically test against the strongest authorship model we can build, and demonstrate that attribution collapses to random chance."

### Q2: "Doesn't k-anonymity fail if an incident itself is unique in the college?"
> "Yes, and that is a crucial distinction. We explicitly distinguish **author-identification privacy** (preventing linguistic style from fingerprinting the writer) from **incident uniqueness**.  
> Unsigned completely destroys the author's stylistic fingerprint. If a specific incident took place in a rare room or at an unusual hour, our per-fact generalisation widens that location up the hierarchy until at least $k$ cards share it. But if an act itself is unique, the committee must be able to act on the danger while remaining blind to who reported it."

### Q3: "Why mention 9.17 ms if 'del text' in Python doesn't securely wipe OS RAM?"
> "You are 100% right: Python's `del` unlinks references, it is not DoD-grade RAM wiping. We do not base our security claim on OS memory wiping. Our guarantee is architectural: raw text never enters SQLite tables, logs, web responses, or released cards. Even if lingering bytes exist in unallocated heap memory before garbage collection, they have zero path to leave the machine."

### Q4: "Your evaluation uses a 44-text seed dataset. How do you know this generalises?"
> "The initial dev seed calibrates our baseline classifier. But our core privacy proofs do not depend on the seed:
> 1. The 3,000 canary fuzzer proves release channel isolation for any arbitrary string.
> 2. The 7-style invariance test proves dialect collapse regardless of writing habits.  
> Furthermore, we built `scripts/import_corpus.py` so that an institution can import Google Form exports and retrain the classifier under grouped cross-validation in under 30 seconds."

### Q5: "Why use rules and regex instead of a pure end-to-end Deep Learning model?"
> "Because the extraction layer sits directly inside the privacy boundary. A deep neural generator is an un-auditable black box that can hallucinate details or smuggle stylistic tokens into the output. A closed-vocabulary fact graph is human-auditable and verifiable by a judge. We deploy ML where it belongs: in distress classification, Poisson anomaly detection, and the adversarial stylometry attacker that audits the release channel."

### Q6: "At 2 AM, is a terrified student expected to act like an NLP data annotator?"
> "No, absolutely not. The preview is not an annotation tool; it is a reassuring safety shield. The student writes freely in whatever language comes out. They see a simple, human card: *'Here is what the committee will read. Tap ✕ to remove any fact. Send when ready.'* One tap to verify, and their words are shredded before their eyes."

### Q7: "The regenerated accounts read mechanically."
> "By design. Same facts, same words, every single time. Syntactic and lexical variation is the exact vector through which stylometric fingerprints leak back in. Monotony is the mathematical proof of privacy."
