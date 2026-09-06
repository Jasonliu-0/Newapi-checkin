#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare Turnstile 交互式验证求解器

原理:
- Turnstile 在 Playwright/patchright 等自动化浏览器中会被静默卡死（CDP 检测），
  组件 shell 渲染了但挑战 iframe 永远不加载
- 但用【真实 Chrome】（无自动化注入）+ CDP 连接时，组件能完整运行
- 交互式勾选框的 UI 渲染在 closed shadow DOM 里，DOM 查询不可见，
  但组件固定 300x65（本地化文案时更宽），勾选框固定在左侧中间，
  用坐标模拟真实鼠标点击即可通过

两种使用方式:
- get_turnstile_token(sitekey): 本地页面渲染组件，仅返回 token
- solve_and_checkin(base_url, ...): 在站点页面内完成 取sitekey -> 解验证 -> 签到 全流程，
  适用于 requests 被 CF 拦截的环境（如 GitHub Actions）
"""
import http.server
import json
import os
import socket
import subprocess
import tempfile
import threading
import time

CHROME_CANDIDATES = [
    os.environ.get('TURNSTILE_CHROME_PATH'),
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/opt/google/chrome/chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]

LOCAL_HTML = ('<html><head><title>ts</title></head>'
              '<body style="margin:0"><div id="ts" style="padding:10px"></div></body></html>')

RENDER_JS = '''async (sitekey) => {
    if (!document.getElementById('ts')) {
        const holder = document.createElement('div');
        holder.id = 'ts';
        holder.style.cssText = 'position:fixed;top:10px;left:10px;z-index:99999;';
        document.body.appendChild(holder);
    }
    if (!document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]')) {
        const s = document.createElement('script');
        s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
        document.head.appendChild(s);
    }
    for (let i = 0; i < 40; i++) {
        if (window.turnstile && window.turnstile.render) break;
        await new Promise(r => setTimeout(r, 500));
    }
    if (!window.turnstile) throw new Error('turnstile api 初始化失败');
    window.__t = null; window.__e = null; window.__inter = false;
    window.__sitekey = sitekey;
    window.__wid = turnstile.render(document.getElementById('ts'), {
        sitekey: sitekey,
        callback: t => window.__t = t,
        'error-callback': c => window.__e = String(c),
        'before-interactive-callback': () => window.__inter = true,
    });
}'''

RESET_JS = '''() => {
    try { turnstile.remove(window.__wid); } catch (e) {}
    window.__e = null; window.__t = null; window.__inter = false;
    window.__wid = turnstile.render(document.getElementById('ts'), {
        sitekey: window.__sitekey,
        callback: t => window.__t = t,
        'error-callback': c => window.__e = String(c),
        'before-interactive-callback': () => window.__inter = true,
    });
}'''

# 渲染 -> 等交互回调 -> 坐标点击 -> 拿 token；每轮只点一次，失败重置重试
SOLVE_JS_POLL = '''() => ({
    token: window.__t || null,
    err: window.__e,
    interactive: !!window.__inter,
    box: (() => {
        const host = document.querySelector('#ts > div');
        if (!host) return null;
        const r = host.getBoundingClientRect();
        return { x: r.x, y: r.y, w: r.width, h: r.height };
    })(),
})'''


def find_chrome():
    for path in CHROME_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return None


def _get_system_proxy():
    """读取系统代理（Windows 注册表 / 环境变量），浏览器必须与 requests 走同一出口"""
    try:
        import urllib.request
        proxies = urllib.request.getproxies()
        return proxies.get('https') or proxies.get('http')
    except Exception:
        return None


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _LocalHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(LOCAL_HTML.encode())

    def log_message(self, *a):
        pass


def _launch_chrome(proxy=None, url=None):
    """启动真实 Chrome 并返回 (proc, dbg_port)"""
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError('未找到 Chrome 浏览器，无法通过 Turnstile 验证')
    dbg_port = _free_port()
    udd = tempfile.mkdtemp(prefix='ts_solver_')
    chrome_log = tempfile.NamedTemporaryFile(prefix='chrome_', suffix='.log', delete=False)
    args = [
        chrome,
        f'--remote-debugging-port={dbg_port}',
        f'--user-data-dir={udd}',
        '--no-first-run', '--no-default-browser-check',
        '--no-sandbox', '--disable-dev-shm-usage',
        '--disable-gpu',
        '--remote-allow-origins=*',
        '--window-size=700,500',
    ]
    if proxy:
        args.append(f'--proxy-server={proxy}')
    args.append(url or 'about:blank')
    proc = subprocess.Popen(args, stdout=chrome_log, stderr=chrome_log)

    # 轮询等待 CDP 端口就绪（冷启动可能远超 4 秒，固定 sleep 会 ECONNREFUSED）
    import socket as _socket
    deadline = time.time() + 40
    while time.time() < deadline:
        if proc.poll() is not None:
            chrome_log.flush()
            with open(chrome_log.name, errors='ignore') as lf:
                tail = lf.read()[-400:]
            raise RuntimeError(f'Chrome 启动失败（退出码 {proc.returncode}）：{tail}')
        try:
            with _socket.create_connection(('127.0.0.1', dbg_port), timeout=2):
                time.sleep(0.5)
                return proc, dbg_port
        except OSError:
            time.sleep(0.5)
    raise RuntimeError('等待 Chrome CDP 端口超时（40s）')


def _solve_in_page(page, sitekey, max_wait=90, verbose=True):
    """在当前页面渲染 Turnstile 并自动点击，返回 token 或 None"""
    page.evaluate(RENDER_JS, sitekey)

    clicked = False
    round_started = 0.0
    rounds = 0
    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(1)
        attempt = int(time.time() - start)
        st = page.evaluate(SOLVE_JS_POLL)

        if st['token']:
            if verbose:
                print(f'[Turnstile] token 获取成功 (耗时 {attempt}s)')
            return st['token']

        # 300xxx = 挑战执行失败（如重复点击破坏挑战），重置组件重试
        if st['err']:
            if verbose:
                print(f'[Turnstile] 挑战失败 ({st["err"]})，重置组件重试...')
            page.evaluate(RESET_JS)
            clicked = False
            rounds += 1
            if rounds >= 4:
                if verbose:
                    print('[Turnstile] 多轮重试均失败')
                return None
            continue

        box, interactive = st['box'], st['interactive']
        # 每轮只点击一次：等交互回调出现并稍作停顿后点击，之后耐心等待结果
        if box and box['w'] > 50 and interactive and not clicked:
            time.sleep(2)
            cx, cy = box['x'] + 30, box['y'] + box['h'] / 2
            if verbose:
                print(f'[Turnstile] 交互验证框出现，模拟点击勾选框 ({cx:.0f}, {cy:.0f})')
            page.mouse.move(cx - 15, cy - 8)
            time.sleep(0.4)
            page.mouse.move(cx - 3, cy)
            time.sleep(0.4)
            page.mouse.click(cx, cy)
            clicked = True
            round_started = time.time()
        elif clicked and time.time() - round_started > 30:
            # 点击后 30s 无结果且无报错，视为挑战卡死，重置重试
            page.evaluate(RESET_JS)
            clicked = False
            rounds += 1
            if rounds >= 4:
                if verbose:
                    print('[Turnstile] 多轮重试均失败')
                return None
    if verbose:
        print('[Turnstile] 等待超时')
    return None


def _wait_cf_pass(page, base_url, timeout=60, verbose=True):
    """导航到站点并等待 CF 验证通过，返回是否成功"""
    page.goto(base_url, wait_until='domcontentloaded', timeout=45000)
    start = time.time()
    while time.time() - start < timeout:
        title = page.title()
        if 'Attention Required' not in title and 'Just a moment' not in title:
            return True
        if verbose:
            print(f'[Turnstile] 等待 CF 验证通过: {title[:40]}')
        time.sleep(5)
    return False


def solve_and_checkin(base_url: str, sitekey: str = None, auth_headers: dict = None,
                      proxy: str = None, max_wait: int = 120, verbose: bool = True):
    """
    在站点页面内完成 Turnstile 解验证 + 签到全流程（requests 被 CF 拦也能走通）

    Args:
        base_url: 站点地址
        sitekey: Turnstile sitekey，不传则自动从 /api/status 获取
        auth_headers: 签到请求头（Authorization / New-Api-User）
        proxy: 代理地址；默认自动读系统代理（GHA 无代理则为 None）
    Returns:
        签到接口的 JSON 响应 dict，失败返回 None
    """
    if proxy is None:
        proxy = _get_system_proxy()
    auth_headers = auth_headers or {}

    proc, dbg_port = _launch_chrome(proxy, url=base_url)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = None
            last_err = None
            for _ in range(3):
                try:
                    browser = p.chromium.connect_over_cdp(f'http://127.0.0.1:{dbg_port}')
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(3)
            if browser is None:
                raise RuntimeError(f'CDP 连接失败: {last_err}')
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            if not _wait_cf_pass(page, base_url, verbose=verbose):
                if verbose:
                    print('[Turnstile] CF 验证未通过')
                return None

            # 页面内 JS：PoW 挑战获取 + 求解（SHA-256 前导零比特，与官方 Worker 算法一致）
            SOLVE_POW_JS = '''async (headers) => {
                const r = await fetch('/api/user/pow/challenge?action=checkin', {
                    credentials: 'include', headers: headers
                });
                const j = await r.json();
                if (!j.success) throw new Error(j.message || '获取 PoW 挑战失败');
                const {challenge_id, prefix, difficulty} = j.data;
                let n = 0;
                for (;;) {
                    const nonce = n.toString(16).padStart(8, '0');
                    const h = new Uint8Array(await crypto.subtle.digest('SHA-256',
                        new TextEncoder().encode(prefix + nonce)));
                    const full = Math.floor(difficulty / 8), rem = difficulty % 8;
                    let ok = true;
                    for (let i = 0; i < full; i++) if (h[i] !== 0) { ok = false; break; }
                    if (ok && rem > 0 && (h[full] & (255 << (8 - rem))) !== 0) ok = false;
                    if (ok) return {challenge_id, nonce};
                    n++;
                    if (n > 0xffffffff) throw new Error('超过最大尝试次数');
                }
            }'''

            POST_JS = '''async (args) => {
                const headers = Object.assign({'Content-Type': 'application/json'}, args.headers);
                const resp = await fetch('/api/user/checkin' + (args.query || ''), {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(args.body || {}),
                    credentials: 'include',
                });
                const text = await resp.text();
                try { return JSON.parse(text); }
                catch (e) { return { success: false, message: '响应非JSON: ' + text.substring(0, 120) }; }
            }'''

            # 第一跳：不带验证参数直接签到
            result = page.evaluate(POST_JS, {'headers': auth_headers})

            # 按服务端要求补验证（最多两轮：PoW / Turnstile 任意组合）
            ts_token = None
            pow_params = None
            for _ in range(2):
                if not isinstance(result, dict) or result.get('success'):
                    break
                msg = str(result.get('message', '')).lower()
                if 'pow' in msg and pow_params is None:
                    if verbose:
                        print('[Turnstile] 服务端要求 PoW 工作量证明，页面内解算...')
                    pow_params = page.evaluate(SOLVE_POW_JS, auth_headers)
                    if verbose:
                        print(f"[Turnstile] PoW 解算完成: nonce={pow_params['nonce']}")
                elif 'turnstile' in msg and ts_token is None:
                    if not sitekey:
                        sitekey = page.evaluate('''async () => {
                            try {
                                const r = await fetch('/api/status');
                                const j = await r.json();
                                return (j.data && j.data.turnstile_site_key) || null;
                            } catch (e) { return null; }
                        }''')
                        if verbose:
                            print(f'[Turnstile] sitekey: {sitekey}')
                    if not sitekey:
                        break
                    ts_token = _solve_in_page(page, sitekey, max_wait=max_wait, verbose=verbose)
                    if not ts_token:
                        break
                else:
                    break
                # 组装查询参数并重试
                query = ''
                body = {}
                from urllib.parse import quote
                if ts_token:
                    query += ('&' if query else '?') + 'turnstile=' + quote(ts_token)
                    body['turnstile'] = ts_token
                if pow_params:
                    query += ('&' if query else '?') + ('pow_challenge=' + quote(pow_params['challenge_id']) +
                             '&pow_nonce=' + quote(pow_params['nonce']))
                result = page.evaluate(POST_JS, {'headers': auth_headers, 'query': query, 'body': body})

            browser.close()
            return result
    except Exception as e:
        print(f'[Turnstile] 求解失败: {e}')
        return None
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def get_turnstile_token(sitekey: str, proxy: str = None, max_wait: int = 90, verbose: bool = True):
    """本地页面渲染 Turnstile 组件并自动点击，返回 token（调试用）"""
    if proxy is None:
        proxy = _get_system_proxy()

    port_http = _free_port()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port_http), _LocalHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    proc = None
    token = None
    try:
        proc, dbg_port = _launch_chrome(proxy, url=f'http://127.0.0.1:{port_http}/')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = None
            last_err = None
            for _ in range(3):
                try:
                    browser = p.chromium.connect_over_cdp(f'http://127.0.0.1:{dbg_port}')
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(3)
            if browser is None:
                raise RuntimeError(f'CDP 连接失败: {last_err}')
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            token = _solve_in_page(page, sitekey, max_wait=max_wait, verbose=verbose)
            browser.close()
    except Exception as e:
        print(f'[Turnstile] 求解失败: {e}')
    finally:
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        server.shutdown()
    return token
