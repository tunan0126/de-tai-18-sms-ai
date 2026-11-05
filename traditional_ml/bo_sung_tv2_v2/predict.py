from pathlib import Path
import hashlib,json,sys
import joblib
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'data_features/bo_sung_tv1_v2'))
import vi_text_v2


def load_model(language='vi'):
    if language!='vi':raise ValueError('Gói v2 này chỉ dành cho tiếng Việt')
    version=json.loads((HERE/'version.json').read_text(encoding='utf-8'))
    config=json.loads((HERE/'config.json').read_text(encoding='utf-8'))
    if hashlib.sha256((HERE/'model.joblib').read_bytes()).hexdigest()!=version['model_sha256']:raise ValueError('Hash ML v2 không khớp')
    if hashlib.sha256((ROOT/'data_features/bo_sung_tv1_v2/vi_text_v2.py').read_bytes()).hexdigest()!=version['normalizer_sha256']:raise ValueError('Normalizer v2 đã thay đổi')
    return joblib.load(HERE/'model.joblib'),config['threshold'],version


def predict(text,loaded):
    if not isinstance(text,str) or not text.strip():raise ValueError('Nội dung không được trống')
    model,threshold,version=loaded
    score=float(np.round(model.predict_proba([text])[0,list(model.classes_).index(1)],12))
    return dict(label='spam' if score>=threshold else 'ham',score=score,threshold=threshold,
                model_version=version['model_sha256'][:12],dataset_id=version['dataset_id'],language='vi',
                architecture=version['architecture'],model_origin='tv1_4_v2')
