"""Ứng dụng TV4: API cùng origin, phiên server-side và dữ liệu theo chủ tài khoản."""
from datetime import datetime, timezone
from contextlib import closing
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import unicodedata
from urllib.parse import urlsplit
import uuid

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from model_service import ModelService, redact

HERE = Path(__file__).resolve().parent
COOKIE = 'tv4_session'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
 display_name TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL,
 user_id TEXT REFERENCES users(id), expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 text_redacted TEXT, sender_display TEXT, keep_history INTEGER NOT NULL,
 result TEXT NOT NULL, created_at TEXT NOT NULL, request_key TEXT NOT NULL, input_digest TEXT NOT NULL,
 UNIQUE(user_id,request_key));
CREATE INDEX IF NOT EXISTS predictions_owner ON predictions(user_id, keep_history, created_at);
CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 sender_key TEXT NOT NULL, sender_display TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN ('block','allow')),
 version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, UNIQUE(user_id,sender_key));
CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 prediction_id TEXT NOT NULL REFERENCES predictions(id), proposed_label TEXT NOT NULL,
 note TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id,prediction_id));
CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY, window REAL NOT NULL, count INTEGER NOT NULL);
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def sender_key(value):
    # Số điện thoại có/không có dấu cách phải khớp cùng luật; không suy đoán mã quốc gia.
    value = unicodedata.normalize('NFC', value).strip().casefold()
    if re.fullmatch(r'[+\d\s().-]+', value):
        value = re.sub(r'[\s().-]', '', value)
    return digest(value)


class ApiError(Exception):
    def __init__(self, message, status=400, **extra):
        self.message, self.status, self.extra = message, status, extra


def create_app(config=None, model_service=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    origin = os.environ.get('APP_ORIGIN', '').rstrip('/')
    allowed = os.environ.get('ALLOWED_HOSTS')
    if allowed:
        hosts = [h.strip() for h in allowed.split(',') if h.strip()]
        if origin and urlsplit(origin).hostname:
            hosts.append(urlsplit(origin).hostname)
        trusted = hosts
    else:
        trusted = None
    app.config.update(DATABASE=os.environ.get('TV4_DATABASE', str(HERE / 'instance/tv4.sqlite3')),
                      COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
                      APP_ORIGIN=origin, MAX_CONTENT_LENGTH=20000, TRUSTED_HOSTS=trusted,
                      ALLOW_REGISTRATION=os.environ.get('ALLOW_REGISTRATION', '1') == '1',
                      SESSION_TTL=8*3600, RATE_LIMITS=True)
    if config:
        app.config.update(config)
    db_path = Path(app.config['DATABASE'])
    db_path.parent.mkdir(exist_ok=True, parents=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript(SCHEMA)
        if not conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            demo_users = [
                (uuid.uuid4().hex, 'admin', 'Quản trị viên', generate_password_hash('Admin@123456'), now()),
                (uuid.uuid4().hex, 'demo_a', 'Tài khoản A', generate_password_hash('Demo@123456'), now()),
                (uuid.uuid4().hex, 'demo_b', 'Tài khoản B', generate_password_hash('Demo@123456'), now()),
            ]
            conn.executemany('INSERT INTO users VALUES(?,?,?,?,?)', demo_users)
            conn.commit()
    service = model_service or ModelService()
    app.extensions['models'] = service
    dummy_hash = generate_password_hash('invalid-account-' + secrets.token_hex(12))

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'], timeout=15)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close_db(error=None):
        if 'db' in g:
            g.db.close()

    def body():
        if not request.is_json:
            raise ApiError('Yêu cầu phải có Content-Type application/json.', 415)
        data = request.get_json()
        if not isinstance(data, dict):
            raise ApiError('Nội dung JSON phải là một object.')
        return data

    def field(data, key, maximum, minimum=0):
        value = data.get(key, '')
        if not isinstance(value, str):
            raise ApiError(f'{key} phải là chuỗi.')
        value = unicodedata.normalize('NFC', value).strip()
        if not minimum <= len(value) <= maximum or '\x00' in value:
            raise ApiError(f'{key}: cần từ {minimum} đến {maximum} ký tự.')
        return value

    def limited(key, count, seconds):
        if not app.config['RATE_LIMITS']:
            return
        stamp = int(time.time() // seconds) * seconds
        with db() as conn:
            conn.execute('INSERT INTO rate_limits(key,window,count) VALUES(?,?,1) '
                         'ON CONFLICT(key) DO UPDATE SET window=excluded.window, '
                         'count=CASE WHEN rate_limits.window=excluded.window THEN rate_limits.count+1 ELSE 1 END',
                         (key, stamp))
            used = conn.execute('SELECT count FROM rate_limits WHERE key=?', (key,)).fetchone()[0]
        if used > count:
            raise ApiError('Thao tác quá nhanh. Vui lòng chờ rồi thử lại.', 429)

    def current_session():
        token = request.cookies.get(COOKIE, '')
        if not token or len(token) > 128:
            return None
        return db().execute('SELECT s.*,u.username,u.display_name FROM sessions s '
                            'LEFT JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires_at>?',
                            (digest(token), time.time())).fetchone()

    def session_response(user_id=None, status=200):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with db() as conn:
            conn.execute('DELETE FROM sessions WHERE expires_at<?', (time.time(),))
            conn.execute('DELETE FROM rate_limits WHERE window<?', (time.time()-86400,))
            if request.cookies.get(COOKIE):
                conn.execute('DELETE FROM sessions WHERE token_hash=?', (digest(request.cookies[COOKIE]),))
            conn.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                         (digest(token), csrf, user_id, time.time()+app.config['SESSION_TTL']))
        user = db().execute('SELECT id,username,display_name FROM users WHERE id=?', (user_id,)).fetchone()
        response = jsonify(user=dict(user) if user else None, csrf=csrf,
                           registration_enabled=app.config['ALLOW_REGISTRATION'])
        response.status_code = status
        secure_flag = app.config['COOKIE_SECURE'] or request.is_secure
        response.set_cookie(COOKIE, token, httponly=True, secure=secure_flag,
                            samesite='Lax', max_age=app.config['SESSION_TTL'], path='/')
        return response

    def login_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            session = current_session()
            if not session or not session['user_id']:
                raise ApiError('Phiên đã hết hạn. Vui lòng đăng nhập.', 401)
            g.user_id = session['user_id']
            return fn(*args, **kwargs)
        return wrapped

    @app.before_request
    def protect_mutations():
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return
        origin_header = request.headers.get('Origin')
        expected = app.config['APP_ORIGIN'] or request.host_url.rstrip('/')
        if origin_header and origin_header != expected and not origin_header.endswith('.onrender.com'):
            raise ApiError('Origin không hợp lệ.', 403)
        session = current_session()
        csrf = request.headers.get('X-CSRF-Token', '')
        if not session:
            raise ApiError('Phiên đã hết hạn. Tải lại trang hoặc đăng nhập.', 401)
        if not secrets.compare_digest(session['csrf'], csrf):
            raise ApiError('Mã xác nhận phiên không hợp lệ. Tải lại trang.', 403)

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if app.config['COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(ApiError)
    def api_error(error):
        return jsonify(error=error.message, **error.extra), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {400:'Dữ liệu yêu cầu không hợp lệ.', 404:'Không tìm thấy dữ liệu.',
                    413:'Yêu cầu quá lớn.', 405:'Phương thức không được hỗ trợ.'}
        return jsonify(error=messages.get(error.code, 'Không thể xử lý yêu cầu.')), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        # Chỉ log tên lỗi, không ghi request/SMS/password hoặc traceback có dữ liệu.
        app.logger.error('TV4 request failed: %s', type(error).__name__)
        return jsonify(error='Dịch vụ gặp lỗi. Dữ liệu đã nhập được giữ trên màn hình; hãy thử lại.'), 503

    @app.get('/')
    def index():
        return send_from_directory(HERE / 'static', 'index.html')

    @app.get('/api/health')
    def health():
        db().execute('SELECT 1').fetchone()
        return jsonify(status='ok', application='tv4', model_integration='real')

    @app.get('/api/session')
    def get_session():
        session = current_session()
        if not session:
            return session_response()
        return jsonify(user={key:session[key] for key in ('username','display_name')} if session['user_id'] else None,
                       csrf=session['csrf'], registration_enabled=app.config['ALLOW_REGISTRATION'])

    @app.post('/api/register')
    def register():
        if not app.config['ALLOW_REGISTRATION']:
            raise ApiError('Đăng ký đang tắt. Liên hệ người quản lý demo.', 403)
        limited('register:' + digest(request.remote_addr or ''), 10, 3600)
        data = body()
        username = field(data, 'username', 32, 3).lower()
        if not re.fullmatch(r'[a-z0-9_.-]{3,32}', username):
            raise ApiError('Tên đăng nhập dùng 3-32 ký tự a-z, 0-9, dấu _, . hoặc -.')
        display_name = field(data, 'display_name', 60, 1)
        password = data.get('password')
        if not isinstance(password, str) or not 10 <= len(password) <= 128:
            raise ApiError('Mật khẩu cần 10-128 ký tự; không dùng mật khẩu của dịch vụ khác.')
        uid = uuid.uuid4().hex
        try:
            with db() as conn:
                conn.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                             (uid, username, display_name, generate_password_hash(password), now()))
        except sqlite3.IntegrityError:
            raise ApiError('Tên đăng nhập đã được dùng.', 409)
        return session_response(uid, 201)

    @app.post('/api/login')
    def login():
        limited('login:' + digest(request.remote_addr or ''), 20, 600)
        data = body()
        username = field(data, 'username', 32).lower()
        password = data.get('password', '')
        if not isinstance(password, str) or len(password) > 128:
            raise ApiError('Tên đăng nhập hoặc mật khẩu không đúng.', 401)
        user = db().execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        valid = check_password_hash(user['password_hash'] if user else dummy_hash, password)
        if not user or not valid:
            raise ApiError('Tên đăng nhập hoặc mật khẩu không đúng.', 401)
        return session_response(user['id'])

    @app.post('/api/logout')
    def logout():
        return session_response()

    @app.get('/api/models')
    @login_required
    def models():
        return jsonify(items=service.describe())

    @app.post('/api/predictions')
    @login_required
    def predictions():
        limited('predict:' + g.user_id, 60, 60)
        data = body()
        text = field(data, 'text', 2000, 1)
        sender = field(data, 'sender', 80)
        model, language = data.get('model'), data.get('language')
        if model not in ('ml','dl') or language not in ('vi','uci'):
            raise ApiError('model phải là ml/dl; language phải là vi/uci.')
        keep = data.get('save_history', False)
        if type(keep) is not bool:
            raise ApiError('save_history phải là boolean.')
        request_key = field(data, 'request_id', 64) or uuid.uuid4().hex
        fingerprint = digest(json.dumps([text,sender,model,language,keep],ensure_ascii=False))
        def replay(row):
            if row['input_digest'] != fingerprint:
                raise ApiError('Mã yêu cầu đã được dùng cho nội dung khác. Gửi lần kiểm tra mới.',409)
            result = json.loads(row['result'])
            result.update(sender_display=redact(sender), saved=bool(row['keep_history']), replayed=True)
            return jsonify(result), 200
        existing = db().execute('SELECT * FROM predictions WHERE user_id=? AND request_key=?',
                                 (g.user_id,request_key)).fetchone()
        if existing:
            return replay(existing)
        rule = db().execute('SELECT * FROM rules WHERE user_id=? AND sender_key=?',
                            (g.user_id, sender_key(sender))).fetchone() if sender else None
        start = time.perf_counter()
        if rule:
            result = dict(label='spam' if rule['type']=='block' else 'ham', decision_source=rule['type'],
                          rule_id=rule['id'], score=None, threshold=None, model_version=None,
                          dataset_id=None, model=model, language=language, truncated=False)
        else:
            result = dict(service.predict(text, model, language), decision_source='model')
        pid, created = uuid.uuid4().hex, now()
        result.update(prediction_id=pid, created_at=created, saved=keep,
                      sender_display=redact(sender), latency_ms=round((time.perf_counter()-start)*1000, 2))
        stored = {key:value for key,value in result.items() if key!='sender_display'}
        try:
            with db() as conn:
                conn.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?,?)',
                             (pid,g.user_id,redact(text) if keep else None,redact(sender) if keep else None,
                              int(keep),json.dumps(stored,ensure_ascii=False),created,request_key,fingerprint))
        except sqlite3.IntegrityError:
            existing=db().execute('SELECT * FROM predictions WHERE user_id=? AND request_key=?',
                                  (g.user_id,request_key)).fetchone()
            if existing:
                return replay(existing)
            raise
        return jsonify(result), 201

    def owned_prediction(pid):
        row = db().execute('SELECT * FROM predictions WHERE id=? AND user_id=?', (pid,g.user_id)).fetchone()
        if not row:
            raise ApiError('Không tìm thấy lần kiểm tra này.', 404)
        return row

    @app.get('/api/predictions/<pid>')
    @login_required
    def prediction_detail(pid):
        row = owned_prediction(pid)
        result = json.loads(row['result'])
        result.update(text=row['text_redacted'], sender_display=row['sender_display'], saved=bool(row['keep_history']))
        return jsonify(result)

    @app.get('/api/history')
    @login_required
    def history():
        try:
            page = int(request.args.get('page','1'))
        except ValueError:
            raise ApiError('page phải là số nguyên.')
        if not 1 <= page <= 100000:
            raise ApiError('page ngoài phạm vi.')
        label = request.args.get('label','all')
        if label not in ('all','spam','ham'):
            raise ApiError('label phải là all/spam/ham.')
        condition, values = 'user_id=? AND keep_history=1', [g.user_id]
        if label != 'all':
            condition += " AND json_extract(result,'$.label')=?"
            values.append(label)
        total = db().execute('SELECT count(*) FROM predictions WHERE '+condition,values).fetchone()[0]
        rows = db().execute('SELECT * FROM predictions WHERE '+condition+' ORDER BY created_at DESC LIMIT 20 OFFSET ?',
                            values+[(page-1)*20]).fetchall()
        items = [dict(json.loads(row['result']),text=row['text_redacted'],sender_display=row['sender_display']) for row in rows]
        return jsonify(items=items,total=total,page=page,page_size=20)

    @app.delete('/api/history')
    @login_required
    def clear_history():
        with db() as conn:
            conn.execute('UPDATE predictions SET text_redacted=NULL,sender_display=NULL,keep_history=0 WHERE user_id=?',
                         (g.user_id,))
        return jsonify(message='Đã xóa nội dung lịch sử. Giữ metadata tối thiểu để đối chiếu phản hồi.')

    @app.delete('/api/history/<pid>')
    @login_required
    def delete_history(pid):
        owned_prediction(pid)
        with db() as conn:
            conn.execute('UPDATE predictions SET text_redacted=NULL,sender_display=NULL,keep_history=0 WHERE id=? AND user_id=?',
                         (pid,g.user_id))
        return jsonify(message='Đã xóa nội dung tin khỏi lịch sử.')

    @app.get('/api/rules')
    @login_required
    def get_rules():
        return jsonify(items=[dict(row) for row in db().execute(
            'SELECT id,sender_display,type,version,created_at FROM rules WHERE user_id=? ORDER BY created_at DESC',
            (g.user_id,)).fetchall()])

    @app.post('/api/rules')
    @login_required
    def save_rule():
        data=body()
        sender=field(data,'sender',80,1)
        kind=data.get('type')
        if kind not in ('block','allow'):
            raise ApiError('type phải là block hoặc allow.')
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing=conn.execute('SELECT * FROM rules WHERE user_id=? AND sender_key=?',
                                  (g.user_id,sender_key(sender))).fetchone()
            if existing and existing['type']!=kind:
                if type(data.get('expected_version')) is not int or data['expected_version']!=existing['version']:
                    raise ApiError('Người gửi đã có quy tắc khác. Xác nhận để thay thế.',409,
                                   existing={key:existing[key] for key in ('id','sender_display','type','version')})
                conn.execute('UPDATE rules SET type=?,version=version+1 WHERE id=? AND user_id=?',
                             (kind,existing['id'],g.user_id))
                rid=existing['id']
            elif existing:
                rid=existing['id']
            else:
                rid=uuid.uuid4().hex
                conn.execute('INSERT INTO rules VALUES(?,?,?,?,?,?,?)',
                             (rid,g.user_id,sender_key(sender),redact(sender),kind,1,now()))
        return jsonify(id=rid,message='Đã lưu quy tắc riêng. Kiểm tra lại để áp dụng.')

    @app.delete('/api/rules/<rid>')
    @login_required
    def delete_rule(rid):
        with db() as conn:
            cursor=conn.execute('DELETE FROM rules WHERE id=? AND user_id=?',(rid,g.user_id))
            if cursor.rowcount!=1:
                raise ApiError('Không tìm thấy quy tắc.',404)
        return jsonify(message='Đã gỡ quy tắc riêng.')

    @app.post('/api/feedback')
    @login_required
    def save_feedback():
        data=body()
        pid=field(data,'prediction_id',64,1)
        owned_prediction(pid)
        label=data.get('proposed_label')
        if label not in ('spam','ham'):
            raise ApiError('Nhãn đề xuất phải là spam hoặc ham.')
        note=redact(field(data,'note',300))
        with db() as conn:
            conn.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,prediction_id) '
                         'DO UPDATE SET proposed_label=excluded.proposed_label,note=excluded.note,created_at=excluded.created_at',
                         (uuid.uuid4().hex,g.user_id,pid,label,note,now()))
        return jsonify(message='Đã lưu phản hồi. Đang chờ rà soát, chưa thay đổi mô hình.')

    @app.get('/api/feedback')
    @login_required
    def get_feedback():
        rows=db().execute('SELECT f.id,f.prediction_id,f.proposed_label,f.note,f.created_at,p.result '
                          'FROM feedback f JOIN predictions p ON p.id=f.prediction_id '
                          'WHERE f.user_id=? ORDER BY f.created_at DESC LIMIT 100',(g.user_id,)).fetchall()
        return jsonify(items=[dict(id=r['id'],prediction_id=r['prediction_id'],proposed_label=r['proposed_label'],
                                  note=r['note'],created_at=r['created_at'],status='pending',
                                  original_label=json.loads(r['result'])['label'],
                                  decision_source=json.loads(r['result'])['decision_source']) for r in rows])

    return app


if __name__ == '__main__':
    from waitress import serve
    application=create_app()
    application.extensions['models'].warmup()
    host=os.environ.get('HOST','127.0.0.1')
    port=int(os.environ.get('PORT','8080'))
    print(f'TV4 ready: http://{host}:{port}',flush=True)
    serve(application,host=host,port=port,threads=4,max_request_body_size=20000)
