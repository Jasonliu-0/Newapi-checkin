#!/usr/bin/env python3
 # -*- coding: utf-8 -*-
"""
Cloudflare 绕过模块

借鉴 newapi-auto-checkin Chrome 扩展的思路：
- 检测 CF 拦截（403 + HTML 验证页面)
- 使用 Playwright 无头浏览器自动过 CF 防护
- 在同一浏览器会话中完成 CF 绕过 + 直接签到（不拆分为两步)

两种模式映射:
  Chrome 扩展: service worker fetch → CF 拦截 → 标签页 executeScript
  本项目:      requests 直连 → CF 拦截 → Playwright 同会话内完成签到
"""

import os
import re
import time
from typing import Optional, Tuple


def detect_cloudflare_block(status_code: int, response_text: str) -> Tuple[bool, str]:
    """
    检测 Cloudflare 拦截

    借鉴 background.js:153-156 的检测逻辑:
    - 403 + "Just a moment" / <!DOCTYPE html>
    - 非 JSON 响应包含 <!DOCTYPE 标签
    """
    if status_code == 403:
        if 'Just a moment' in response_text or 'just a moment' in response_text.lower():
            return True, 'Cloudflare JS Challenge (403 + Just a moment)'
        if '<!DOCTYPE html' in response_text.lower() and 'cloudflare' in response_text.lower():
            return True, 'Cloudflare HTML Challenge (403 + Cloudflare page)'

    if status_code == 503:
        if 'cloudflare' in response_text.lower() and ('challenge' in response_text.lower() or 'checking your browser' in response_text.lower()):
            return True, 'Cloudflare Challenge (503)'

    try:
        import json
        json.loads(response_text)
    except (json.JSONDecodeError, ValueError):
        if '<!DOCTYPE' in response_text and ('Just a moment' in response_text or 'challenge-platform' in response_text or 'cf-challenge' in response_text):
            return True, 'Cloudflare Challenge (non-JSON HTML response)'

    return False, ''


class CloudflareBypasser:
    """
    使用 Playwright 无头浏览器绕过 Cloudflare 防护

    核心设计: 在同一个浏览器会话中完成 CF 绕过和签到
    (对应 Chrome 扩展在同一标签页中完成所有操作)
    """

    def __init__(self, base_url: str, session_cookie: str = None, user_id: str = None, access_token: str = None):
        self.base_url = base_url.rstrip('/')
        self.session_cookie = session_cookie
        self.user_id = user_id
        self.access_token = access_token
        self._playwright_available = self._check_playwright()

    def _build_auth_headers(self) -> dict:
        """构建认证请求头（new-api 支持 Authorization 访问令牌认证，不依赖 session cookie）"""
        headers = {}
        if self.access_token:
            headers['Authorization'] = self.access_token
        if self.user_id:
            headers['New-Api-User'] = str(self.user_id)
        return headers

    def _check_playwright(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        return self._playwright_available

    def _solve_cf_challenge(self, page, max_attempts: int = 5, wait_seconds: int = 8) -> bool:
        """
        解决 CF 验证挑战
        """
        for attempt in range(max_attempts):
            title = page.title()
            current_url = page.url
            print(f'[CF 绕过] 检查 CF 验证状态 (尝试 {attempt + 1}/{max_attempts}): Title="{title[:50]}"')

            is_cf_challenge = (
                'Just a moment' in title or
                'Checking your browser' in title or
                'Attention Required' in title or
                'cloudflare' in title.lower() and 'challenge' in title.lower()
            )

            if not is_cf_challenge:
                print(f'[CF 绕过] CF 验证已通过: Title="{title}"')
                return True

            print(f'[CF 绕过] CF 验证页面，等待自动解决 ({attempt + 1}/{max_attempts})...')
            try:
                page.wait_for_load_state('networkidle', timeout=30000)
            except Exception:
                pass
            time.sleep(wait_seconds)

        title = page.title()
        is_cf_challenge = (
            'Just a moment' in title or
            'Checking your browser' in title or
            'Attention Required' in title or
            'cloudflare' in title.lower() and 'challenge' in title.lower()
        )
        if not is_cf_challenge:
            print(f'[CF 绕过] CF 验证已通过: Title="{title}"')
            return True

        print('[CF 绕过] CF 验证未能自动解决')
        return False

    def bypass_and_checkin(self, timeout: int = 90) -> Optional[dict]:
        """
        在同一个 Playwright 会话中完成 CF 绕过 + 签到

        流程 (对应 Chrome 扩展 background.js:115-248):
        1. 启动 Playwright 无头浏览器 (stealth 模式)
        2. 设置 session cookie
        3. 导航到目标站点，等待 CF 验证自动解决
        4. CF 验证通过后，注入 user_id 到 localStorage
        5. 在同一页面内调用 /api/user/checkin 完成签到
        6. 返回签到结果
        """
        if not self._playwright_available:
            print('[CF 绕过] Playwright 未安装，无法绕过 Cloudflare')
            return None

        print(f'[CF 绕过] 使用 Playwright 访问 {self._mask_url(self.base_url)}...')
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )

                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN',
                )

                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                """)

                if self.session_cookie:
                    domain = self.base_url.replace('https://', '').replace('http://', '').split('/')[0]
                    context.add_cookies([
                        {'name': 'session', 'value': self.session_cookie, 'domain': domain, 'path': '/'}
                    ])

                page = context.new_page()

                print('[CF 绕过] 正在加载页面并等待 CF 验证...')
                page.goto(self.base_url, wait_until='domcontentloaded', timeout=timeout * 1000)

                cf_solved = self._solve_cf_challenge(page, max_attempts=6, wait_seconds=8)

                if not cf_solved:
                    print('[CF 绕过] CF 验证无法自动通过，尝试直接签到...')
                else:
                    print('[CF 绕过] CF 验证已通过，准备执行签到...')

                if self.user_id:
                    page.evaluate(f'() => localStorage.setItem("user", JSON.stringify({{"id": {self.user_id}}}))')

                # 诊断: 打印浏览器当前携带的 cookie，确认 session 是否真的在
                cookie_names = [c['name'] for c in context.cookies(self.base_url)]
                print(f'[CF 诊断] 浏览器当前 cookies: {cookie_names}')

                auth_headers = self._build_auth_headers()

                # 认证预检: 用 /api/user/self 判断认证是否被后端接受
                # （返回 JSON 说明请求已穿过 CF；401/无权 说明是凭证问题而非 CF 问题）
                try:
                    precheck = page.evaluate('''async (extraHeaders) => {
                        try {
                            const resp = await fetch('/api/user/self', {
                                credentials: 'include',
                                headers: extraHeaders
                            });
                            const text = await resp.text();
                            let msg = text.substring(0, 120);
                            try {
                                const j = JSON.parse(text);
                                msg = j.message || (j.success === true ? 'ok' : msg);
                                return { status: resp.status, message: msg, success: j.success === true };
                            } catch (e) {
                                return { status: resp.status, message: msg, success: false, notJson: true };
                            }
                        } catch (e) {
                            return { status: 0, message: e.message, success: false };
                        }
                    }''', auth_headers)
                    print(f'[CF 诊断] 认证预检 /api/user/self: HTTP {precheck.get("status")} - {precheck.get("message")}')
                except Exception as e:
                    print(f'[CF 诊断] 认证预检执行失败: {e}')

                try:
                    user_text = page.evaluate('() => localStorage.getItem("user")')
                    if not user_text and self.session_cookie:
                        print('[CF 绕过] localStorage 无 user 数据， 尝试访问登录页...')
                        page.goto(f'{self.base_url}/login', wait_until='domcontentloaded', timeout=20000)
                        self._solve_cf_challenge(page, max_attempts=3, wait_seconds=5)
                        user_text = page.evaluate('() => localStorage.getItem("user")')
                except Exception:
                    pass

                checkin_result = page.evaluate('''async (extraHeaders) => {
                    const post = async (query) => {
                        const resp = await fetch('/api/user/checkin' + query, {
                            method: 'POST',
                            headers: Object.assign({'Content-Type': 'application/json'}, extraHeaders),
                            credentials: 'include'
                        });
                        const text = await resp.text();
                        try { return {json: JSON.parse(text), status: resp.status}; }
                        catch (e) { return {notJson: true, status: resp.status, text: text.substring(0, 200)}; }
                    };
                    // PoW 工作量证明：获取挑战并计算 nonce（SHA-256 前导零比特）
                    const solvePoW = async () => {
                        const r = await fetch('/api/user/pow/challenge?action=checkin', {
                            credentials: 'include', headers: extraHeaders
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
                    };
                    try {
                        let res = await post('');
                        if (res.json && res.json.message &&
                            (res.json.message + '').toLowerCase().includes('pow')) {
                            const pow = await solvePoW();
                            res = await post('?pow_challenge=' + encodeURIComponent(pow.challenge_id) +
                                             '&pow_nonce=' + encodeURIComponent(pow.nonce));
                        }
                        if (res.notJson) {
                            return { error: 'Response is not JSON: ' + res.text, httpStatus: res.status, success: false };
                        }
                        const data = res.json;
                        const success = data.success === true || data.status === 'success' || data.ret === 1 || data.code === 0;
                        const message = data.message || data.msg || data.data || '签到完成';
                        const msgStr = typeof message === 'string' ? message : JSON.stringify(message);
                        const alreadyKeywords = ['已签到', '已经签到', 'already', '重复签到'];
                        const alreadyCheckedIn = !success && alreadyKeywords.some(k => msgStr.includes(k));
                        return {
                            success: success || alreadyCheckedIn,
                            alreadyCheckedIn,
                            message: msgStr,
                            httpStatus: res.status,
                            data: data
                        };
                    } catch(e) {
                        return { error: e.message, success: false, httpStatus: 0 };
                    }
                }''', auth_headers)

                print(f'[CF 绕过] 签到结果: {checkin_result.get("message", checkin_result.get("error", "unknown"))}')

                browser.close()
                return checkin_result

            except Exception as e:
                print(f'[CF 绕过] Playwright 执行失败: {e}')
                try:
                    browser.close()
                except Exception:
                    pass
                return None

    @staticmethod
    def _mask_url(url: str) -> str:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain_parts = parsed.netloc.split('.')
            if len(domain_parts) >= 2:
                masked_domain = f"{domain_parts[0]}.***." + '.'.join(domain_parts[-1:])
            else:
                masked_domain = '***'
            return f"{parsed.scheme}://{masked_domain}"
        except Exception:
            return 'https://***'