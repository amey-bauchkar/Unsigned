# Unsigned — Complete Solution Blueprint (source of truth)

*MUSA CodeX 2026 · CX0105 "Read Between the Lines" (Artificial Intelligence & Machine Learning) · Locked 14 September 2026 · Software only · Every claim tagged KNOWN, ASSUMPTION, or VERIFY.*

---

## 0. The thesis

Removing the name from a complaint is not anonymity. Punctuation habits, spelling variants, emoji, sentence rhythm — a student's *style* — link anonymous complaints to each other and, with one known writing sample, to a person. Every existing "anonymous complaint box" leaks this way. **Unsigned never shows the committee what the student wrote.** The student's text is consumed on a college laptop by a pipeline that classifies distress and urgency, decomposes the story into a **fact graph** of closed values, generalises every identifying fact until it is not unique, **regenerates a full account from Unsigned's own lexicon** — so the committee reads what happened in our words, never theirs — discards the raw text within milliseconds, and continuously **attacks its own output** with the strongest stylometry model it can build. The committee sees the danger, the facts and the pattern — never the student.

## 1. The problem statement, decomposed

Exact text (KNOWN): *"A college anti-ragging cell wants to spot distress signals hidden in anonymous student complaint text — sarcasm, coded slang, mixed languages — but must never be able to identify the student who wrote it, even indirectly through writing style. Build an NLP early-warning classifier that works under this strict anonymity constraint, where re-identification itself must be provably impossible. Twist: Word choice and punctuation habits alone can fingerprint a student across multiple anonymous complaints — the system must actively strip or randomize stylistic cues it doesn't need for classification, not just remove the name field."*

| # | Requirement | Unsigned's answer |
|---|---|---|
| R1 | Spot **distress** in sarcasm, slang, mixed languages | Code-mixed (Hinglish / Marathi-English) classifier with distress, urgency, type and sarcasm heads; honest F1 on the sarcastic subset |
| R2 | **Never identify** the student, even indirectly | Raw text never stored or displayed; committee sees cards only |
| R3 | **Provably** impossible | Four-part claim: architectural invariant · information-theoretic bound on the card channel · side channels closed · strongest attacker at chance on the residual channel (Section 4) |
| R4 | Twist: **style fingerprints across complaints** | Style is not stripped — it is *never released*: the account the committee reads is regenerated from a closed lexicon over the fact graph; a runtime invariant refuses to emit any token outside that lexicon (Section 4A) |
| R5 | Strip only what classification doesn't need | Classification runs on the raw text in memory; only the classification's outputs and extracted facts leave the sanitiser |

Second-order problems the PS only implies, which we solve explicitly:

- **Content self-identification.** "The only girl in the robotics club" identifies without any style. → A **pre-submission privacy preview**: the student sees the exact card the committee will see, with rare field combinations flagged, *before* sending.
- **Metadata side channels.** Submission time, IP, device, request size all fingerprint. → No accounts, no IP logs, no cookies, time bucketed, randomised release delay by urgency, padded requests.
- **The cell can't act on a card alone.** → Cards feed a **pattern detector** (location × time × type, rising-trend alerts) so the cell acts on the *pattern* — the hostel, the hour, the behaviour — not the person.
- **The student is left alone after reporting.** → An **anonymous two-way channel**: a random passphrase token lets the student read the cell's reply and add information, with no identity.

## 2. What other teams will build, and how we differ

| Tier | What they build | Why it loses |
|---|---|---|
| 70% | Sentiment/toxicity classifier + anonymous form; "we don't store the name" | Style leak untouched; committee reads raw text; the twist is ignored |
| Good | Same + paraphrase with an LLM to "remove style" | Unmeasured; LLM wrapper; paraphrase still leaks; raw text often still stored |
| Very good | Stylometric feature stripping (punctuation normalisation, spelling canonicalisation) + classifier | Closer — but "stripping" is a losing race against an attacker; no measurement, no bound, no side-channel handling |
| **Unsigned** | Never release the text; release a generalised card; template narrative by construction; attacker-in-the-loop audit with a live linkability meter; bound on the card channel; side channels closed; pre-submission privacy preview; pattern-level alerts; anonymous reply channel | Every claim is either provable by construction or measured against the strongest attacker we could build |

KNOWN context for the pitch: UGC's *Regulations on Curbing the Menace of Ragging in Higher Educational Institutions* (2009) require institutions to maintain anti-ragging committees and squads — every judge's college has one. VERIFY the exact regulation title and year before it goes on a slide.

## 3. Product definition

**Name:** Unsigned. **One line:** the committee sees the danger, never the student.

**Users:** (1) the student reporting — on their phone, from anywhere on the college network; (2) the anti-ragging cell / squad — the console on one college laptop; (3) the warden / mentor who receives an urgent alert; (4) the institution — audit and compliance reports.

**Core loop:** student writes → sees the card that *will* be released (privacy preview) → submits → pipeline classifies, extracts, generalises, audits, discards raw text → card released after a delay set by urgency → pattern detector updates → cell acts on patterns and urgent cards → student checks replies with the token.

## 4. The privacy architecture — what "provably impossible" means, honestly

We do not claim "unbreakable". We claim four things, each with a different kind of evidence:

1. **Architectural invariant (verifiable in code and logs).** Raw text exists only in process memory during the ~2-second pipeline run. It is never written to disk, never logged, never displayed, never sent anywhere. The audit log records `raw_discarded_after_ms` for every submission and the console shows it.

2. **Information-theoretic bound on the card channel (provable by construction).** A card is a tuple of categorical fields: distress {none, low, high} × urgency {routine, soon, immediate} × type {8 classes, multi-label capped at 3} × location (generalised hierarchy, ≤ 12 leaves) × time bucket {4} × actor role {3}. The narrative is generated from a template over those fields and adds no information. Therefore a card carries at most `log2(#distinct cards)` bits about *anything*, including the author — computed and displayed per deployment (order of 12–14 bits before generalisation). More importantly, **no author style enters the card at all**: the channel simply does not carry it.

3. **k-anonymity on content (enforced).** The released combination (location, time bucket, type) must appear in at least k cards (k = 3 by default) or the location/time is generalised up its hierarchy ("Hostel B, 2nd floor" → "Hostel B" → "hostels") until it does. Cards that cannot reach k are held in a *quarantine* the cell sees only as a count ("2 cards awaiting k") until more arrive or a time limit forces release at the coarsest level.

4. **Empirical, for the one residual channel (measured).** Optional *detail* text — when the cell truly needs specifics — is not edited but **regenerated**: facts are extracted first, then re-expressed by a translation round-trip and paraphrase so the output's style is the model's, not the student's. Before release, the strongest attacker we could build measures the **style information** in the released text as the total-variation distance between its author posterior on the released text and on a *null template with the same fields* — 0.00 by construction for a template-only card, > 0 only if detail text carries style. Above a margin, the detail is dropped and the card ships template-only. (A forced-choice attacker's raw *confidence* on a template is meaningless — it will say "author X, 96%" about any English sentence — which is why the metric is information over the null, not confidence.) We report the attacker's accuracy on raw text (to prove it is strong) and on released cards (≤ chance, to prove they carry nothing).

**Side channels closed (design rules, all cheap):** no accounts; no IP logging (server config, shown); no cookies or third-party scripts on the submission page; submission time stored only as a day bucket; release delay randomised — immediate urgency: 0–15 min, soon: 1–6 h, routine: next 6-hour batch — so arrival order cannot be matched to hallway observation; request bodies padded to a fixed size; the token is a random passphrase, stored hashed.

**Scope statement for the slide:** *provable for the channels we control (architecture, card channel, k-anonymity, metadata); measured against the strongest attacker we could build for the one channel we can't fully remove.* A judge who has thought about privacy will recognise this as the right shape of claim.

## 4A. Facts, not fingerprints — the Style-Free Account engine (built 15 Sep)

The gap it closes: a categorical card is private but lossy — *"you threw away the evidence"* is the question that would have sunk us. Paraphrasing the text (the original G1 plan) leaks style and cannot be proven. The engine dissolves the trade-off instead of picking a side.

**How it works** (`pipeline/facts.py`, `privacy/rarity.py`, `pipeline/narrate.py`):

1. **Fact graph.** The normalised text is decomposed into closed-vocabulary facts: 21 *acts* (forced standing, money demand, recording, sharing online, threats, unwanted contact, substance coercion…), actor role and count band, place, time bucket, frequency (once / repeated / daily), duration band, money band, digital artefacts, consequences (fear, loss of sleep, injury, missed classes…), whether others were present, whether it is still going on. Numbers are read from the raw text and **banded** (₹1500 → ₹500–2000; 3 ghante → 2–5 hours). Free text never enters a fact.
2. **The student checks the facts.** The privacy preview shows every fact as a chip with the words that produced it ("from your words: *khade*, *1500 rupees*, *whatsapp*"). The student removes a wrong chip, corrects a band, adds a missed act from the closed list. Edits are validated against the closed sets server-side; no free text is accepted.
3. **Per-fact k-anonymity.** Each *identifier* fact — where, when, how much, how long, how many, how often — is widened up its hierarchy until at least k released cards share it, and the student sees the arrow ("₹500–2000 → some money"). **What happened is never suppressed**: a single report of sexual harassment reaches the committee even if it is the only one; a single report naming "room 214 at 2:40 am" cannot.
4. **Controlled generation.** A fixed grammar turns the fact graph into a full account — *"A group of senior students made the reporter stand for two to five hours, demanded money (an unspecified amount) and recorded the reporter on the second floor of Hostel B at night. A messaging group and a video were involved. This has happened more than once. The reporter describes fear and loss of sleep."* — using only a 178-word lexicon built from the grammar's own fragments.
5. **The invariant.** `narrate()` tokenises its own output and **raises** if any token is outside the lexicon; the audit re-checks and reports `foreign_tokens` per card. Same facts → same words, always: variation cannot encode style because there is none.

**What we can now claim, and how each claim is backed:**

| Claim | Kind | Evidence |
|---|---|---|
| Not one of the student's words, spellings, emoji or punctuation reaches the committee | provable by construction, enforced at runtime | lexicon invariant; `evaluate.py`: *1,084 account words released, 0 outside the lexicon* (dev seed) |
| The account channel is bounded | provable | `narrative_capacity_bits` ≈ 54.7 bits — the fact space; none of it style |
| The attacker cannot attribute accounts | measured | leave-one-out attribution on accounts ≤ chance (dev seed: 11% vs 17%); linkability AUC 0.45 |
| The attacker now links by *content*, not *author* | measured, shown live | Present slide 4: on raw text its best pair is the true pair at 81% (next 2%); on accounts its best pair is a different one — two incidents at the same place |
| The committee can act | practical | acts, place, time, frequency, money, media, consequences — in a sentence a warden can brief from |
| Nothing a student types can reach the committee — for *any* writer | adversarial, non-circular | 3,000 fuzzed inputs (Hinglish, Devanagari, emoji, HTML, URLs, names, injection lines) each with a planted canary: 0 canaries in accounts, 0 in stored cards, 0 student words, 0 foreign tokens |
| Style never enters — same incident, any style, one account | property test | 3 incidents × 7 styles → 3/3 identical accounts; the attacker attributes the 7 raw texts to 6 different authors |

**Why competitors cannot match it in the room:** it requires the insight to *replace* rather than *sanitise*, a fact schema and a Hinglish/Marathi cue lexicon, per-fact generalisation, a grammar with a runtime invariant, and an attacker to prove it — plus the honesty to say what it does not do: facts the extractor misses are the student's to add, and the student sees exactly what will be said.

## 5. Data — availability, collection, labels, ground truth

### 5.1 What exists publicly (VERIFY licences and current download paths before use)

| Resource | What it is | Use |
|---|---|---|
| SemEval-2020 Task 9 "SentiMix" Hinglish | ~17k+ code-mixed Hindi-English tweets with sentiment labels | Domain pre-training and an auxiliary sentiment head |
| HASOC (2020/2021) Hindi-English code-mixed subtasks | Hate/offensive labels on code-mixed text | Auxiliary "abusive language" head — helps detect verbal abuse in complaints |
| L3Cube HingCorpus / HingBERT / HingRoBERTa | Large roman-script Hinglish corpus and pretrained encoders (L3Cube, Pune) | Best starting encoder for Hinglish |
| L3Cube MahaSent / MahaHate + MahaBERT | Marathi sentiment/hate datasets and encoders | Marathi-English coverage for Mumbai colleges |
| google/muril-base-cased; ai4bharat/IndicBERTv2 | Multilingual Indian-language encoders incl. transliterated text | Alternative encoders |
| PAN authorship attribution shared-task corpora | Multi-author texts for authorship attribution | Optional pre-training of the attacker |

None of these contains ragging complaints. They give the encoders and the auxiliary tasks; the in-domain data must be ours — and it is the one dataset that makes the privacy claim *real*.

### 5.2 The Unsigned corpus (real, in our control, ready by 17 Sep)

**Who writes:** 30–40 students from the team's college(s), consented, each writing **≥ 5 short complaints** (2–6 sentences) *as if* they were a first-year student. They are told to write the way they text — Hinglish or Marathi-English, their own punctuation, emoji, spelling — because the *style* must be real even though the *incidents* are fictional.

**What each writer produces:** 3 ragging-type complaints of varying severity (at least one sarcastic — "wow such a warm welcome from seniors, love standing for 3 hours"), 2 mundane campus complaints (mess, wifi, attendance) as hard negatives. Optional: 1 in a different mood to test within-author variance.

**Collection:** a Google Form: consent text → assigned author code (A01…A40) → five text boxes → optional "which language mix do you use?" Nothing else. ~175–200 texts.

**Labels:** two annotators label every text independently: `distress ∈ {0,1,2}`, `urgency ∈ {routine, soon, immediate}`, `type ⊆ {verbal_abuse, physical, coercion_forced_acts, exclusion_social, sexual_harassment, extortion_financial, cyber, none}`, `sarcasm ∈ {0,1}`, and free-text spans for `location`, `time`, `actor_role`. Disagreements resolved by discussion; **Cohen's κ reported** on the slide. Annotation guide is in `data/annotation_guide.md`.

**Ground truth for the privacy experiment:** authorship is known by construction (the author code). This is what makes the attack a real experiment, not a simulation.

**Ethics on the slide:** fictional incidents; informed consent; no real complaints are processed during the hackathon; the corpus is deleted after evaluation; the live demo uses team-written examples.

### 5.3 Augmentation (training only, never in reported numbers)

Back-translation variants, transliteration variants (romanisation spellings), emoji/punctuation perturbation for the *classifier* only — never for the attacker's evaluation set.

## 6. AI/ML architecture

**Governing rule:** each model ships with an ablation; a model that doesn't beat its simpler baseline on held-out data ships disabled. No LLM anywhere in the pipeline.

| ID | Model | Input → Output | Method | Data | Ablation |
|---|---|---|---|---|---|
| **C0** Baseline classifier | text → distress, urgency, type, sarcasm | Char + word n-gram TF-IDF → logistic regression (one per head). Always shipped; runs anywhere | Corpus + public auxiliary sets | The floor every other model must beat |
| **C1** Encoder classifier | same | Fine-tuned HingRoBERTa / MuRIL with four heads; auxiliary sentiment/abuse heads from public data; sarcasm-aware augmentation | Corpus + public | Macro-F1 vs C0; F1 on the sarcastic subset; false-alert rate on mundane complaints |
| **X0** Extractor | text → location, time, actor role, behaviours | Gazetteer (hostel/block/department names, time words in Hindi/Marathi/English) + regex + keyword taxonomy; C1's type probabilities | Corpus spans | Field accuracy vs annotators |
| **X1** Span model (optional) | same | Token classification head on the encoder | Corpus spans | Only if it beats X0 |
| **A1** Stylometry attacker | texts → author; pair → same-author probability | Char 2–5-gram TF-IDF + style features (punctuation profile, emoji rate, caps ratio, word-length distribution, function-word frequencies, spelling-variant choices) → logistic regression / linear SVM; plus a fine-tuned encoder variant, ensembled | Corpus (known authors) | Accuracy@1 leave-one-text-out; pairwise linkability AUC — reported on raw text, normalised text, regenerated detail, and cards |
| **N1** Normaliser | text → normalised text (internal only) | Lowercase, punctuation canonicalisation, emoji removal, repeated-character squashing, Hinglish spelling canonicalisation (nhi/nai/nahi → nahi), digit normalisation | Dictionary | Attacker accuracy drop (this is *not* the privacy mechanism — it is a pre-processor for classification) |
| **F1** Fact extractor + **N2** controlled generator (Section 4A) | text → fact graph → account | Cue lexicons + number banding → closed facts; per-fact k-anonymity; grammar over a 178-word lexicon with a runtime invariant | Corpus spans (for extractor coverage) | Fact coverage on ragging texts; foreign tokens (must be 0); attacker attribution on accounts vs chance |
| **K1** Generaliser | card → k-anonymous card | Hierarchies for location and time; generalise until (location, time, type) appears ≥ k | Cards | k achieved; share of cards generalised |
| **P1** Pattern detector | cards over time → alerts | Counts per (location, time bucket, type) per week vs a Poisson baseline; alert when surprise exceeds threshold with ≥ m distinct cards | Cards (replayed timeline for the demo, labelled simulated) | Detection lead time on the replay |

**Training / inference:** C0, A1, X0, K1, P1 need no GPU and train in seconds. C1 fine-tunes in under an hour on a free Colab GPU and exports to ONNX for CPU inference. G1 is optional and heavy; if unavailable, cards ship template-only — and that is the *more* private configuration. Inference per submission: ~1–2 s on a laptop CPU without G1.

**Explainability:** every card carries "why": the top n-gram features behind the distress and type decisions (from C0/C1 attributions), the extracted spans that filled each field, the generalisation steps applied, and the audit result. The committee can see *why* a card is urgent without seeing the text.

## 7. System architecture

```
Student phone ──HTTPS on college LAN──▶ Submission page (no cookies, no trackers, padded requests)
      │  /preview  ─▶ Pipeline (in memory): N1 → C1|C0 → X0 → card → K1 → A1 audit ─▶ card preview + risk flags
      │  /submit   ─▶ same, then: raw text discarded ▸ card queued with urgency-based delay ▸ token issued (hashed)
                                                     │
                     Release scheduler ─▶ SQLite (cards, audits, patterns, replies; never raw text)
                                                     │
                     Committee console ◀── FastAPI + WebSocket ──▶ P1 pattern detector ──▶ alerts (console, SMS/e-mail optional)
                     Student status page (token) ◀──────────────▶ anonymous replies
```

**Backend (Python, FastAPI):** `POST /preview` (returns the card that *would* be released, with rarity flags — nothing stored); `POST /submit` (runs the pipeline, discards raw text, queues the card, returns a passphrase token); `GET /cards` (released cards, generalised); `GET /patterns`; `GET /audit` (attacker results, leakage bound, k achieved, `raw_discarded_after_ms` distribution); `POST /cards/{id}/reply` (cell → student, via token); `GET /status/{token}`; `GET /eval/latest`.

**Storage (SQLite, single laptop):** `cards` (fields, generalisation level, urgency, released_at bucket, why-features), `audits` (per-card attacker score, decision), `patterns`, `replies`, `tokens` (hash only), `metrics`. There is no table for raw text; the schema is shown on a slide.

**Submission page:** plain HTML + minimal JS, served from the same laptop; QR code for the demo; the *privacy preview* renders the card and highlights any field combination that would currently be unique ("this combination matches fewer than 3 reports — we will generalise 'Hostel B, 2nd floor' to 'Hostel B'").

**Console (React + Vite or plain HTML):** three tabs — **Patterns** (map/heat grid of location × time × type with rising-trend alerts), **Cards** (released cards, urgent first, each with "why" and audit badge), **Evidence** (attacker accuracy raw vs released, leakage bits, k, discard latency, classifier metrics — all from `evaluate.py`, dated). A demo-only toggle "show what an attacker sees with raw text" drives the wow moment.

**Deployment:** one `docker compose up` or `python -m unsigned` on a college laptop; no cloud; optional SMS/e-mail for immediate-urgency alerts.

**Failure handling:** pipeline exception → submission acknowledged, card marked "needs manual triage" with *no text attached* (the raw text is still discarded); the student's token still works; the cell sees a count. Encoder unavailable → C0 baseline. Audit unavailable → template-only cards (fail closed to the more private mode).

## 8. The prototype — repository layout and build order

```
unsigned/
  pipeline/normalize.py      N1 lexical normaliser
  pipeline/classify.py       C0 baseline heads (+ C1 loader when trained)
  pipeline/extract.py        X0 gazetteer/regex extractor → card fields
  pipeline/card.py           Card schema, template narrative, leakage bits
  privacy/attacker.py        A1 stylometry attacker (fit / attribute / link)
  privacy/kanon.py           K1 hierarchies and generalisation
  privacy/audit.py           attacker-in-the-loop release decision
  patterns/detect.py         P1 rising-pattern detector
  api/app.py                 FastAPI: preview / submit / cards / patterns / audit / status
  web/submit.html, console.html
scripts/evaluate.py          every number for the slides, dated
scripts/train_transformer.py C1 fine-tune (optional; needs transformers)
data/collection_form.md, annotation_guide.md, corpus_schema.csv
data/dev_seed.csv            team-written examples for smoke tests — never in reported numbers
```

**Build order:** (1) corpus schema + dev seed + A1 attacker (the hook works on day one) → (2) N1 + C0 + X0 + card + K1 → (3) API + submission page + preview → (4) audit + console + Evidence tab → (5) `evaluate.py` on the real corpus → (6) C1 fine-tune → (7) P1 + replay → (8) G1 only if time remains.

## 8A. Prototype status — the complete app, built and tested on 14 Sep (`unsigned/`)

Run: `python scripts/evaluate.py --train` → `python scripts/seed_demo.py` → `python -m unsigned --port 8000 --key committee`. Checks: 7 unit tests (`tests/test_pipeline.py`) and a 17-step end-to-end smoke test (`tests/smoke_api.py`) — all passing.

| Surface / component | Status | What it does |
|---|---|---|
| Student: submission page | built | Warm-paper identity, serif voice. Write → **Show me the card first** (exact card, rarity flags, traceability meter) → **Send** → the words visibly **shred** away with a "raw text discarded" stamp → passphrase |
| Student: case page | built | Passphrase → status timeline, committee replies, **add information** (threaded through the same pipeline) |
| Committee: console (passcode) | built | Dark operations identity. **Overview** (KPIs, location × time heat grid with cells below k hidden, rising-pattern alerts with actions, cards-per-week, "needs you now") · **Cases** (filter chips, table, detail drawer with "why", linkability audit + raw toggle, thread, reply, status) · **Privacy proof** (pipeline stepper, attacker bars vs chance, try-it, k / latency / F1 tiles, dev-seed warning) · **Demo setup** (the three complaints for Present, reference samples) · weekly report |
| **Present mode** | built | Nine full-screen slides computed live on the real models: hook → attacker reveal with animated link → shredding into cards → attacker on cards → live QR step with the meter flipping → heat grid + alert → measured proof → close. ← → keys, F fullscreen |
| Sanitiser pipeline | built | normalize → classify (C0) → extract (X0) → card → k-anon → audit → discard; ~20 ms |
| A1 attacker | built | 97% attribution on dev-seed raw text (chance 17%); 92% after normalisation; ≤ chance on cards |
| Audit metric | built | leak = TV distance vs a null template (0.00 for template cards); demo mode reports P(reference author | raw) vs P(· | card) |
| K1 k-anonymity | built | stored at full detail, displayed at the level shared by ≥ k cards; groups match on location/time with any shared type |
| P1 pattern detector | built | Poisson-surprise per location × time × type; on the seeded timeline: *hostel b · night · coercion — 7 cards* |
| Side channels | built | no accounts, no IP logs (access log off), no cookies, day buckets, urgency-randomised release delay, padded requests, no-store/no-referrer headers, flood control without identity |
| **Non-circular proofs** | built | `scripts/fuzz_release_channel.py`: 3,000 adversarial inputs with planted canary words → 0 canaries in any account or stored card, 0 student words, 0 foreign tokens · `scripts/style_invariance.py`: 3 incidents × 7 styles (lowercase, CAPS+emoji, formal, Marathi, SMS, sarcastic, Devanagari) → one identical account each while the attacker sees 6 authors in the raw texts · both in the test suite and on the Evidence tab / Present |
| Rules layer (`pipeline/rules.py`) | built | transparent post-classifier rules (campus-services complaint with no act → not ragging; sarcasm about a real act → high distress); every firing recorded in `why`; under grouped CV the **system** cuts false alerts on mundane complaints 35% → 10% and lifts sarcastic-subset distress F1 0.52 → 0.63 — structurally, not by seed tuning |
| Hallway-test instrument | built | `data/user_study.md` protocol + one-tap anonymous feedback on the student page (`/api/feedback`, counts only) surfaced on the Evidence tab |
| Number words | built | "three hours", "paanch sau rupees", "do ghante" band correctly |
| Devanagari input | built | `translit.py` — native-script Hindi/Marathi reach the same cues; tested |
| Hardening after adversarial review | built | demo gating (`--no-demo`), latency padding, atomic model-file writes under a lock, FastAPI lifespan, ARIA + focus management + loading states, honest erasure copy, corpus importer |
| C1 encoder fine-tune | script ready | `scripts/train_transformer.py`; needs `transformers` and the real corpus; ships only if it beats C0 |
| **Style-Free Account engine** | built | fact graph (21 acts, banded numbers, Hinglish/Marathi cues) · student fact editor with spans and add/remove · per-fact k-anonymity with visible widening · 178-word lexicon grammar with runtime invariant · `foreign_tokens` in every audit · new evaluation metrics |

Dev-seed numbers are smoke tests. The Round 2 slide numbers come from `evaluate.py` on the real corpus, dated.

## 9. Evaluation — what `evaluate.py` prints (with the run date)

- **Attacker strength:** A1 accuracy@1 on raw text, leave-one-text-out over N authors (chance = 1/N); pairwise linkability AUC.
- **Privacy result:** the same attacker on normalised text, on regenerated detail (if G1 is on), and on cards — expected ≈ chance / AUC ≈ 0.5.
- **Leakage bound:** `log2(#distinct cards)` for the deployed schema, before and after generalisation.
- **k-anonymity:** k achieved on the released set; share of cards generalised; quarantine count.
- **Discard latency:** distribution of `raw_discarded_after_ms`.
- **Classifier:** C0 vs C1 macro-F1 per head (5-fold, grouped by author so no author leaks across folds); F1 on the sarcastic subset; false-alert rate on mundane complaints; κ between annotators.
- **Extractor:** field accuracy vs annotators.
- **Pattern detector:** lead time on the replayed timeline (labelled simulated).
- **Latency:** per-submission pipeline time on the laptop.

Nothing goes on a slide that this script did not print.

## 10. The live demo (six minutes)

| Time | On screen | What happens |
|---|---|---|
| 0:00 | Three anonymous complaints, no names | "Two of these were written by the same student. Which two?" Judges guess. |
| 0:20 | A1 attacker output: pair (1, 3), 82% | "Any warden with a laptop can do this. Deleting the name is not anonymity." |
| 0:50 | The naive system: sentiment score + raw text in a committee inbox | "This is what every anonymous complaint box is. It leaks by design." |
| 1:30 | Unsigned submission page on a judge's phone (QR) | The judge types a sarcastic Hinglish complaint. **Privacy preview** shows the exact card; "Hostel B, 2nd floor" is flagged rare and generalised before their eyes. |
| 2:30 | Submit → the words shred; the console shows the **account** — a full paragraph in our words, every fact a chip, the rare ₹ band visibly widened; `raw text discarded after 22 ms · 61 words, 0 of them the student's` | "That text no longer exists anywhere. This is what the committee reads." |
| 3:00 | **Linkability Audit meter:** attacker tries to link the judge's card to their earlier complaint → 3% (chance). Toggle "what the attacker sees with raw text" → 82%. Red → green. | The twist, solved and measured, on the judge's own words. |
| 3:45 | Patterns tab: replay six weeks of cards → "rising pattern: Hostel B · nights · coercion — 7 distinct cards over 3 weeks" → alert with an action | "The cell acts on the hostel and the hour, not on a person." |
| 4:30 | Student status page with the passphrase token: the cell's reply is visible, no identity | The student is not alone after reporting. |
| 5:00 | Evidence tab: attacker raw vs cards, leakage bits, k, discard latency, C0 vs C1, sarcastic-subset F1, κ — dated | Everything measured, nothing asserted. |
| 5:40 | Close | "Mandated in every college. Runs on one laptop. The committee sees the danger, never the student." Each member names their part. |

Fallbacks: recorded replay of every step with a visible badge; the judge's phone step has a pre-typed example if the LAN misbehaves.

## 11. Scoring on the eight official criteria

| Criterion | Where the points come from | Evidence |
|---|---|---|
| Innovation | Never release the text; attacker-in-the-loop audit; provable card channel; privacy preview | The audit meter; the leakage bound |
| Problem Understanding | Twist solved by *not releasing style*; plus content self-identification, metadata side channels, pattern-level action, the student's aftermath | Preview flags; side-channel slide; patterns tab; token page |
| Technical Implementation | Code-mixed multi-head classifier, extractor, stylometry ensemble, k-anonymity, scheduler, pattern detector; ablations | `evaluate.py` output, dated |
| Scalability | One laptop per college; no cloud; no per-unit cost; schema-driven | Deployment slide |
| Practical Impact | UGC-mandated committees in every institution; earlier detection of patterns; a channel students will trust | Replay lead time; the preview |
| Presentation | The "which two?" hook; the meter turning green on the judge's own text | The script |
| User Experience | Privacy preview; three-tap submission; passphrase token; patterns-first console | Live on a judge's phone |
| Teamwork | NLP · privacy/attacker · backend/console · data/annotation/pitch | Hand-offs |

## 12. Hostile-judge Q&A

- **"Provably impossible? Nothing is."** Correct — so we don't claim that. Provable for the channels we control: the architecture (no text stored), the card channel (a bounded categorical tuple with no style in it), k-anonymity, closed metadata channels. Measured for the one channel we can't fully remove, against the strongest attacker we could build — here is its accuracy on raw text, and here it is on our outputs.
- **"Your attacker is weak, so 'chance' means nothing."** It reaches N% attribution accuracy on raw text over N authors — far above chance — and a pairwise AUC of X. It is a standard PAN-style ensemble. Bring a stronger one; the audit slot is pluggable.
- **"The committee needs details to act."** They get a full account — who, what, where, when, how often, how long, how much, what media, what effect — regenerated from the fact graph in our words. Here is one. Here is the count of the student's words in it: zero, enforced at runtime, re-checked in every audit.
- **"Your extractor will miss things."** Yes, and the student sees exactly which facts were captured, with the words that produced them, and adds or removes facts from a closed list before sending. The student is the reviewer; the text never leaves the phone to be reviewed by anyone else.
- **"Content can identify a student."** Yes — which is why the student sees the card first, with rare combinations flagged and generalised. The reporter controls the content; we make the risk visible before submission.
- **"How do you reach the student?"** They reach us: a passphrase token they alone hold; replies are visible on the status page; no identity ever.
- **"Small dataset."** The privacy result does not depend on classifier accuracy. The classifier reports honest F1 on 175–200 in-domain texts plus public auxiliary data, with the sarcastic subset broken out.
- **"Isn't paraphrasing enough?"** No — paraphrase leaks and is unmeasured. We don't paraphrase the text; we replace it with a card, and only regenerate optional detail under audit.
- **"Your numbers come from 36 texts you wrote yourselves."** The privacy proofs don't: 3,000 adversarial inputs with planted canaries and zero leaks, and seven styles of one incident producing one account — those hold for any writer. The attacker-accuracy number does depend on real writers; it comes from the collected corpus with its run date, and anything still from the dev seed is labelled on screen.
- **"Is this an LLM wrapper?"** There is no LLM in it. Nothing in the pipeline is heavier than a logistic regression.
- **"Why a regex extractor and not a neural model? This is the AI/ML track."** Because the extractor sits *inside the privacy boundary*. A neural span model is a black box we cannot audit for what it leaks into its outputs; a cue lexicon is a list a judge can read. The extractor's job is narrow — map phrasings to 22 closed acts — and its misses are visible to the student, who repairs them before sending. The ML in Unsigned is where ML belongs: the distress/urgency classifier, and the attacker that proves the release channel is clean. If a fine-tuned encoder (C1) beats the baseline on the real corpus under grouped cross-validation, it ships; if not, it doesn't — that ablation is in `evaluate.py`.
- **"Your extractor is brittle — what about Devanagari, or 'they wouldn't let me leave'?"** Native-script Hindi and Marathi are transliterated before every other step, so one cue set covers both scripts (`translit.py`); "wouldn't let me leave", "locked us in", "threw water on me", "aggressive", "takleef" are covered, and `tests/test_coverage.py` holds phrasings the seed was *not* written around. Every miss you find in the real corpus is a one-line addition, and the student sees exactly what was captured.
- **"`del text` is not secure erasure."** Correct, and we don't claim it. The guarantee is architectural, not about memory: no table, log, response or channel can carry the text, and the account is generated from a lexicon that cannot contain it. `del` drops the reference; a hardened deployment would add memory locking and zeroing. The bytes lingering in a process page cannot reach the committee, because nothing reads them.
- **"Response time leaks text length."** Every submission-path response is padded with random latency (20–140 ms) on top of its own compute, and requests are padded to a fixed size. Absolute timing still varies with load; the text-length signal is gone.
- **"`demo_author` is a privacy hole."** It is honoured only in demo mode. `python -m unsigned --no-demo` disables it along with Present mode and the attacker endpoints; in that mode the field is silently dropped.
- **"The narrative is repetitive and mechanical."** By design: same facts, same words, always — variation is the one thing a generator could use to smuggle style back in. The committee reads a report, not prose.
- **"Who deploys it?"** The institution's anti-ragging committee, on a laptop the college already owns. Cost: zero per complaint.

## 13. Risks and elimination

| Risk | Elimination |
|---|---|
| Corpus not collected in time | Form goes out today; 30 writers × 5 texts is 20 minutes each; team members recruit 8 each |
| Low classifier accuracy on sarcasm | Public auxiliary data; augmentation; report the sarcastic subset honestly; the privacy story carries |
| Weak attacker undermines the claim | Build the ensemble; show raw-text accuracy first; keep the slot pluggable |
| G1 (regeneration) too heavy for the laptop | It is optional; template-only cards are the more private default |
| "Provably" over-claimed | The scoped four-part claim; never the word "unbreakable" |
| Demo LAN/phone failure | Pre-typed examples; recorded replay with badge |
| Ethics concerns | Fictional corpus, consent, deletion after evaluation, no real complaints processed |
| Domain lock | CX0105 is AI/ML — confirm registration before 16 Sep |
| "All your numbers are from 36 texts you wrote" (the adversarial review's strongest point) | True until the corpus exists. `scripts/import_corpus.py` turns the form export into `corpus.csv` in one command; every slide number is regenerated by `evaluate.py` with its run date; the dev-seed warning banner is shown until then |
| Extractor misses on real phrasings | Devanagari transliteration; wider cue lexicon; `tests/test_coverage.py`; the student's fact editor as the repair path |

## 14. Timeline and roles (today is 14 Sep)

| Dates | Milestone |
|---|---|
| 14 Sep | Collection form live; scaffold running on the dev seed; A1 attacker demo working; Round 1 document drafted (Sections 0, 1, 4, 5) |
| 15–16 Sep | ≥ 100 texts in; A1 numbers on real authors; C0 + X0 + card + K1; **Round 1 submitted 16 Sep** |
| 17–19 Sep | Corpus complete and double-annotated (κ); API + submission page + privacy preview; audit + console; `evaluate.py` v1 on real data |
| 20–22 Sep | C1 fine-tuned (Colab) and ablated; P1 + replay; Evidence tab; deck + 3-minute recorded demo; **Round 2 on 22 Sep** |
| 23–25 Sep | Side-channel hardening; token/reply channel; G1 only if audit passes; feature freeze 25 Sep |
| 26 Sep | Four rehearsals with hostile Q&A; replay files exported with dates |
| 27 Sep | Finale |

**Roles:** (1) NLP — C0/C1, X0, augmentation, `evaluate.py` · (2) Privacy — A1 attacker, K1, audit, side-channel rules, the four-part argument · (3) Backend/console — API, scheduler, storage, submission page, preview, console · (4) Data & pitch — recruitment, annotation lead, κ, deck, demo direction. Everyone writes 5 seed texts and recruits 8 writers.

## 15. Deck skeleton (12 slides)

1. Unsigned — the committee sees the danger, never the student.
2. "Which two are from the same student?" — the hook, with the attacker's answer.
3. Why anonymous boxes leak — style, content, metadata.
4. The twist, decomposed — R1–R5 and our answers.
5. Never release the text — the card channel and its bound.
6. Attacker in the loop — the linkability audit and the meter.
7. Privacy preview — the student sees the card first.
8. Patterns, not people — the detector and an alert.
9. Evidence — `evaluate.py` table, dated.
10. Architecture — one laptop, no cloud, no raw-text table.
11. Adoption — UGC-mandated committees; zero cost per complaint; the aftermath channel.
12. Team.

## 16. Facts, assumptions, VERIFY

**KNOWN:** PS text, timeline, criteria; UGC anti-ragging regulations mandate institutional committees (VERIFY exact citation); character n-gram models are the standard strong baseline for authorship attribution; the public datasets and encoders listed exist (VERIFY licences and paths).

**ASSUMPTIONS:** fictional complaints written by real students preserve real style; k = 3 is an acceptable anonymity floor for a college of a few thousand students (configurable); the cell can act on patterns plus categorical cards.

**VERIFY (owner: member 4):** dataset licences and download paths; UGC regulation citation; that the chosen encoder handles roman-script Marathi; Colab GPU availability the week of 20 Sep.
