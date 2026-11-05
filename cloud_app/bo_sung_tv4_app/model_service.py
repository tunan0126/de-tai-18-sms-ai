"""Adapter TV4: giữ gói TV2/TV3; bản sửa Việt được lưu riêng và khóa bằng hash."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import joblib

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS', '2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS', '1')
ROOT = Path(__file__).resolve().parents[2]
REVISION = Path(__file__).resolve().parent / 'vi_model_revision'
TV1 = ROOT / 'data_features/bo_sung_tv1'
sys.path.insert(0, str(TV1))
from privacy import redact


def match_sha256(path, expected):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() == expected:
        return True
    norm_lf = data.replace(b'\r\n', b'\n')
    if hashlib.sha256(norm_lf).hexdigest() == expected:
        return True
    crlf = norm_lf.replace(b'\n', b'\r\n')
    return hashlib.sha256(crlf).hexdigest() == expected


def import_loader(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModelService:
    def __init__(self):
        self.cache = {}
        self.lock = threading.RLock()
        self.loaders = {}
        path = REVISION / 'active.json'
        self.revision = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        path=Path(__file__).resolve().parent/'release_v2.json'
        self.v2=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

    def uses_v2(self, model, language):
        return language=='vi' and bool(self.v2 and model in self.v2)

    def loader_for(self,model,language):
        if self.uses_v2(model,language):
            key=model+'_vi_v2'
            if key not in self.loaders:
                base=ROOT/('traditional_ml/bo_sung_tv2_v2' if model=='ml' else 'deep_learning/bo_sung_tv3_v2')
                self.loaders[key]=import_loader('tv4_'+key,base/'predict.py')
            return self.loaders[key]
        if model not in self.loaders:
            path=ROOT/('traditional_ml/bo_sung_tv2/predict.py' if model=='ml' else 'deep_learning/bo_sung_tv3/predict_dl.py')
            self.loaders[model]=import_loader('tv4_'+model+'_loader',path)
        return self.loaders[model]

    def revised(self, model, language):
        return language == 'vi' and model in self.revision

    def load(self, model, language):
        with self.lock:
            key = (model, language)
            if key not in self.cache:
                if self.uses_v2(model,language):
                    base=ROOT/('traditional_ml/bo_sung_tv2_v2' if model=='ml' else 'deep_learning/bo_sung_tv3_v2')
                    paths={'ml':base/'config.json','dl':base/'model_config.json'}
                    if not match_sha256(paths[model], self.v2[model]['config_sha256']):
                        raise ValueError('Config v2 không khớp snapshot triển khai')
                    for name,digest in self.v2[model]['runtime_hashes'].items():
                        if not match_sha256(ROOT/name, digest):
                            raise ValueError('Artifact/phụ thuộc v2 không khớp snapshot triển khai')
                    self.cache[key]=self.loader_for(model,language).load_model(language)
                    return self.cache[key]
                if model not in self.loaders:
                    path = ROOT / ('traditional_ml/bo_sung_tv2/predict.py' if model == 'ml'
                                   else 'deep_learning/bo_sung_tv3/predict_dl.py')
                    self.loaders[model] = import_loader('tv4_' + model + '_loader', path)
                if model == 'ml':
                    base = REVISION if self.revised(model, language) else ROOT / 'traditional_ml/bo_sung_tv2' / language
                    version = json.loads((base / 'version.json').read_text(encoding='utf-8'))
                    model_path = base / ('model.joblib' if self.revised(model, language) else 'model/model.joblib')
                    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
                    if digest != version['model_sha256']:
                        raise ValueError('Hash model ML không khớp phiên bản')
                    if self.revised(model, language):
                        if digest != self.revision['ml']['model_sha256'] or not match_sha256(base/'config.json', self.revision['ml']['config_sha256']):
                            raise ValueError('Bản sửa ML chưa khớp phiên bản triển khai')
                        config=json.loads((base/'config.json').read_text(encoding='utf-8'))
                        self.cache[key]=(joblib.load(model_path),float(config['nguong']),version)
                elif self.revised(model, language):
                    base=REVISION/'dl'
                    config_path=base/'model_config.json'
                    if not match_sha256(config_path, self.revision['dl']['config_sha256']):
                        raise ValueError('Bản sửa DL chưa khớp phiên bản triển khai')
                    config=json.loads(config_path.read_text(encoding='utf-8'))
                    prep_path=base/'preprocessing.json'
                    if not match_sha256(prep_path, config['preprocessing_sha256']):
                        raise ValueError('Bộ xử lý DL sửa không khớp hash')
                    prep=json.loads(prep_path.read_text(encoding='utf-8'))
                    candidate=config['candidates'][config['selected']]
                    model_path=base/candidate['model_file']
                    if not match_sha256(model_path, candidate['model_sha256']):
                        raise ValueError('Model DL sửa không khớp hash')
                    module=self.loaders['dl']
                    vectorizer=module.keras.layers.TextVectorization(max_tokens=prep['max_tokens'],standardize=module.unicode_lower,
                        split=prep['split'],output_mode='int',output_sequence_length=prep['sequence_length'],vocabulary=prep['vocabulary'])
                    self.cache[key]=(module.keras.models.load_model(model_path,compile=False),vectorizer,
                        {**candidate,'dataset_id':config['dataset_id'],'language':'vi','model_origin':'tv4_vi_revision'})
                if key not in self.cache:
                    self.cache[key] = self.loaders[model].load_model(language)
            return self.cache[key]

    def predict(self, text, model, language):
        # Một tiến trình/một hàng đợi suy luận cho demo CPU; không chia sẻ loader đang khởi tạo.
        with self.lock:
            loaded = self.load(model, language)
            loader=self.loader_for(model,language)
            result = loader.predict(text, loaded)
            result.update(model=model, truncated=False, input_tokens=None, sequence_length=None)
            result['model_origin']='tv1_4_v2' if self.uses_v2(model,language) else 'tv4_vi_revision' if self.revised(model,language) else 'tv2' if model=='ml' else 'tv3'
            if model == 'dl':
                prepared = redact(text) if language == 'vi' else text
                tf = loader.tf
                if self.uses_v2(model,language) and loaded[1].get_config().get('split')=='character':
                    length=len(loader.normalize(text))
                else:
                    length = int(tf.strings.split(tf.constant([prepared])).row_lengths()[0])
                limit = loaded[1].get_config()['output_sequence_length']
                result.update(truncated=length > limit, input_tokens=length, sequence_length=limit)
            return result

    def warmup(self):
        for language in ('vi', 'uci'):
            for model in ('ml', 'dl'):
                self.predict('Tin mẫu khởi động.' if language == 'vi' else 'Startup message.', model, language)

    def describe(self):
        rows = []
        for language in ('vi', 'uci'):
            if self.uses_v2('ml',language):
                base=ROOT/'traditional_ml/bo_sung_tv2_v2'
                version=json.loads((base/'version.json').read_text(encoding='utf-8'))
                config=json.loads((base/'config.json').read_text(encoding='utf-8'))
                rows.append(dict(model='ml',language='vi',architecture=version['architecture'],representation=version['representation'],
                    model_version=version['model_sha256'][:12],threshold=config['threshold'],dataset_id=version['dataset_id'],model_origin='tv1_4_v2'))
                rows.append(self.describe_dl(language))
                continue
            revised=self.revised('ml',language)
            base = REVISION if revised else ROOT / 'traditional_ml/bo_sung_tv2' / language
            version = json.loads((base / 'version.json').read_text(encoding='utf-8'))
            report = json.loads((base / ('report.json' if revised else 'results/ket_qua_cuoi.json')).read_text(encoding='utf-8'))
            config = json.loads((base / ('config.json' if revised else 'model/config.json')).read_text(encoding='utf-8'))
            rows.append(dict(model='ml', language=language, architecture=version['architecture'] if revised else report['cau_hinh_chon']['model'],
                             representation=version['representation'] if revised else report['cau_hinh_chon']['vector'],
                             model_origin='tv4_vi_revision' if revised else 'tv2',
                             model_version=version['model_sha256'][:12], threshold=config['nguong'],
                             dataset_id=version['dataset_id']))
            rows.append(self.describe_dl(language))
        return rows

    def describe_dl(self, language):
        if self.uses_v2('dl',language):
            base=ROOT/'deep_learning/bo_sung_tv3_v2';origin='tv1_4_v2'
        else:
            base=REVISION/'dl' if self.revised('dl',language) else ROOT/'deep_learning/bo_sung_tv3'/language
            origin='tv4_vi_revision' if self.revised('dl',language) else 'tv3'
        config=json.loads((base/'model_config.json').read_text(encoding='utf-8'))
        item=config['candidates'][config['selected']]
        return dict(model='dl',language=language,architecture=item['architecture'],model_origin=origin,
                    model_version=item['model_sha256'][:12],threshold=item['threshold'],dataset_id=config['dataset_id'])
