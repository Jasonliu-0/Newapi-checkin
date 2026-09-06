#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云端配置同步工具（WebDAV 推/拉）

把本地 .env 的账号配置推送到云端（坚果云/群晖/NextCloud 等 WebDAV），
或从云端拉取配置更新本地 .env —— 一处配置，处处生效。

用法:
    python sync_config.py push     # 本地 .env -> 云端
    python sync_config.py pull     # 云端 -> 本地 .env
    python sync_config.py show     # 查看云端配置（脱敏）

WebDAV 地址与认证的来源（优先级从高到低）:
    1. 命令行参数: --url https://dav.jianguoyun.com/dav/ --auth 用户名:应用密码
    2. .env 中的 CONFIG_URL / CONFIG_AUTH
    3. 交互输入

云端文件格式与配置生成器"保存到云端"一致:
    {"accounts": [...], "dingtalk": {...}, "email": {...}, "serverchan": {...}, "updated_at": "..."}
"""
import argparse
import base64
import io
import json
import os
import re
import sys
from datetime import datetime

import requests

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')


def load_env():
    """读取 .env 为字典"""
    env = {}
    if os.path.exists(ENV_FILE):
        with io.open(ENV_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env


def update_env_var(key, value):
    """更新 .env 中的单个变量（保留其他内容），不存在则追加"""
    with io.open(ENV_FILE, encoding='utf-8') as f:
        content = f.read()
    m = re.search(r'^%s=.*$' % re.escape(key), content, re.M)
    line = f'{key}={value}'
    if m:
        content = content[:m.start()] + line + content[m.end():]
    else:
        content = content.rstrip('\n') + '\n' + line + '\n'
    with io.open(ENV_FILE, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)


def webdav_headers(auth):
    headers = {'Content-Type': 'application/json'}
    if auth:
        if auth.startswith('token:'):
            headers['Authorization'] = 'Bearer ' + auth[6:]
        elif ':' in auth:
            cred = base64.b64encode(auth.encode('utf-8')).decode('utf-8')
            headers['Authorization'] = 'Basic ' + cred
    return headers


def mask(s):
    if not s:
        return '(空)'
    return s[:6] + '***' + s[-4:] if len(s) > 14 else '***'


def cloud_get(url, auth):
    r = requests.get(url, headers=webdav_headers(auth), timeout=30)
    if r.status_code == 401:
        sys.exit('❌ 认证失败: 请检查用户名/应用密码')
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        sys.exit(f'❌ 加载失败: HTTP {r.status_code}')
    try:
        return r.json()
    except json.JSONDecodeError:
        sys.exit('❌ 云端文件不是有效的 JSON')


def cloud_put(url, auth, payload):
    r = requests.put(url, headers=webdav_headers(auth),
                     data=json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'),
                     timeout=30)
    if r.status_code not in (200, 201, 204):
        sys.exit(f'❌ 上传失败: HTTP {r.status_code} {r.text[:120]}')


def build_payload_from_env(env):
    accounts_str = env.get('NEWAPI_ACCOUNTS', '')
    if not accounts_str:
        sys.exit('❌ 本地 .env 中没有 NEWAPI_ACCOUNTS 配置')
    try:
        accounts = json.loads(accounts_str)
    except json.JSONDecodeError:
        sys.exit('❌ 本地 NEWAPI_ACCOUNTS 不是有效的 JSON（简单格式请先在配置生成器转成 JSON）')

    payload = {'accounts': accounts, 'updated_at': datetime.now().isoformat()}

    # 同步通知配置（如已配置）
    dingtalk = {}
    if env.get('DINGTALK_WEBHOOK'):
        dingtalk['webhook'] = env['DINGTALK_WEBHOOK']
    if env.get('DINGTALK_SECRET'):
        dingtalk['secret'] = env['DINGTALK_SECRET']
    if dingtalk:
        payload['dingtalk'] = dingtalk

    email = {k: env[k] for k in ('EMAIL_SMTP_HOST', 'EMAIL_SMTP_PORT', 'EMAIL_USER',
                                 'EMAIL_PASS', 'EMAIL_TO', 'EMAIL_FROM') if env.get(k)}
    if email:
        payload['email'] = email

    if env.get('SERVERCHAN_SENDKEY'):
        payload['serverchan'] = {'sendkey': env['SERVERCHAN_SENDKEY']}

    return payload


def resolve_target(args, env):
    url = args.url or env.get('CONFIG_URL', '')
    auth = args.auth or env.get('CONFIG_AUTH', '')
    if not url:
        print('未找到 WebDAV 地址。请提供 --url 参数，或在 .env 中配置：')
        print('  CONFIG_URL=https://dav.jianguoyun.com/dav/你的目录/')
        print('  CONFIG_AUTH=你的邮箱:应用专用密码')
        sys.exit(1)
    if not url.endswith('/'):
        url += '/'
    filename = args.file or 'newapi-config.json'
    if not re.search(r'\.json$', url):
        url += filename
    return url, auth


def cmd_push(args, env):
    url, auth = resolve_target(args, env)
    payload = build_payload_from_env(env)
    print(f'[推送] {url}')
    print(f'[推送] 账号 {len(payload["accounts"])} 个，令牌已脱敏: '
          + ', '.join(mask(a.get("access_token") or a.get("session") or "") for a in payload["accounts"]))
    cloud_put(url, auth, payload)
    print('✅ 已推送到云端。GHA（通过 Secret 或 CONFIG_URL）和本地拉取均可使用此配置')


def cmd_pull(args, env):
    url, auth = resolve_target(args, env)
    print(f'[拉取] {url}')
    data = cloud_get(url, auth)
    if data is None:
        sys.exit('❌ 云端尚无配置（先执行 push 或在配置生成器保存到云端）')

    accounts = data if isinstance(data, list) else data.get('accounts', [])
    if not accounts:
        sys.exit('❌ 云端配置中没有账号')
    update_env_var('NEWAPI_ACCOUNTS', json.dumps(accounts, ensure_ascii=False))
    print(f'✅ 已拉取 {len(accounts)} 个账号到本地 .env')

    # 通知配置也一并同步到 .env（.env 已有的值不覆盖）
    if isinstance(data, dict):
        dt = data.get('dingtalk', {})
        if dt.get('webhook') and not env.get('DINGTALK_WEBHOOK'):
            update_env_var('DINGTALK_WEBHOOK', dt['webhook'])
        if dt.get('secret') and not env.get('DINGTALK_SECRET'):
            update_env_var('DINGTALK_SECRET', dt['secret'])
        sc = data.get('serverchan', {})
        if sc.get('sendkey') and not env.get('SERVERCHAN_SENDKEY'):
            update_env_var('SERVERCHAN_SENDKEY', sc['sendkey'])
    print('提示: 通知配置如云端有而本地缺失，已自动补齐')


def cmd_show(args, env):
    url, auth = resolve_target(args, env)
    data = cloud_get(url, auth)
    if data is None:
        print('云端尚无配置')
        return
    accounts = data if isinstance(data, list) else data.get('accounts', [])
    print(f'云端配置: {len(accounts)} 个账号, 更新于 {data.get("updated_at", "未知") if isinstance(data, dict) else "-"}')
    for a in accounts:
        cred = mask(a.get('access_token') or a.get('session') or '')
        print(f"  - {a.get('name') or a.get('url')}: {a.get('url')} [{cred}]")


def main():
    parser = argparse.ArgumentParser(description='云端配置同步（WebDAV）')
    parser.add_argument('action', choices=['push', 'pull', 'show'], help='push=本地到云端 / pull=云端到本地 / show=查看')
    parser.add_argument('--url', help='WebDAV 目录或文件地址')
    parser.add_argument('--auth', help='认证: 用户名:应用密码 或 token:令牌')
    parser.add_argument('--file', help='云端文件名（默认 newapi-config.json）')
    args = parser.parse_args()

    env = load_env()
    {'push': cmd_push, 'pull': cmd_pull, 'show': cmd_show}[args.action](args, env)


if __name__ == '__main__':
    main()
