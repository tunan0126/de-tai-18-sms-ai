"""Chuẩn hóa dùng chung khi học vocabulary và khi nạp lại model TV3."""
import tensorflow as tf


def unicode_lower(text):
    return tf.strings.lower(text, encoding="utf-8")
