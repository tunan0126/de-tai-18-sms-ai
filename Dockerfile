FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8080 TV4_DATABASE=/tmp/tv4.sqlite3
WORKDIR /app
COPY cloud_app/bo_sung_tv4_app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
# Chỉ copy runtime và artifact cần suy luận; không copy dữ liệu train, venv, tài khoản hay DB máy người dùng.
COPY cloud_app/bo_sung_tv4_app/app.py cloud_app/bo_sung_tv4_app/model_service.py cloud_app/bo_sung_tv4_app/manage.py /app/cloud_app/bo_sung_tv4_app/
COPY cloud_app/bo_sung_tv4_app/static/ /app/cloud_app/bo_sung_tv4_app/static/
COPY cloud_app/bo_sung_tv4_app/vi_model_revision/active.json cloud_app/bo_sung_tv4_app/vi_model_revision/model.joblib cloud_app/bo_sung_tv4_app/vi_model_revision/config.json cloud_app/bo_sung_tv4_app/vi_model_revision/version.json cloud_app/bo_sung_tv4_app/vi_model_revision/report.json /app/cloud_app/bo_sung_tv4_app/vi_model_revision/
COPY cloud_app/bo_sung_tv4_app/vi_model_revision/dl/model_config.json cloud_app/bo_sung_tv4_app/vi_model_revision/dl/preprocessing.json /app/cloud_app/bo_sung_tv4_app/vi_model_revision/dl/
COPY cloud_app/bo_sung_tv4_app/vi_model_revision/dl/models/ /app/cloud_app/bo_sung_tv4_app/vi_model_revision/dl/models/
COPY data_features/bo_sung_tv1/privacy.py /app/data_features/bo_sung_tv1/privacy.py
COPY data_features/bo_sung_tv1_v2/vi_text_v2.py /app/data_features/bo_sung_tv1_v2/vi_text_v2.py
COPY cloud_app/bo_sung_tv4_app/release_v2.json /app/cloud_app/bo_sung_tv4_app/release_v2.json
COPY traditional_ml/bo_sung_tv2_v2/predict.py traditional_ml/bo_sung_tv2_v2/model.joblib traditional_ml/bo_sung_tv2_v2/config.json traditional_ml/bo_sung_tv2_v2/version.json traditional_ml/bo_sung_tv2_v2/report.json /app/traditional_ml/bo_sung_tv2_v2/
COPY traditional_ml/TV2_hoc_may/features_regex.py /app/traditional_ml/TV2_hoc_may/features_regex.py
COPY traditional_ml/bo_sung_tv2/predict.py /app/traditional_ml/bo_sung_tv2/predict.py
COPY traditional_ml/bo_sung_tv2/vi/model/ /app/traditional_ml/bo_sung_tv2/vi/model/
COPY traditional_ml/bo_sung_tv2/vi/version.json /app/traditional_ml/bo_sung_tv2/vi/version.json
COPY traditional_ml/bo_sung_tv2/vi/results/ket_qua_cuoi.json /app/traditional_ml/bo_sung_tv2/vi/results/ket_qua_cuoi.json
COPY traditional_ml/bo_sung_tv2/uci/model/ /app/traditional_ml/bo_sung_tv2/uci/model/
COPY traditional_ml/bo_sung_tv2/uci/version.json /app/traditional_ml/bo_sung_tv2/uci/version.json
COPY traditional_ml/bo_sung_tv2/uci/results/ket_qua_cuoi.json /app/traditional_ml/bo_sung_tv2/uci/results/ket_qua_cuoi.json
COPY deep_learning/bo_sung_tv3/predict_dl.py deep_learning/bo_sung_tv3/text_processing.py /app/deep_learning/bo_sung_tv3/
COPY deep_learning/bo_sung_tv3/vi/models/ /app/deep_learning/bo_sung_tv3/vi/models/
COPY deep_learning/bo_sung_tv3/vi/model_config.json deep_learning/bo_sung_tv3/vi/preprocessing.json /app/deep_learning/bo_sung_tv3/vi/
COPY deep_learning/bo_sung_tv3/uci/models/ /app/deep_learning/bo_sung_tv3/uci/models/
COPY deep_learning/bo_sung_tv3/uci/model_config.json deep_learning/bo_sung_tv3/uci/preprocessing.json /app/deep_learning/bo_sung_tv3/uci/
RUN mkdir -p /tmp && chmod 777 /tmp
EXPOSE 8080
HEALTHCHECK --start-period=90s --interval=30s --timeout=5s CMD python -c "import urllib.request, os; p = os.environ.get('PORT', '8080'); urllib.request.urlopen('http://127.0.0.1:' + p + '/api/health', timeout=4)"
CMD ["python", "cloud_app/bo_sung_tv4_app/app.py"]
