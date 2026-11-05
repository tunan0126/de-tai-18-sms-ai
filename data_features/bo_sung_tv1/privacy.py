"""Quy tắc che thông tin cho bản dữ liệu bổ sung; không thay đổi dữ liệu cũ."""
import re
import unicodedata

VERSION = "vi-redaction-v1"
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\w)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\w)")
LONG_NUMBER = re.compile(r"(?<!\w)\d{4,}(?!\w)")


def redact(text):
    """Giữ chữ hoa/dấu câu; che email, số điện thoại và dãy số >= 4 chữ số.

    Không suy đoán tên riêng hay đổi nhãn. Tên tự do cần chủ nguồn rà lại.
    """
    if not isinstance(text, str):
        raise TypeError("Tin nhắn phải là chuỗi")
    text = unicodedata.normalize("NFC", text)
    text = EMAIL.sub("[EMAIL]", text)
    text = re.sub(r"(https?://[^\s?#]+)[?#][^\s]+", r"\1?[REDACTED]", text, flags=re.I)
    text = PHONE.sub("[PHONE]", text)
    text = LONG_NUMBER.sub("[NUMBER]", text)
    return re.sub(r"\s+", " ", text).strip()


def remaining_identifiers(text):
    return bool(EMAIL.search(text) or PHONE.search(text) or LONG_NUMBER.search(text))
