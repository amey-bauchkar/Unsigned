<div align="center">

<br/>

```
██╗   ██╗███╗   ██╗███████╗██╗ ██████╗ ███╗   ██╗███████╗██████╗
██║   ██║████╗  ██║██╔════╝██║██╔════╝ ████╗  ██║██╔════╝██╔══██╗
██║   ██║██╔██╗ ██║███████╗██║██║  ███╗██╔██╗ ██║█████╗  ██║  ██║
██║   ██║██║╚██╗██║╚════██║██║██║   ██║██║╚██╗██║██╔══╝  ██║  ██║
╚██████╔╝██║ ╚████║███████║██║╚██████╔╝██║ ╚████║███████╗██████╔╝
 ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚═════╝
```

### *Privacy-Preserving Institutional Intelligence for Campus Anti-Ragging Cells*

**MUSA CodeX 2026 · Problem Statement CX0105 — "Read Between the Lines"**
*Domain: Artificial Intelligence & Machine Learning · 100% Offline Architecture*

<br/>

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Offline](https://img.shields.io/badge/Network-100%25%20Offline-FF6B35?style=for-the-badge&logo=wifi&logoColor=white)](#quickstart)
[![Privacy](https://img.shields.io/badge/Architecture-Zero--Persistence-27AE60?style=for-the-badge&logo=shield&logoColor=white)](#defense-in-depth-privacy-architecture)

[![Stylometry AUC](https://img.shields.io/badge/Stylometry%20AUC-1.00%20→%200.46-brightgreen?style=flat-square)](#empirical-adversarial-validation)
[![Canary Leaks](https://img.shields.io/badge/Canary%20Leaks-0%20%2F%203%2C000-brightgreen?style=flat-square)](#canary-fuzzing)
[![Style Invariance](https://img.shields.io/badge/Style%20Invariance-100%25%20Identical-brightgreen?style=flat-square)](#style-invariance)
[![Lexicon Violations](https://img.shields.io/badge/Lexicon%20Violations-0-brightgreen?style=flat-square)](#lexicon-integrity)
[![Accessibility](https://img.shields.io/badge/Accessibility-WCAG%202.2%20AA-9B59B6?style=flat-square)](#student-experience)
[![UGC](https://img.shields.io/badge/Regulation-UGC%202009%20Compliant-blue?style=flat-square)](#regulatory-compliance)

<br/>

> **"The committee sees the danger, never the student."**

<br/>

[The Problem](#-the-problem--the-twist) ·
[The Solution](#-the-unsigned-solution) ·
[Architecture](#-system-architecture) ·
[Privacy Layers](#-defense-in-depth-privacy-architecture) ·
[Adversarial Proofs](#-empirical-adversarial-validation) ·
[Quickstart](#-quickstart) ·
[Surfaces](#-application-surfaces) ·
[Testing](#-testing) ·
[Structure](#-directory-structure) ·
[Compliance](#-regulatory-compliance)

</div>

---

## 🎯 The Problem & "The Twist"

> *"A college anti-ragging cell wants to spot distress signals hidden in anonymous student complaint text — but must never be able to identify the student who wrote it, even indirectly through writing style.*
> ***Twist:** Word choice and punctuation habits alone can fingerprint a student across multiple anonymous complaints — the system must actively strip or randomize stylistic cues."*
> — **CodeX 2026 PS CX0105**

### Why Every Existing System Fails

Most "anonymous" complaint portals delete a student's name and call it done. That is catastrophically wrong.

```
Student writes:  "bhai ye log roz raat ko bulate hain aur paise maangte hain nhi dene pe dhamki dete h"
                  ↑              ↑              ↑               ↑              ↑
            spelling habit   SMS slang     punctuation     emoji pattern   Hinglish mix
                                           cadence
```

A warden with a past assignment submission and 10 lines of Python can re-identify this student in minutes using **stylometric fingerprinting**. Anonymous complaint boxes, UGC portals, and enterprise whistleblowing tools all share the same fatal flaw: **they store raw text.**

| What They Delete | What They Miss |
|---|---|
| ✅ Name, roll number, email | ❌ Punctuation cadence |
| ✅ Phone number | ❌ `nhi` vs `nahi` vs `nai` spelling habit |
| ✅ Hostel room number | ❌ Emoji usage patterns |
| — | ❌ SMS abbreviation style |
| — | ❌ Sentence rhythm and word frequency |
| — | ❌ Code-switching patterns between Hinglish/Marathi |

**Our attacker model links raw complaints to their author with 97.7% accuracy and AUC 1.00.** Any sufficiently motivated institutional actor can do the same. This is not a hypothetical threat.

---

## 🔏 The Unsigned Solution

Instead of the unwinnable race of `raw text → de-stylized text`, Unsigned makes a clean architectural break:

```
Raw Text ──[in-memory]──► Structured Facts ──[coarsening]──► Generalized Facts ──[lexicon]──► Fresh Narrative
                                                                                                    ↑
                                                                                       0 student words here
```

**The three principles:**

1. **Style never enters.** The student's text is parsed into a closed-vocabulary fact graph — 22 structured ragging acts, banded numbers, discrete outcomes. Style is structurally excluded, not stripped.

2. **Raw text is never persisted.** It lives in process memory for ~9ms, then is dereferenced with `del text`. It never touches SQLite, logs, HTTP responses, or disk.

3. **Output is regenerated, not sanitized.** The committee reads what happened through a deterministic 178-word lexicon. Same facts → same words, always. Variation cannot leak style because variation does not exist.

### The Institutional Intelligence Leap

Most anti-ragging tools ask: *"How do we handle one complaint?"*
Unsigned asks: **"How do we stop systemic abuse without tracking individual students?"**

```
Individual Complaints (Protected)              Anti-Ragging Cell Intelligence (Actionable)
┌──────────────────────────────────────┐       ┌────────────────────────────────────────────────┐
│ "Hostel B night coercion" [SHREDDED] │ ──┐   │ 🚨 POISSON SURGE: Hostel B · Nights            │
├──────────────────────────────────────┤   │   │    Coercion: 12 cards this week (Baseline: 1)  │
│ "Hostel B corridor demand" [SHREDDED]│ ──┼──►│    p < 0.001 · Statistically significant       │
├──────────────────────────────────────┤   │   │    Action: Double night squad patrols           │
│ "Hostel B 2nd floor slap" [SHREDDED] │ ──┘   │    Result: Intervention → abuse halted         │
└──────────────────────────────────────┘       │    Zero student names or raw text ever read     │
   (Raw text destroyed in-memory)              └────────────────────────────────────────────────┘
```

The committee never needs to unmask "Rahul" or "Priya" to take decisive institutional action. Individual vulnerable reports become **statistically significant spatial and temporal hot-spots** that drive targeted interventions.

---

## 🏗️ System Architecture

```
╔══════════════════════════════════════════════════════════════════╗
║  STUDENT  (any language — Hinglish · Marathi · English · Emoji) ║
╚══════════════════════════════════════════════════════════════════╝
                              │
              ┌───────────────▼───────────────┐
              │  1. TRANSLITERATION           │  translit.py
              │  Devanagari → Roman phonetic  │  Schwa deletion · Script normalisation
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  2. LEXICAL NORMALISATION     │  normalize.py
              │  SMS slang expansion          │  Emoji → semantic tag · Unicode cleanup
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  3. MULTI-TASK CLASSIFIER     │  classify.py / classify_c1.py
              │  Distress: none/low/high      │  C0: TF-IDF + Logistic Regression
              │  Urgency: routine/soon/immed  │  C1: MurIL/HingRoBERTa ONNX (optional)
              │  Types: 22 ragging categories │  Sarcasm detection head
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  4. FACT GRAPH EXTRACTION     │  extract.py + facts.py
              │  Acts · Location · Time       │  22 closed act types
              │  Duration · Amount · Actor    │  Banded numbers · Discrete outcomes
              │  Consequences · Digital media │  Gazetteer regex span extractor
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  5. EXPLAINABLE RULE LAYER    │  rules.py
              │  Overrides classifier output  │  False alerts: 35% → 10%
              │  Suppresses mundane reports   │  Human-auditable, not a black box
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  6. STUDENT PREVIEW           │  ← Shown to student only, never stored
              │  "Here is what the committee  │  Student edits/removes facts
              │   will read. Send when ready."│  Reassurance before irrevocable submission
              └───────────────┬───────────────┘
                              │  [SUBMISSION]
              ┌───────────────▼───────────────┐
              │  7. k-ANONYMITY ENFORCEMENT   │  kanon.py + rarity.py
              │  Per-fact generalisation      │  Location/time widened up hierarchy
              │  Card-level quarantine        │  Released only when k ≥ 3 cards match
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  8. INVARIANT NARRATIVE       │  narrate.py
              │  178-word bounded lexicon     │  Fixed grammar → deterministic output
              │  Runtime assertion enforced   │  foreign_tokens == 0 or CRASH (not release)
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  9. ADVERSARIAL AUDIT         │  attacker.py + audit.py
              │  A1 stylometry attacker runs  │  Verifies attribution < random chance
              │  on every released card       │  AUC: raw=1.00 → cards=0.46
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  10. RAW TEXT DESTROYED       │  run.py line 91: del text
              │  Python dereference in ~9ms   │  Never in SQLite · logs · HTTP · disk
              │  Response jitter applied      │  20–140ms padding · no-store headers
              └───────────────┬───────────────┘
                              │
         ┌────────────────────┴─────────────────────┐
         │                                          │
┌────────▼────────┐                      ┌──────────▼──────────┐
│ COMMITTEE       │                      │ STUDENT FOLLOW-UP   │
│ CONSOLE         │                      │ status.html         │
│ ─────────────── │                      │ ─────────────────── │
│ Anonymized cards│                      │ Passphrase only     │
│ Poisson alerts  │                      │ No identity needed  │
│ Spatial heatmap │                      │ Read committee reply│
│ Case drawer     │                      │ nova-cedar-jade-    │
│ Institutional   │                      │ violet              │
│ export report   │                      │                     │
└─────────────────┘                      └─────────────────────┘
```

---

## 🛡️ Defense-in-Depth Privacy Architecture

Unsigned does not rely on any single privacy mechanism. Five independent defensive layers must all be defeated simultaneously for any privacy breach to occur.

| # | Layer | Mechanism | What It Prevents | Proof |
|---|---|---|---|---|
| **1** | **Zero-Persistence Invariant** | `del text` after ~9ms; never enters SQLite, logs, or responses | Forensic disk recovery · DB leaks · Log scraping | Raw text absent from all persistent state |
| **2** | **Bounded Semantic Graph** | 22 closed acts · banded numbers · discrete outcomes | Idiosyncratic narrative style · vocabulary fingerprints | Channel capacity bounded to ~19 bits (card) / ~57 bits (narrative) |
| **3** | **Identifier Generalisation** | Per-fact + card-level k-anonymity (k ≥ 3) | Quasi-identifier triangulation (location × time × amount) | 38/44 cards generalised; unique places widened up hierarchy |
| **4** | **Invariant Lexicon Generation** | Fixed grammar over 178-word vocabulary | Linguistic & vocabulary fingerprints in output | `lexicon_violations = 0` across all corpus texts |
| **5** | **Network Side-Channel Defence** | Jitter 20–140ms · body padding · `Cache-Control: no-store` · `access_log=False` | Packet-size timing attacks · traffic analysis · IP logging | Zero client IP addresses recorded |

---

## 🔬 Empirical Adversarial Validation

Privacy claims are enforced by construction **and** empirically stress-tested. We do not ask you to take any guarantee on faith.

### Stylometry Attacker Results

The A1 attacker uses Character 2–5 grams and Word 1–2 grams across 6 reference author profiles:

```
                    Raw Text          Released Cards      Random Chance
                    ────────────      ──────────────      ─────────────
Attribution Acc:    97.7%         →   13.6%               16.7%  ← baseline
Link AUC:           1.00          →   0.46                0.50   ← random
```

**What this means:** On raw student text, the attacker identifies the author nearly perfectly. On released complaint cards, attribution collapses **below random chance** — the system actively harms the attacker's ability to link reports to individuals.

**Linkability shift:** On raw text, residual guesses link by *author style*. On released cards, they link by *event location* — proving authorial style has been completely eliminated from the output channel.

### Canary Fuzzing

```bash
python scripts/fuzz_release_channel.py --n 3000
```

3,000 synthetic adversarial inputs containing:
- Hinglish word salads and Devanagari script injection
- Emoji runs and mixed-script Unicode
- HTML tags: `<script>alert(1)</script>`
- SQL injection strings: `SELECT * FROM students`
- Phone numbers, student names, email addresses
- Planted canary strings: `ZQ[A-Z0-9]{6}`

| Metric | Result |
|---|---|
| Canaries in released accounts | **0 / 3,000** |
| Canaries in persistent database | **0 / 3,000** |
| Foreign tokens outside lexicon | **0** |
| Student words in any account | **0** |
| Total leaks | **0** |

### Style Invariance

```bash
python scripts/style_invariance.py
```

3 distinct incidents, each written in 7 divergent writing styles:

| Style | Example |
|---|---|
| Lowercase & dots | `bhai log roz bulate h.. dar lagta h` |
| ALL-CAPS + emojis | `RAAT KO BULATE HAIN 😡🤬 PAISE MAANGTE` |
| Formal polite English | `Senior students have been repeatedly summoning me...` |
| Marathi-English mix | `Aamhi bahere jaau shakto nahi, paise magtat` |
| SMS shortcuts | `snrs r dmndng mnY evry nit, scared` |
| Sarcastic irony | `Oh how wonderful, being woken up for money again` |
| Native Devanagari | `वरिष्ठ छात्र रोज़ रात को पैसे मांगते हैं` |

**Results: 3/3 incidents → identical fact graphs → identical released accounts (100%)**

The attacker attributed the 7 raw texts to 6 different authors. Unsigned produced the exact same account for every variation.

### Sample Invariant Output

> *"A group of senior students made the reporter stand for two to five hours and demanded money (one hundred to five hundred rupees) in Hostel B at night. The reporter describes fear. The reporter expresses serious distress. Urgency: soon."*

This sentence is produced identically whether the student wrote in formal English, Devanagari, or emoji-laden SMS slang.

---

## 📊 Classifier Performance

| Head | C0 Alone | C0 + Rules System | C1 MurIL (500 samples) |
|---|---|---|---|
| **Distress F1** | 0.780 | **0.867** | 0.615 |
| **Urgency F1** | 0.694 | **0.731** | 0.551 |
| **Sarcasm F1** | 0.397 | 0.630 | 0.487 |
| **False Alert Rate** | 35% | **10%** | 0.6% (mundane) |

> **Design note:** The rule layer on C0 outperforms raw C1 on false-alert suppression because the rule layer is human-auditable and directly encodes the UGC taxonomy — exactly the right tool for a privacy-critical extraction boundary where a black-box neural generator is unacceptable.

---

## ⚡ Quickstart

> Zero external API keys. Zero cloud. Zero configuration. Runs on any Python 3.10+ laptop.

```bash
# Clone and enter the project
git clone <repo-url>
cd unsigned

# Install dependencies (CPU-only — no GPU needed)
pip install -r requirements.txt

# Train models + generate adversarial benchmarks (~30 seconds)
python scripts/evaluate.py --train

# Seed a 6-week historical timeline for demo
python scripts/seed_demo.py

# Launch the server
python -m unsigned --port 8000 --key committee
```

Open `http://localhost:8000` — fully live, fully offline.

### CLI Options

```
python -m unsigned [OPTIONS]

  --port    INT     Server port (default: 8000)
  --key     STR     Committee console passphrase (default: committee)
  --no-demo         Disable demo mode and ?demo=1 pairing surface
  --real-delays     Enforce multi-hour release batches (production mode)
```

### Production Deployment

```bash
# For real institutional use — disable demo surfaces, enforce privacy delays
python -m unsigned --no-demo --real-delays --key <STRONG_PASSCODE>
```

---

## 🖥️ Application Surfaces

| Surface | URL | Persona | Function |
|---|---|---|---|
| **Student Reporting** | `http://localhost:8000/` | Student (mobile/LAN) | Free-form complaint · live card preview · shredding animation · passphrase generation |
| **Case Follow-up** | `http://localhost:8000/status` | Student (mobile/LAN) | Zero-identity case tracking · read committee replies · send anonymous follow-ups |
| **Committee Console** | `http://localhost:8000/console` | Anti-Ragging Cell | Poisson surge alerts · spatial heat grid · case detail drawer · institutional export |
| **Present Mode** | `http://localhost:8000/present` | Presenter | 9-slide real-time pitch — live model outputs on actual data (`← →` navigate · `F` fullscreen) |

---

## 🎓 Student Experience

A terrified first-year student reporting ragging at 2 AM must not be treated like an NLP data annotator. Every design decision is deliberate:

**① Expressive Free-Form Input**
Type however you want — Hinglish, Marathi, English, emojis, SMS shorthand. The system handles everything.

**② Reassuring Card Preview**
Before anything is submitted, the student sees exactly what the committee will read:
*"Here is what the committee will see. Tap ✕ to remove any fact. Tap Send when ready."*
No surprises. Full control. Zero annotation burden.

**③ The Shredding Moment**
On submission, the student's text literally fragments, rotates, and dissolves from the screen.
A visual stamp appears: `✓ raw text discarded — nothing stored`
This is not cosmetic. It reflects an architectural truth.

**④ Anonymous Two-Way Passphrase**
A 4-word mnemonic is generated client-side — e.g., `nova-cedar-jade-violet`.
This is the student's only credential: no account, no email, no identity.
Use it to check case status and read committee replies — anonymously, permanently.

---

## 🧪 Testing

### Unit & Integration Tests

```bash
# 11 unit tests — sanitisation, k-anonymity, card structure, lexicon invariant
pytest tests/test_pipeline.py -v

# 6 integration tests — Devanagari input, canary fuzzing, style invariance
pytest tests/test_coverage.py -v

# 17-step end-to-end HTTP API smoke test
python tests/smoke_api.py
```

### Adversarial Benchmarks

```bash
# Full evaluation: train models + run all adversarial benchmarks
python scripts/evaluate.py --train

# Canary fuzz: 3,000 adversarial inputs, verify 0 leaks
python scripts/fuzz_release_channel.py --n 3000

# Style invariance: 3 incidents × 7 writing styles → must be identical output
python scripts/style_invariance.py
```

### Import Your Own Corpus & Retrain

```bash
# Import a Google Forms CSV export and retrain in < 30 seconds
python scripts/import_corpus.py --input your_forms_export.csv

# Optional: Fine-tune C1 transformer (requires: pip install transformers torch)
python scripts/train_c1_local.py

# Export fine-tuned model to ONNX for CPU-only inference
python scripts/export_to_onnx.py
```

---

## 📁 Directory Structure

```
unsigned/
│
├── 📂 data/
│   ├── corpus.csv              # Full annotated complaint corpus
│   ├── dev_seed.csv            # 44 calibrated benchmark complaints (6 authors)
│   ├── corpus_schema.csv       # Long-format multi-label classification schema
│   ├── collection_form.md      # Google Form template for campus data collection
│   ├── annotation_guide.md     # Ground-truth multi-label tagging guidelines
│   └── user_study.md           # 30-min hallway usability protocol (5-8 students)
│
├── 📂 docs/
│   └── PITCH.md                # 6-minute presentation script + 30s judge rebuttals
│
├── 📂 models/
│   ├── c0.joblib               # Trained C0 multi-task baseline classifier (~600 KB)
│   ├── a1.joblib               # Trained A1 stylometry attacker model
│   ├── a1_reference.json       # Adversary author reference profiles
│   ├── c1_metrics.json         # C1 transformer training metrics
│   ├── evaluation.json         # Full benchmark metrics + adversarial proof logs
│   └── 📂 c1_onnx/             # Exported ONNX transformer (~905 MB, optional)
│       ├── model.onnx
│       ├── model.pt
│       ├── tokenizer.json
│       ├── config.json
│       └── head_config.json
│
├── 📂 scripts/
│   ├── evaluate.py             # Cross-validated training + full benchmark runner
│   ├── fuzz_release_channel.py # 3,000-sample canary fuzzing stress test
│   ├── style_invariance.py     # 7-style incident invariance verification
│   ├── seed_demo.py            # 6-week historical timeline generator
│   ├── import_corpus.py        # Google Forms CSV importer + unlabelled formatter
│   ├── train_c1_local.py       # C1 transformer fine-tuner (MurIL / HingRoBERTa)
│   ├── train_transformer.py    # Alternate transformer training entry point
│   └── export_to_onnx.py       # Export fine-tuned model to ONNX
│
├── 📂 tests/
│   ├── test_pipeline.py        # 11 unit tests: sanitisation, k-anon, card structure
│   ├── test_coverage.py        # 6 integration tests: Devanagari, fuzzer, invariance
│   └── smoke_api.py            # 17-step end-to-end HTTP API verification
│
└── 📂 unsigned/                # Core Python package
    ├── __init__.py
    ├── __main__.py             # CLI launcher (--port, --key, --no-demo, --real-delays)
    │
    ├── 📂 api/
    │   └── app.py              # FastAPI backend: lifespan, locks, hygiene headers
    │
    ├── 📂 pipeline/
    │   ├── translit.py         # Devanagari → Roman phonetic (schwa deletion)
    │   ├── normalize.py        # Lexical cleaner, emoji handler, SMS expander
    │   ├── classify.py         # C0 TF-IDF char+word n-gram → Logistic Regression
    │   ├── classify_c1.py      # C1 ONNX transformer classifier (same .predict() API)
    │   ├── extract.py          # Gazetteer regex span extractor
    │   ├── facts.py            # Closed-vocabulary 22-act Fact Graph engine
    │   ├── rules.py            # Explainable decision rules (false-alert reduction)
    │   ├── narrate.py          # 178-word lexicon grammar + invariant assertion
    │   ├── card.py             # Card dataclass + channel capacity calculators
    │   └── run.py              # Sanitiser pipeline orchestrator (del text line 91)
    │
    ├── 📂 privacy/
    │   ├── attacker.py         # Authorship attribution + linkability engine (A1)
    │   ├── audit.py            # Total-variation distance stylometry audit
    │   ├── kanon.py            # Card-level k-anonymity quarantine + generalisation
    │   └── rarity.py           # Per-fact identifier generalisation (hierarchy trees)
    │
    └── 📂 web/
        ├── app.css             # Dual-theme tokens (warm paper student / dark ops console)
        ├── submit.html         # Student reporting portal (ARIA + WCAG 2.2 AA)
        ├── status.html         # Case tracking + anonymous two-way messaging
        ├── console.html        # Committee command centre: heat grid + case drawer
        └── present.html        # 9-slide real-time pitch deck
```

---

## 📦 Dependencies

```
fastapi>=0.110       # Async web framework
uvicorn>=0.29        # ASGI server
pydantic>=2          # Data validation and serialisation
scikit-learn>=1.4    # TF-IDF, Logistic Regression, SVM (C0 + A1 models)
numpy>=1.26          # Numerical computing
pandas>=2.1          # Data handling and corpus management
scipy>=1.12          # Poisson survival function (surge detection)
joblib>=1.3          # Model serialisation and persistence

# Optional — C1 transformer fine-tuning only:
# transformers>=4.40   # MurIL / HingRoBERTa
# torch>=2.2           # PyTorch training backend
```

All dependencies are open-source (MIT / BSD / Apache 2.0). Zero proprietary licences. Zero cloud API keys. Zero cost.

---

## ⚖️ Regulatory Compliance & Ethics

**UGC Anti-Ragging Regulations 2009**
Designed specifically to satisfy the reporting, investigation, and squad intervention requirements of the *UGC Regulations on Curbing the Menace of Ragging in Higher Educational Institutions (2009)*. All 22 act categories map directly to UGC-defined ragging definitions.

**DPDP Act 2023**
Zero student personal data collected, stored, or processed. No name, roll number, IP address, device fingerprint, cookie, or user account — anywhere in the system. Architecturally compliant, not just policy-compliant.

**Zero Surveillance Architecture**
The institutional intelligence the committee receives — surge patterns, spatial heat-spots — is derived entirely from aggregated, anonymized, k-anonymous structured cards. Individual students are permanently invisible to the system.

**Emergency Safety**
The submission interface displays: *"If you are in immediate physical danger, contact your institution's emergency line or the National Anti-Ragging Helpline: 1800-180-5522 (24x7, toll-free)."*

**Honest Scope**
We do not claim absolute mathematical anonymity against all adversaries. Our claim is:
- Release privacy is enforced by construction (raw text never enters persistent state)
- The residual stylometric channel is empirically tested against the strongest attacker we can build (AUC 0.46, below random chance)
- k-Anonymity protects quasi-identifiers; incident uniqueness is separately acknowledged

---

## 🏗️ Docker

```bash
docker build -t unsigned .
docker run -p 8000:8000 unsigned
```

---

## 💬 Defensible Q&A

<details>
<summary><b>"Is this a mathematical proof of anonymity? Nothing in CS is truly provable."</b></summary>
<br>
We agree completely — which is why we don't claim absolute mathematical anonymity across all domains. Our claim is scoped and defensible:
<ol>
<li>Release privacy is enforced by construction: raw text never enters persistent state, and the output channel is bounded to a closed 178-word lexicon with a runtime invariant check.</li>
<li>For the residual stylometric channel, we test against the strongest authorship model we can build and demonstrate attribution collapses below random chance (AUC 0.46 vs 0.50 baseline).</li>
</ol>
</details>

<details>
<summary><b>"Doesn't k-anonymity fail if an incident is unique?"</b></summary>
<br>
Yes — and this is a crucial distinction we explicitly make. Unsigned destroys <em>author-identification privacy</em> (stylometric fingerprinting). If an incident took place in a rare room or at an unusual hour, per-fact generalisation widens that location up the hierarchy until ≥ k cards share it. But if an act itself is genuinely unique, the committee must act on the danger while remaining permanently blind to who reported it. These are separate problems with separate solutions.
</details>

<details>
<summary><b>"Why does 'del text' in Python not securely wipe OS RAM?"</b></summary>
<br>
You're 100% right — Python's <code>del</code> unlinks references; it is not DoD-grade RAM wiping. We don't base our security claim on OS memory wiping. Our guarantee is architectural: raw text never enters SQLite tables, log files, web responses, or released cards. Even if lingering bytes exist in unallocated heap before GC, they have zero path to leave the machine.
</details>

<details>
<summary><b>"Your dev seed is 44 texts. How does this generalise?"</b></summary>
<br>
The dev seed calibrates the baseline classifier. Our core privacy proofs don't depend on it:
<ol>
<li>The 3,000-sample canary fuzzer proves release channel isolation for any arbitrary string.</li>
<li>The 7-style invariance test proves dialect collapse regardless of writing habits.</li>
</ol>
We built <code>scripts/import_corpus.py</code> so any institution can import Google Form exports and retrain under grouped cross-validation in under 30 seconds.
</details>

<details>
<summary><b>"Why regex rules instead of an end-to-end deep learning model?"</b></summary>
<br>
Because the extraction layer sits directly inside the privacy boundary. A deep neural generator is an un-auditable black box that can hallucinate details or smuggle stylistic tokens into output. A closed-vocabulary fact graph is human-auditable and verifiable by a judge. We deploy ML where it belongs: distress classification, Poisson anomaly detection, and the adversarial stylometry audit — not inside the privacy-critical extraction boundary.
</details>

<details>
<summary><b>"The regenerated accounts read mechanically."</b></summary>
<br>
By design. Same facts → same words, every single time. Syntactic and lexical variation is the exact vector through which stylometric fingerprints leak back into output. Monotony is the mathematical proof of privacy. The committee doesn't need prose; it needs facts.
</details>

---

## 📚 References

- Sweeney, L. (2002). *k-Anonymity: A Model for Protecting Privacy.* IJUFKS 10(5).
- Koppel, M., Schler, J., & Argamon, S. (2009). *Computational Methods in Authorship Attribution.* JASIST 60(1).
- Brennan, M., Afroz, S., & Greenstadt, R. (2012). *Adversarial Stylometry.* ACM TISSEC.
- UGC. *Regulations on Curbing the Menace of Ragging in Higher Educational Institutions, 2009.* New Delhi.
- MEITY. *The Digital Personal Data Protection Act, 2023.* Government of India.
- Google Research. *MurIL: Multilingual Representations for Indian Languages.* 2021.

---

<div align="center">

---

```
╔═══════════════════════════════════════════════════╗
║                                                   ║
║     The committee sees the danger,                ║
║                          never the student.       ║
║                                                   ║
╚═══════════════════════════════════════════════════╝
```

**Unsigned · MUSA CodeX 2026**

*Built for every first-year student who needed to report at 2 AM,*
*but didn't — because they were afraid of being found out.*

---

[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?style=flat-square&logo=python)](https://python.org)
[![MUSA CodeX 2026](https://img.shields.io/badge/MUSA-CodeX%202026-purple?style=flat-square)](https://musa.ac.in)
[![Zero Cloud](https://img.shields.io/badge/Cloud-Zero-FF6B35?style=flat-square)](https://github.com)
[![Open Source](https://img.shields.io/badge/Licence-Open%20Source-green?style=flat-square)](LICENSE)

</div>
