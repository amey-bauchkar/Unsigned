import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
import torch
import torch.nn as nn
from transformers import AutoModel, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from unsigned.pipeline.card import TYPES


class MultiHeadClassifier(nn.Module):
    def __init__(self, encoder):
        super().__init__()
        self.encoder = encoder
        h = encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.distress_head = nn.Linear(h, 3)
        self.urgency_head = nn.Linear(h, 3)
        self.sarcasm_head = nn.Linear(h, 2)
        self.types_head = nn.Linear(h, len(TYPES))

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls = self.dropout(out.last_hidden_state[:, 0])
        return (self.distress_head(cls), self.urgency_head(cls),
                self.sarcasm_head(cls), self.types_head(cls))


def main():
    model_dir = os.path.join(ROOT, "models", "c1_onnx")
    pt_path = os.path.join(model_dir, "model.pt")
    onnx_path = os.path.join(model_dir, "model.onnx")

    print("Loading base encoder...")
    encoder = AutoModel.from_pretrained("google/muril-base-cased")
    model = MultiHeadClassifier(encoder)
    print(f"Loading weights from {pt_path}...")
    model.load_state_dict(torch.load(pt_path, map_location="cpu"))
    model.eval()

    tok = AutoTokenizer.from_pretrained(model_dir)
    dummy = tok("test sentence", return_tensors="pt", padding=True, truncation=True, max_length=128)

    print("Exporting to ONNX...")
    torch.onnx.export(
        model,
        (dummy["input_ids"], dummy["attention_mask"]),
        onnx_path,
        input_names=["input_ids", "attention_mask"],
        output_names=["distress_logits", "urgency_logits", "sarcasm_logits", "types_logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "distress_logits": {0: "batch"},
            "urgency_logits": {0: "batch"},
            "sarcasm_logits": {0: "batch"},
            "types_logits": {0: "batch"},
        },
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,
    )
    print(f"SUCCESS: Exported ONNX model to {onnx_path}")


if __name__ == "__main__":
    main()
