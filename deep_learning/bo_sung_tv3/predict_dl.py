"""Nạp model TV3 một lần rồi gọi predict; giữ nguyên phần ứng dụng TV4."""
import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "4")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")

from pathlib import Path
import argparse
import hashlib
import json
import sys

import tensorflow as tf
from tensorflow import keras
from text_processing import unicode_lower

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "data_features/bo_sung_tv1"))
from privacy import redact


def load_model(language="vi", architecture=None):
    if language not in ("vi", "uci"):
        raise ValueError("language phải là vi hoặc uci")
    base = HERE / language
    config = json.loads((base / "model_config.json").read_text(encoding="utf-8"))
    name = architecture or config["selected"]
    if name not in config["candidates"]:
        raise ValueError("architecture phải là lstm hoặc conv1d")
    candidate = config["candidates"][name]
    path = base / candidate["model_file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != candidate["model_sha256"]:
        raise ValueError("Hash mô hình không khớp model_config.json")
    prep_path = base / "preprocessing.json"
    if hashlib.sha256(prep_path.read_bytes()).hexdigest() != config["preprocessing_sha256"]:
        raise ValueError("Hash bộ xử lý văn bản không khớp")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    standardize = unicode_lower if prep["standardize"] == "unicode_lower" else prep["standardize"]
    vectorizer = keras.layers.TextVectorization(max_tokens=prep["max_tokens"],
        standardize=standardize, split=prep["split"], output_mode="int",
        output_sequence_length=prep["sequence_length"], vocabulary=prep["vocabulary"])
    model = keras.models.load_model(path, compile=False)
    return model, vectorizer, {**candidate, "dataset_id": config["dataset_id"], "language": language}


def predict(text, loaded):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Nội dung tin nhắn không được để trống")
    model, vectorizer, config = loaded
    prepared = redact(text) if config["language"] == "vi" else text
    tokens = vectorizer(tf.constant([prepared], dtype=tf.string))
    score = float(model(tokens, training=False).numpy()[0, 0])
    return {"label": "spam" if score >= config["threshold"] else "ham",
            "score": score, "threshold": config["threshold"],
            "model_version": config["model_sha256"][:12], "architecture": config["architecture"],
            "dataset_id": config["dataset_id"], "language": config["language"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=("vi", "uci"), default="vi")
    parser.add_argument("--architecture", choices=("lstm", "conv1d"))
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    print(json.dumps(predict(args.text, load_model(args.language, args.architecture)), ensure_ascii=False, indent=2))
