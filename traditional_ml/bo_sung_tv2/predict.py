"""Bộ nạp dành cho TV4. Gọi load_model một lần lúc ứng dụng khởi động."""
from pathlib import Path
import argparse
import json
import sys

import joblib
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "traditional_ml/TV2_hoc_may"))
sys.path.insert(0, str(ROOT / "data_features/bo_sung_tv1"))
from privacy import redact


def load_model(language="vi"):
    if language not in ("vi", "uci"):
        raise ValueError("language phải là vi hoặc uci")
    base = HERE / language
    model = joblib.load(base / "model/model.joblib")
    config = json.loads((base / "model/config.json").read_text(encoding="utf-8"))
    version = json.loads((base / "version.json").read_text(encoding="utf-8"))
    return model, float(config["nguong"]), version


def predict(text, loaded):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Nội dung tin nhắn không được để trống")
    model, threshold, version = loaded
    prepared = redact(text) if version["language"] == "vi" else text
    classes = list(model.classes_)
    score = float(np.round(model.predict_proba([prepared])[0, classes.index(1)],
                           version.get("score_decimals", 12)))
    return {"label": "spam" if score >= threshold else "ham", "score": score,
            "threshold": threshold, "model_version": version["model_sha256"][:12],
            "dataset_id": version["dataset_id"], "language": version["language"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--language", choices=("vi", "uci"), default="vi")
    args = parser.parse_args()
    print(json.dumps(predict(args.text, load_model(args.language)), ensure_ascii=False, indent=2))
