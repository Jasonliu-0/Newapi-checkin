#!/usr/bin/env python3
 # -*- coding: utf-8 -*-
"""
Cloudflare 绕过模块

借鉴 newapi-auto-checkin Chrome 扩展的思路：
- 检测 CF 拦截（403 + HTML 验证页面)
- 使用 Playwright 无头浏览器自动过 CF 阴护
- 在同一浏览器会话中完成 CF 绌过 + 磀到签到（不拆分为两步)

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
    lower_text = response_text.lower()

    if status_code == 403:
        if 'just a moment' in lower_text:
            return True, 'Cloudflare JS Challenge (403 + Just a moment)'
        if '<!doctype html' in lower_text and 'cloudflare' in lower_text:
            return True, 'Cloudflare HTML Challenge (403 + Cloudflare page)'

    if status_code == 503:
        if 'cloudflare' in lower_text and ('challenge' in lower_text or 'checking your browser' in lower_text):
            return True, 'Cloudflare Challenge (503)'

    try:
        import json
        json.loads(response_text)
    except (json.JSONDecodeError, ValueError):
        if '<!doctype' in lower_text and ('just a moment' in lower_text or 'challenge-platform' in lower_text or 'cf-challenge' in lower_text):
            return True, 'Cloudflare Challenge (non-JSON HTML response)'

    return False, ''


class CloudflareBypasser:
    """
    使用 Playwright 无头浏览器绕过 Cloudflare 防护

    核心设计: 在同一个浏览器会话中完成 CF 绕过和签到
    (对应 Chrome 扩展在同一标签页中完成所有操作)
    """

    def __init__(self, base_url: str, session_cookie: str = None, user_id: str = None,
                 cf_clearance: str = None):
        self.base_url = base_url.rstrip('/')
        self.session_cookie = session_cookie
        self.user_id = user_id
        self.cf_clearance = cf_clearance
        self._playwright_available = self._check_playwright()

    def _check_playwright(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        return self._playwright_available

    def _solve_cf_challenge(self, page, max_attempts: int = 5, wait_seconds: int = 8, deadline: float = None) -> bool:
        """
        磻解 CF 验证挑战
        """
        for attempt in range(max_attempts):
            if deadline is not None and time.monotonic() >= deadline:
                break
            title = page.title()
            current_url = page.url
            print(f'[CF 绕过] 检查 CF 猡证状态 (尝试 {attempt + 1}/{max_attempts}): Title="{title[:50]}"')

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
                remaining_ms = 10000 if deadline is None else max(1, int((deadline - time.monotonic()) * 1000))
                page.wait_for_load_state('networkidle', timeout=min(10000, remaining_ms))
            except Exception:
                pass
            remaining = wait_seconds if deadline is None else max(0, deadline - time.monotonic())
            time.sleep(min(wait_seconds, remaining))

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

    def bypass_and_checkin(self, checkin_path: str = '/api/user/sign_in', timeout: int = 90) -> Optional[dict]:
        """
        在同一个 Playwright 会话中完成 CF 绕过 + 笾到签到

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
        deadline = time.monotonic() + timeout
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

                if self.session_cookie or self.cf_clearance:
                    from urllib.parse import urlparse
                    parsed_url = urlparse(self.base_url)
                    cookies = []
                    if self.session_cookie:
                        cookies.append({
                            'name': 'session',
                            'value': self.session_cookie,
                            'domain': parsed_url.hostname,
                            'path': '/',
                            'secure': parsed_url.scheme == 'https',
                        })
                    if self.cf_clearance:
                        cookies.append({
                            'name': 'cf_clearance',
                            'value': self.cf_clearance,
                            'domain': parsed_url.hostname,
                            'path': '/',
                            'secure': parsed_url.scheme == 'https',
                        })
                    context.add_cookies(cookies)

                page = context.new_page()

                print('[CF 绕过] 正在加载页面并等待 CF 验证...')
                page.goto(self.base_url, wait_until='domcontentloaded', timeout=min(30000, max(1, int((deadline - time.monotonic()) * 1000))))

                cf_solved = self._solve_cf_challenge(page, max_attempts=6, wait_seconds=8, deadline=deadline)

                if not cf_solved:
                    print('[CF 绕过] CF 验证无法自动通过，尝试直接签到...')
                else:
                    print('[CF 绕过] CF 验证已通过，准备执行签到...')

                if self.user_id:
                    page.evaluate('(userId) => localStorage.setItem("user", JSON.stringify({id: userId}))', self.user_id)

                try:
                    user_text = page.evaluate('() => localStorage.getItem("user")')
                    if not user_text and self.session_cookie and deadline - time.monotonic() > 10:
                        print('[CF 绕过] localStorage 无 user 数据， 尝试访问登录页...')
                        page.goto(f'{self.base_url}/login', wait_until='domcontentloaded', timeout=min(15000, max(1, int((deadline - time.monotonic()) * 1000))))
                        self._solve_cf_challenge(page, max_attempts=3, wait_seconds=5, deadline=deadline)
                        user_text = page.evaluate('() => localStorage.getItem("user")')
                except Exception:
                    pass

                req_headers = {'Content-Type': 'application/json'}
                if self.user_id:
                    req_headers['new-api-user'] = str(self.user_id)
                remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
                checkin_result = page.evaluate('''async ({reqHeaders, checkinPath, requestDeadline}) => {
                    try {
                        const paths = checkinPath === '/api/user/sign_in'
                            ? ['/api/user/sign_in', '/api/user/checkin']
                            : [checkinPath];
                        for (const path of paths) {
                            const requestTimeout = Math.max(1, requestDeadline - Date.now());
                            const resp = await fetch(path, {
                                method: 'POST',
                                headers: reqHeaders,
                                credentials: 'include',
                                redirect: 'error',
                                signal: AbortSignal.timeout(requestTimeout)
                            });
                            if (path === '/api/user/sign_in' && (resp.status === 404 || resp.status === 405)) continue;
                            const text = await resp.text();
                            try {
                                const data = JSON.parse(text);
                                const success = data.success === true || data.status === 'success' || data.ret === 1 || data.code === 0;
                                const message = data.message || data.msg || data.data || '签到完成';
                                const msgStr = typeof message === 'string' ? message : JSON.stringify(message);
                                const alreadyKeywords = ['已签到', '已经签到', '今日已签', '重复签到', 'already checked', 'already check-in', 'already checkin'];
                                const alreadyCheckedIn = !success && alreadyKeywords.some(k => msgStr.includes(k));
                                return {
                                    success: success || alreadyCheckedIn,
                                    alreadyCheckedIn,
                                    message: msgStr,
                                    httpStatus: resp.status,
                                    data: data
                                };
                            } catch(e) {
                                return { error: 'Response is not JSON: ' + text.substring(0, 200), httpStatus: resp.status, success: false };
                            }
                        }
                        return { error: 'No supported check-in endpoint', success: false, httpStatus: 404 };
                    } catch(e) {
                        return { error: e.message, success: false, httpStatus: 0 };
                    }
                }''', {
                    'reqHeaders': req_headers,
                    'checkinPath': checkin_path,
                    'requestDeadline': int(time.time() * 1000) + remaining_ms,
                })

                print(f'[CF 绕过] 磾到结果: {checkin_result.get("message", checkin_result.get("error", "unknown"))}')

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
            domain_parts = (parsed.hostname or '').split('.')
            if len(domain_parts) >= 2:
                masked_domain = f"{domain_parts[0]}.***." + '.'.join(domain_parts[-1:])
            else:
                masked_domain = '***'
            port = f':{parsed.port}' if parsed.port else ''
            return f"{parsed.scheme}://{masked_domain}{port}"
        except Exception:
            return 'https://***'
