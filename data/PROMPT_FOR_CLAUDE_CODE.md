# 🚀 Prompt for Claude Code — Unsigned ML Classifier (Local Training)

> **Paste this entire prompt into Claude Code while inside the project directory: `c:\Users\SEBIN\Desktop\MUSA\unsigned`**

---

You are working on **Unsigned**, an anonymous anti-ragging complaint system at an Indian engineering college. The project is at `c:\Users\SEBIN\Desktop\MUSA\unsigned`.

Your job is to build a complete ML classification pipeline — generate training data, train a transformer model locally on CPU, export to ONNX, and integrate it with the existing system. Do everything step by step, running commands and creating files as you go.

---

# STEP 1: Generate Training Data

Create the file `data/corpus.csv` with **500 annotated training sentences**.

## CSV Schema

```
author,text,distress,urgency,types,sarcasm,mundane
```

- `author`: A01 to A50 (50 fake student IDs). Each author appears 8-12 times.
- `text`: Natural student complaint typed on phone. Quote with double-quotes. Escape any internal double-quotes.
- `distress`: `none` | `low` | `high`
- `urgency`: `routine` | `soon` | `immediate`
- `types`: semicolon-separated from: `verbal_abuse`, `physical`, `coercion_forced_acts`, `exclusion_social`, `sexual_harassment`, `extortion_financial`, `cyber`, `none`
- `sarcasm`: `0` | `1`
- `mundane`: `0` | `1`

## Language Distribution (CRITICAL — this is an Indian college)

- **40% Hinglish** (Hindi+English, Roman script): "bhai seniors ne raat ko khade rakha"
- **25% Marathi-English** (Roman script): "hostel madhe seniors ni mala ubha kela"
- **20% Formal English**: "Sir, I wish to report that some senior students..."
- **10% SMS-style**: "srs ne kal rat 3 hrs khda rkha intro k liye 😭😭"
- **5% Pure Marathi (Roman)**: "kal ratri hostel madhe khup traas dila tyanni"

## Author Style Consistency

Each author (A01-A50) MUST have a consistent writing style across ALL their entries:
- Some always formal English, some always Marathi, some always emoji-heavy, some always SMS abbreviations, etc.
- This is critical because the privacy system must verify the model learned CONTENT not STYLE.

## Category Distribution (500 total)

### Ragging Complaints (250 sentences, mundane=0)
| Category | Count | distress | urgency | types |
|----------|-------|----------|---------|-------|
| Severe physical (slap, push, beating) | 25 | high | immediate | physical |
| Forced acts (standing, intro, dance, push-ups) | 40 | high | soon | coercion_forced_acts |
| Verbal abuse (gaali, insults, taunts) | 35 | low or high | routine or soon | verbal_abuse |
| Extortion (forced treat, money taken) | 30 | high | soon | extortion_financial |
| Social exclusion (boycott, isolation) | 20 | high | soon | exclusion_social |
| Sexual harassment (inappropriate touch, comments) | 15 | high | immediate | sexual_harassment |
| Cyber (recording video, sharing on WhatsApp) | 15 | high | immediate | cyber |
| Multiple types combined | 30 | high | soon or immediate | e.g. physical;verbal_abuse |
| Mild / tolerable ragging | 20 | low | routine | verbal_abuse or coercion_forced_acts |
| Witnessed (reporting about someone else) | 20 | high | soon | any |

### Mundane Campus Complaints (150 sentences, mundane=1, types=none, distress=none, urgency=routine)
Hard negatives — the model must NOT flag these as ragging:
- Mess/canteen food (30): "mess ka khana thanda hai", "samosa khatam ho gaya"
- Hostel facilities (30): wifi, AC, water, electricity, cleanliness
- Academic (25): lab, library, projector, attendance portal, exam schedule
- Transport (15): bus timing, parking, shuttle
- General (25): ID card, fees, gym, laundry, toilet, elevator
- Angry but NOT ragging (25): "BHAI WIFI 3 DIN SE NAHI CHAL RAHA 😡😡😡" — angry tone but mundane

### Sarcastic (50 sentences, sarcasm=1)
- 30 sarcastic ragging (mundane=0): irony describing real acts. E.g. "wow kya welcome hai, roz corridor me dance 🙏". Must have correct distress/types for the actual act.
- 20 sarcastic mundane (mundane=1): "library closes at 8 during exams?? brilliant 😂". distress=none, types=none.

### Negation / Denial (50 sentences, distress=none, urgency=routine, types=none, mundane=0, sarcasm=0)
Student DENIES ragging: "seniors ne kuch nahi kiya", "kahich zala nahi", "nothing happened", "no ragging in our hostel".

## Quality Rules
1. Every sentence unique and natural — no copy-paste patterns
2. Vary length: some 5 words, some 2-3 lines
3. Realistic details: hostel A/B/C, floor numbers, canteen, ground, lab, corridor, times (kal raat, subah 6 baje), amounts (500 rupees, 3 ghante)
4. Emotions: 😭 😡 🙏 !!! ??? "yaar" "bhai" "please help" "kya karu"
5. Both male and female students
6. First-person ("mere saath hua") and third-person ("mere roommate ke saath")
7. Multi-incident: "pehle gaali diya phir paise maange"

## Reference Examples (DO NOT repeat these)
```csv
A01,"seniors ne kal raat hostel b me 2 ghante khade rakha... intro dene ko bola bar bar... yaar thak gaya hu",high,soon,coercion_forced_acts,0,0
A02,"BHAI canteen me samosa khatam ho jata hai 11 baje!!! 😭 kuch karo!!!",none,routine,none,0,1
A06,"wow such a warm welcome from seniors?? 3 hours standing in hostel B corridor at night, great tradition hmm",high,soon,coercion_forced_acts,1,0
```

**Save the complete 500-row CSV to `data/corpus.csv`.**

---

# STEP 2: Install Dependencies

Run these commands:
```
pip install transformers torch onnx onnxruntime --quiet
```

If torch is too large, use CPU-only:
```
pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet
```

---

# STEP 3: Write and Run Training Script

Create `scripts/train_c1_local.py` — a complete training script that runs on CPU.

## Architecture

```python
class MultiHeadClassifier(nn.Module):
    def __init__(self, encoder):
        super().__init__()
        self.encoder = encoder
        h = encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.distress_head = nn.Linear(h, 3)   # none=0, low=1, high=2
        self.urgency_head = nn.Linear(h, 3)     # routine=0, soon=1, immediate=2
        self.sarcasm_head = nn.Linear(h, 2)     # 0, 1
        self.types_head = nn.Linear(h, 8)       # multi-label, 8 classes
```

## Label Encoding

```python
DISTRESS = ["none", "low", "high"]
URGENCY  = ["routine", "soon", "immediate"]
TYPES    = ["verbal_abuse", "physical", "coercion_forced_acts", "exclusion_social",
            "sexual_harassment", "extortion_financial", "cyber", "none"]
```

For types: split by semicolon → multi-hot encode against TYPES list.

## Training Config
- Encoder: `google/muril-base-cased` (supports Hindi, Marathi, English natively)
- Grouped K-Fold CV by `author` column (5 folds) — no author leaks across folds
- Learning rate: 2e-5 with linear warmup (10% of steps)
- Epochs: 6 (CPU-friendly)
- Batch size: 8 (smaller for CPU memory)
- Max sequence length: 128
- Weight decay: 0.01
- Print progress every 50 batches

## Metrics to Print
- Per-fold: macro-F1 for distress, urgency, sarcasm
- Distress F1 on sarcastic-only subset
- False-alert rate on mundane subset (should be near 0)
- Overall averages across folds

## After CV
1. Train final model on ALL data (all 500 rows)
2. Export to ONNX:
   - Save to `models/c1_onnx/model.onnx`
   - Inputs: `input_ids` (int64), `attention_mask` (int64) with dynamic axes
   - Outputs: `distress_logits`, `urgency_logits`, `sarcasm_logits`, `types_logits`
   - Opset 14
3. Save tokenizer: `tokenizer.save_pretrained("models/c1_onnx/")`
4. Save metrics to `models/c1_metrics.json`

## Run the training:
```
python scripts/train_c1_local.py --corpus data/corpus.csv --epochs 6 --batch-size 8
```

This will take ~1-2 hours on CPU. That's fine. Let it run. Print progress so we can see it's working.

---

# STEP 4: Write ONNX Inference Wrapper

Create `unsigned/pipeline/classify_c1.py`:

```python
class OnnxClassifier:
    """C1 — fine-tuned MurIL with 4 heads, exported to ONNX.
    Drop-in replacement for BaselineClassifier. Same .predict() contract."""
    
    def __init__(self, model_dir: str = "models/c1_onnx"):
        # Load ONNX session (CPU) and tokenizer
        ...
    
    def predict(self, text: str, type_threshold: float = 0.5) -> dict:
        # Tokenize → run ONNX → softmax/sigmoid → format output
        ...
```

### Return format MUST match BaselineClassifier.predict():
```python
{
    "distress": "high",                    # string from ["none", "low", "high"]
    "urgency": "soon",                     # string from ["routine", "soon", "immediate"]
    "sarcasm": "1",                        # string "0" or "1"
    "types": ["physical", "verbal_abuse"], # list of strings
    "distress_confidence": 0.92,           # float
    "urgency_confidence": 0.85,            # float
    "types_confidence": {"verbal_abuse": 0.8, ...},  # dict
    "why": {}                              # can be empty dict
}
```

### Integration is automatic — the existing code at `unsigned/pipeline/classify.py` already does:
```python
def load_classifier(model_dir="models"):
    c1 = os.path.join(model_dir, "c1_onnx")
    if os.path.isdir(c1):
        from .classify_c1 import OnnxClassifier
        return OnnxClassifier(c1)   # auto-detected!
```

---

# STEP 5: Verify

After training completes:
1. Restart the server: `python -m unsigned --port 8000 --key committee`
2. Test with these sentences and print the results:
   - "seniors ne kal raat hostel me 2 ghante khade rakha" → should be high distress
   - "mess ka khana thanda hai" → should be none distress
   - "wow kya welcome hai seniors ka, mazaa aa gaya 🙏" → should detect sarcasm + high distress
   - "seniors ne kuch nahi kiya, sab theek hai" → should be none distress (negation)
   - "BHAI WIFI NAHI CHAL RAHA 😡😡😡" → should be none distress (angry mundane)

---

# IMPORTANT NOTES

- This is a Windows machine. Use PowerShell-compatible commands.
- Project root is `c:\Users\SEBIN\Desktop\MUSA\unsigned`
- The model `google/muril-base-cased` is ~400MB download — that's fine, let it download.
- Training on CPU is expected to take 1-2 hours. That's acceptable. Don't try to speed it up by reducing quality.
- After training, the `rules.py` safety layer STILL applies on top of C1 predictions (the pipeline in `run.py` calls `apply_rules()` after classification). So rules remain as a safety net.

Execute all steps sequentially. Start with Step 1.
