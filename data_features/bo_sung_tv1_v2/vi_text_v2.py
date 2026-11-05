"""Chuẩn hóa dùng chung TV1-TV4 v2; không phải luật phân loại spam."""
from pathlib import Path
import sys
import unicodedata
import re

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bo_sung_tv1'))
from privacy import redact

VERSION='vi-nfc-redact-accentfold-v2'


def normalize(text):
    if not isinstance(text,str):raise TypeError('Nội dung phải là chuỗi')
    text=redact(text).casefold().replace('đ','d')
    text=''.join(c for c in unicodedata.normalize('NFD',text) if unicodedata.category(c)!='Mn')
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',text)).strip()


def normalize_many(texts):return [normalize(text) for text in texts]
