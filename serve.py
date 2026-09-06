#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地配置服务器

功能:
1. 托管配置生成器等静态页面 (python serve.py 后访问 http://127.0.0.1:8765/)
2. WebDAV 代理: 配置页的"云端同步"通过本机的 /cloud-proxy 转发到 WebDAV，
   彻底绕开浏览器 CORS 跨域限制（页面从 localhost 访问时自动走此通道）

用法:
    python serve.py            # 默认 127.0.0.1:8765
    python serve.py --port 9000

安全: 仅监听 127.0.0.1，外部无法访问。代理只转发 http/https 请求。
"""
import argparse
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

ALLOWED_SCHEMES = ('http://', 'https://')


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # 禁用缓存，保证页面/配置改动即时生效
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_POST(self):
        if self.path.rstrip('/') != '/cloud-proxy':
            self.send_error(404, 'Unknown endpoint')
            return

        try:
            length = int(self.headers.get('Content-Length', 0))
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            url = payload.get('url', '')
            method = payload.get('method', 'GET').upper()
            headers = payload.get('headers', {}) or {}
            body = payload.get('body', '') or ''
        except Exception as e:
            self._json_response(400, {'status': 0, 'text': f'请求格式错误: {e}'})
            return

        if not url or not url.startswith(ALLOWED_SCHEMES):
            self._json_response(400, {'status': 0, 'text': '仅支持 http/https 地址'})
            return

        try:
            resp = requests.request(method, url, headers=headers, data=body,
                                    timeout=30, allow_redirects=True)
            self._json_response(200, {'status': resp.status_code, 'text': resp.text})
        except requests.exceptions.RequestException as e:
            self._json_response(200, {'status': 0, 'text': f'Connection failed: {e}'})

    def _json_response(self, code, obj):
        data = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        # 静态请求不打日志，只记录代理操作
        if self.path.startswith('/cloud-proxy'):
            sys.stderr.write('[cloud-proxy] %s\n' % (fmt % args))


def main():
    parser = argparse.ArgumentParser(description='NewAPI 签到 - 本地配置服务器')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'配置服务器已启动: http://127.0.0.1:{args.port}/config_generator.html')
    print('云端同步已启用本地代理（无 CORS 限制），Ctrl+C 停止')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')


if __name__ == '__main__':
    main()
