# 🚀 MEGA PROMPT for Claude Opus 5 — Data + Training + Deployment

> **Copy EVERYTHING below the `---` line and paste into Claude Opus 5.**
> Opus will output 3 files: the CSV dataset, a Colab training notebook, and the inference integration code.

---

You are a senior ML engineer building the classification brain for **Unsigned**, an anonymous anti-ragging complaint system at an Indian engineering college. You must produce **3 complete deliverables** in one response:

1. **`corpus.csv`** — 500 annotated training sentences
2. **`train_colab.py`** — A complete Google Colab-ready training script
3. **`classify_c1.py`** — ONNX inference wrapper that plugs into the existing pipeline

---

# DELIVERABLE 1: corpus.csv (500 rows)

## CSV Schema

```
author,text,distress,urgency,types,sarcasm,mundane
```

- `author`: A01 to A50. Each appears 8-12 times.
- `text`: Natural student complaint typed on phone.
- `distress`: `none` | `low` | `high`
- `urgency`: `routine` | `soon` | `immediate`
- `types`: semicolon-separated from: `verbal_abuse`, `physical`, `coercion_forced_acts`, `exclusion_social`, `sexual_harassment`, `extortion_financial`, `cyber`, `none`
- `sarcasm`: `0` | `1`
- `mundane`: `0` | `1`

## Language Distribution

- **40% Hinglish** (Roman script): "bhai seniors ne raat ko khade rakha"
- **25% Marathi-English** (Roman): "hostel madhe seniors ni mala ubha kela"
- **20% Formal English**: "Sir, I wish to report that..."
- **10% SMS-style**: "srs ne kal rat 3 hrs khda rkha 😭😭"
- **5% Pure Marathi (Roman)**: "kal ratri hostel madhe khup traas dila"

## Author Consistency

Each author has ONE consistent style (some always formal, some always emoji-heavy, some Marathi, etc.). The model must learn CONTENT not STYLE.

## Category Distribution (500 total)

### Ragging (250 sentences, mundane=0)
| Category | Count | distress | urgency | types |
|----------|-------|----------|---------|-------|
| Severe physical | 25 | high | immediate | physical |
| Forced acts | 40 | high | soon | coercion_forced_acts |
| Verbal abuse | 35 | low/high | routine/soon | verbal_abuse |
| Extortion | 30 | high | soon | extortion_financial |
| Social exclusion | 20 | high | soon | exclusion_social |
| Sexual harassment | 15 | high | immediate | sexual_harassment |
| Cyber | 15 | high | immediate | cyber |
| Multi-type | 30 | high | soon/immediate | e.g. physical;verbal_abuse |
| Mild ragging | 20 | low | routine | verbal_abuse or coercion_forced_acts |
| Witnessed | 20 | high | soon | any |

### Mundane (150 sentences, mundane=1, types=none, distress=none, urgency=routine)
Food/mess (30), hostel facilities (30), academic (25), transport (15), general (25), angry-but-not-ragging (25).
Some MUST be written angrily: "BHAI WIFI 3 DIN SE NAHI CHAL RAHA 😡😡😡" — still mundane.

### Sarcastic (50 sentences, sarcasm=1)
- 30 sarcastic ragging (mundane=0, with proper distress/types)
- 20 sarcastic mundane (mundane=1, distress=none, types=none)

### Negation (50 sentences, distress=none, urgency=routine, types=none, mundane=0, sarcasm=0)
Student DENIES ragging: "seniors ne kuch nahi kiya", "kahich zala nahi", "nothing happened"

## Quality Rules
- Every sentence unique, realistic, natural
- Varied lengths (3 words to 3 lines)
- Real details: hostel A/B/C, floors, canteen, ground, lab, corridor, times, amounts
- Emotions: 😭 😡 🙏 !!! ??? "yaar" "bhai" "please help"
- Both genders reporting
- First-person and third-person reports
- Multi-incident: "pehle gaali diya phir paise maange"

---

# DELIVERABLE 2: train_colab.py (Google Colab Training Script)

Write a complete, runnable Python script for Google Colab that:

## Setup
```python
# Cell 1: Install dependencies
# !pip install transformers datasets onnx onnxruntime accelerate -q
```

## Requirements
1. **Load corpus.csv** (uploaded to Colab)
2. **Encoder**: Use `google/muril-base-cased` (supports Hindi, Marathi, English natively). Also support `l3cube-pune/hing-roberta` as alternate.
3. **4 classification heads** on top of the [CLS] token:
   - `distress`: 3-class (none=0, low=1, high=2)
   - `urgency`: 3-class (routine=0, soon=1, immediate=2)
   - `sarcasm`: 2-class (0, 1)
   - `types`: multi-label binary (8 classes, BCEWithLogitsLoss)
4. **Grouped K-Fold CV** by `author` column (5 folds). No author's data leaks across train/test.
5. **Training config**:
   - Learning rate: 2e-5 with linear warmup (10% of steps)
   - Epochs: 8
   - Batch size: 16
   - Max sequence length: 128
   - Weight decay: 0.01
   - Mixed precision (fp16) if GPU available
6. **Print metrics per fold**: macro-F1 for distress, urgency, sarcasm. Also print distress F1 on sarcastic-only subset and false-alert rate on mundane subset.
7. **After CV, train final model on ALL data**.
8. **Export to ONNX**:
   - Export the encoder + heads as a single ONNX model
   - Input: `input_ids` (int64), `attention_mask` (int64)
   - Outputs: `distress_logits`, `urgency_logits`, `sarcasm_logits`, `types_logits`
   - Opset 14, dynamic axes for batch_size and sequence_length
   - Save as `c1_onnx/model.onnx`
   - Also save the tokenizer to `c1_onnx/` using `tokenizer.save_pretrained("c1_onnx")`
9. **Save metrics** to `c1_metrics.json`
10. **Zip the output** folder for download: `!zip -r c1_onnx.zip c1_onnx/`

## Model Architecture

```python
class MultiHeadClassifier(torch.nn.Module):
    def __init__(self, encoder, n_types=8):
        super().__init__()
        self.encoder = encoder
        h = encoder.config.hidden_size
        self.dropout = torch.nn.Dropout(0.1)
        self.distress_head = torch.nn.Linear(h, 3)
        self.urgency_head = torch.nn.Linear(h, 3)
        self.sarcasm_head = torch.nn.Linear(h, 2)
        self.types_head = torch.nn.Linear(h, n_types)

    def forward(self, input_ids, attention_mask):
        cls = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0]
        cls = self.dropout(cls)
        return (self.distress_head(cls), self.urgency_head(cls),
                self.sarcasm_head(cls), self.types_head(cls))
```

## Label Encoding

```python
DISTRESS = ["none", "low", "high"]    # map to 0, 1, 2
URGENCY  = ["routine", "soon", "immediate"]  # map to 0, 1, 2
TYPES    = ["verbal_abuse", "physical", "coercion_forced_acts", "exclusion_social",
            "sexual_harassment", "extortion_financial", "cyber", "none"]
```

For types: split by semicolon, multi-hot encode against the TYPES list.

---

# DELIVERABLE 3: classify_c1.py (ONNX Inference for Production)

Write a Python module `classify_c1.py` that:

1. **Loads the ONNX model** from a directory (default `models/c1_onnx/`)
2. **Has the same `.predict(text)` interface** as the existing BaselineClassifier:

```python
class OnnxClassifier:
    """C1 — fine-tuned MurIL/HingRoBERTa with 4 heads, exported to ONNX.
    
    Drop-in replacement for BaselineClassifier. Same .predict() contract.
    Requires: pip install onnxruntime transformers
    """
    def __init__(self, model_dir: str = "models/c1_onnx"):
        ...  # load ONNX session + tokenizer
    
    def predict(self, text: str, type_threshold: float = 0.5) -> dict:
        """Return dict with keys: distress, urgency, sarcasm, types,
        distress_confidence, urgency_confidence, types_confidence, why."""
        ...
```

3. **Return format** must match BaselineClassifier.predict():
```python
{
    "distress": "high",           # string
    "urgency": "soon",            # string  
    "sarcasm": "1",               # string "0" or "1"
    "types": ["physical", "verbal_abuse"],  # list of strings
    "distress_confidence": 0.92,  # float
    "urgency_confidence": 0.85,   # float
    "types_confidence": {"verbal_abuse": 0.8, "physical": 0.9, ...},  # dict
    "why": {"distress": [...], "urgency": [...]}  # top contributing tokens (optional, can be empty lists)
}
```

4. Uses `onnxruntime.InferenceSession` (CPU provider by default)
5. Uses `AutoTokenizer.from_pretrained(model_dir)` for tokenization
6. Applies softmax to get confidence scores
7. For types: sigmoid on logits, threshold at `type_threshold`

## Integration Point

The existing system at `unsigned/pipeline/classify.py` already has this code that will auto-detect C1:

```python
def load_classifier(model_dir: str = "models") -> BaselineClassifier:
    c1 = os.path.join(model_dir, "c1_onnx")
    if os.path.isdir(c1):
        try:
            from .classify_c1 import OnnxClassifier
            return OnnxClassifier(c1)     # same .predict() contract
        except Exception:
            pass
    c0 = os.path.join(model_dir, "c0.joblib")
    if os.path.exists(c0):
        return BaselineClassifier.load(c0)
```

So `classify_c1.py` goes into `unsigned/pipeline/classify_c1.py` and it will be auto-loaded.

---

# OUTPUT FORMAT

Output all 3 deliverables in this exact format:

```
===== FILE: corpus.csv =====
author,text,distress,urgency,types,sarcasm,mundane
A01,"seniors ne kal raat...",high,soon,coercion_forced_acts,0,0
... (500 rows)

===== FILE: train_colab.py =====
"""Google Colab training script for Unsigned C1 classifier."""
... (complete Python script)

===== FILE: classify_c1.py =====
"""C1 — ONNX inference wrapper for the fine-tuned encoder."""
... (complete Python module)
```

**DO NOT add markdown code fences around the files. Just the raw content between the ===== markers.**

Begin generating all 3 deliverables now.
