"""Tạo tài khoản demo riêng trên mỗi bản cài; không đưa mật khẩu vào Git/ZIP."""
import argparse
from contextlib import closing
from pathlib import Path
import secrets
import sqlite3
import uuid
from werkzeug.security import generate_password_hash
from app import create_app, now


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['create-demo-users'])
    args=parser.parse_args()
    app=create_app()
    output=Path(app.config['DATABASE']).parent/'Tai_khoan_demo.txt'
    rows=[]
    with closing(sqlite3.connect(app.config['DATABASE'])) as conn, conn:
        for username,name in [('demo_a','Tài khoản A'),('demo_b','Tài khoản B')]:
            if conn.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
                continue
            password=secrets.token_urlsafe(15)
            conn.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                         (uuid.uuid4().hex,username,name,generate_password_hash(password),now()))
            rows.append(f'{name}\nTên đăng nhập: {username}\nMật khẩu: {password}\n')
    if rows:
        with output.open('a',encoding='utf-8') as f:
            f.write('\n'.join(rows)+'\nGiữ riêng file này; không đưa vào Git/ZIP công khai.\n')
        try:output.chmod(0o600)
        except OSError:pass
        print(f'Đã tạo tài khoản mới. Thông tin đăng nhập: {output}')
    else:
        print('Tài khoản demo đã có; không đổi mật khẩu hoặc ghi đè dữ liệu.')


if __name__=='__main__':
    main()
