#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewAPI 自动签到脚本
支持多账号签到，通过 GitHub Actions 定时执行
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from typing import Optional

try:
    from cf_bypass import detect_cloudflare_block, CloudflareBypasser
    CF_BYPASS_AVAILABLE = True
except ImportError:
    CF_BYPASS_AVAILABLE = False
    detect_cloudflare_block = None
    CloudflareBypasser = None

try:
    from dingtalk_notifier import send_checkin_notification
except ImportError:
    send_checkin_notification = None

try:
    from notifier import send_email_notification, send_serverchan_notification
except ImportError:
    send_email_notification = None
    send_serverchan_notification = None

try:
    from lottery import run_for_account as lottery_run_for_account
    from lottery import run_gwent_for_account
except ImportError:
    lottery_run_for_account = None
    run_gwent_for_account = None


class NewAPICheckin:
    """NewAPI 签到类"""

    @staticmethod
    def _mask_url(url: str) -> str:
        """
        脱敏 URL，隐藏域名细节
        例如: https://api.example.com -> https://api.***.**
        """
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain_parts = parsed.netloc.split('.')
            if len(domain_parts) >= 2:
                # 保留第一部分和最后一部分，中间用 *** 代替
                masked_domain = f"{domain_parts[0]}.***." + '.'.join(domain_parts[-1:])
            else:
                masked_domain = '***'
            return f"{parsed.scheme}://{masked_domain}"
        except Exception:
            return 'https://***'

    @staticmethod
    def _mask_user_id(user_id: str) -> str:
        """
        脱敏用户ID
        例如: 1429 -> ****
        """
        return '****'

    def __init__(self, base_url: str, session_cookie: str, user_id: str = None, cf_clearance: str = None,
                 login_username: str = None, login_password: str = None, access_token: str = None):
        self.base_url = base_url.rstrip('/')
        self.session_cookie = session_cookie
        self.original_cf_clearance = cf_clearance
        self.cf_bypassed = False
        self.login_username = login_username
        self.login_password = login_password
        self.access_token = access_token
        self.session = requests.Session()
        if session_cookie:
            self.session.cookies.set('session', session_cookie)

        if cf_clearance:
            self.session.cookies.set('cf_clearance', cf_clearance)

        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-store',
            'Pragma': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

        # new-api 支持系统访问令牌认证（Authorization 头），不依赖 session cookie
        if access_token:
            self.session.headers.update({'Authorization': access_token})

        self.user_id = user_id
        if user_id:
            self.session.headers.update({'new-api-user': str(user_id)})

    def _try_login(self) -> bool:
        """
        尝试使用配置的账号密码重新登录，获取新的 session

        登录接口：POST /api/user/login
        请求体：{"username": x, "password": x}
        成功时 cookie 中包含新的 session_id

        Returns:
            True 如果登录成功，False 否则
        """
        if not self.login_username or not self.login_password:
            return False

        print(f'  [登录] 尝试重新登录...')
        try:
            resp = self.session.post(
                f'{self.base_url}/api/user/login',
                json={'username': self.login_username, 'password': self.login_password},
                timeout=30
            )

            if resp.status_code == 429:
                print(f'  [登录] 请求过多 (429)，跳过登录')
                return False

            try:
                data = resp.json()
            except json.JSONDecodeError:
                content_preview = resp.text[:100] if resp.text else '(空响应)'
                print(f'  [登录] 响应格式错误 (HTTP {resp.status_code}): {content_preview}')
                return False

            if resp.status_code == 200 and data.get('success'):
                # 从响应 cookie 中获取新的 session_id
                new_session = None
                for cookie in resp.cookies:
                    if cookie.name == 'session' or cookie.name == 'session_id':
                        new_session = cookie.value
                        break

                if new_session:
                    self.session_cookie = new_session
                    self.session.cookies.set('session', new_session)
                    print(f'  [登录] 登录成功，已更新 session')
                    return True
                else:
                    # 可能 session cookie 在 set-cookie 头中
                    set_cookie = resp.headers.get('Set-Cookie', '')
                    import re
                    match = re.search(r'(?:session|session_id)=([^;]+)', set_cookie)
                    if match:
                        new_session = match.group(1)
                        self.session_cookie = new_session
                        self.session.cookies.set('session', new_session)
                        print(f'  [登录] 登录成功，已更新 session')
                        return True

                    print(f'  [登录] 登录成功但未获取到新的 session cookie')
                    return False
            else:
                msg = data.get('message', '未知错误')
                print(f'  [登录] 登录失败: {msg}')
                return False

        except Exception as e:
            print(f'  [登录] 登录请求异常: {e}')
            return False

    def get_user_info(self, verbose: bool = False) -> Optional[dict]:
        """
        获取用户信息

        自动设置 new-api-user 请求头

        Args:
            verbose: 是否显示详细调试信息
        """
        try:
            resp = self.session.get(f'{self.base_url}/api/user/self', timeout=30)

            if verbose:
                print(f'  [调试] HTTP 状态码: {resp.status_code}')
                print(f'  [调试] 响应内容预览: {resp.text[:200]}...')

            # 检查认证失败
            if resp.status_code == 401:
                print(f'[错误] 认证失败 (401): Session 可能已过期')
                if verbose:
                    print(f'  [调试] 完整响应: {resp.text[:500]}')

                # 尝试自动登录
                if self._try_login():
                    print(f'  [登录] 重试获取用户信息...')
                    resp = self.session.get(f'{self.base_url}/api/user/self', timeout=30)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            if data.get('success'):
                                user_data = data.get('data')
                                if user_data and 'id' in user_data:
                                    self.user_id = user_data['id']
                                    self.session.headers.update({
                                        'new-api-user': str(self.user_id)
                                    })
                                return user_data
                        except Exception:
                            pass
                    print(f'  [登录] 重试后仍无法获取用户信息')
                    return None
                else:
                    if self.login_username and self.login_password:
                        print('  [登录] 尝试登录不成功')
                    else:
                        print('  [登录] 未配置账号密码，无法自动重新登录')
                    return None

            # 尝试解析 JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                # 检测是否是 Cloudflare 拦截
                if detect_cloudflare_block:
                    is_blocked, reason = detect_cloudflare_block(resp.status_code, resp.text)
                    if is_blocked:
                        print(f'[CF] 获取用户信息时检测到 Cloudflare 拦截: {reason}')
                        print(f'[CF] 该站点需要 CF 绕过才能访问')
                        return None
                print(f'[错误] 响应格式错误 (HTTP {resp.status_code}): 无法解析 JSON')
                if verbose:
                    print(f'  [调试] 原始响应: {resp.text[:500]}')
                return None

            if verbose:
                print(f'  [调试] success 字段: {data.get("success")}')
                print(f'  [调试] message 字段: {data.get("message")}')

            if resp.status_code == 200:
                if data.get('success'):
                    user_data = data.get('data')
                    # 保存用户ID并设置到请求头
                    if user_data and 'id' in user_data:
                        self.user_id = user_data['id']
                        self.session.headers.update({
                            'new-api-user': str(self.user_id)
                        })
                    return user_data
                else:
                    if verbose:
                        print(f'  [调试] API 返回失败: {data.get("message", "未知错误")}')
            else:
                print(f'[错误] HTTP {resp.status_code}: {data.get("message", "未知错误")}')

            return None

        except requests.exceptions.Timeout:
            print(f'[错误] 请求超时')
            return None
        except requests.exceptions.RequestException as e:
            print(f'[错误] 网络请求失败: {e}')
            return None
        except Exception as e:
            print(f'[错误] 未知错误: {e}')
            if verbose:
                import traceback
                traceback.print_exc()
            return None

    def checkin(self) -> dict:
        """
        执行签到

        流程（借鉴 Chrome 扩展 background.js:115-248）：
        1. requests 直连签到（快速模式）
        2. CF 拦截检测 → Playwright 获取 cookie 后重新签到
        3. 仍然失败 → Playwright 浏览器内直接签到（终极回退）

        Returns:
            签到结果字典
        """
        result = {
            'success': False,
            'message': '',
            'checkin_date': None,
            'quota_awarded': None
        }

        try:
            resp = self.session.post(f'{self.base_url}/api/user/checkin', timeout=30)

            if resp.status_code == 401:
                result['message'] = '认证失败: Session 可能已过期，请重新获取'
                # 尝试自动登录
                if self._try_login():
                    print(f'  [登录] 重试签到...')
                    resp = self.session.post(f'{self.base_url}/api/user/checkin', timeout=30)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            if data.get('success'):
                                result['success'] = True
                                result['message'] = data.get('message', '签到成功')
                                checkin_data = data.get('data', {})
                                result['checkin_date'] = checkin_data.get('checkin_date')
                                result['quota_awarded'] = checkin_data.get('quota_awarded')
                                return result
                        except Exception:
                            pass
                    result['message'] = '重新登录后签到失败'
                    return result
                else:
                    if self.login_username and self.login_password:
                        result['message'] = '尝试登录不成功'
                    return result

            try:
                data = resp.json()
            except json.JSONDecodeError:
                if detect_cloudflare_block:
                    is_blocked, reason = detect_cloudflare_block(resp.status_code, resp.text)
                    if is_blocked:
                        print(f'[CF] 检测到 Cloudflare 拦截: {reason}')
                        return self._cf_bypass_checkin()
                content_preview = resp.text[:200] if resp.text else '(空响应)'
                result['message'] = f'响应格式错误 (HTTP {resp.status_code}): {content_preview}'
                return result

            if detect_cloudflare_block and resp.status_code in (403, 503):
                is_blocked, reason = detect_cloudflare_block(resp.status_code, json.dumps(data))
                if is_blocked:
                    print(f'[CF] 检测到 Cloudflare 拦截: {reason}')
                    return self._cf_bypass_checkin()

            if resp.status_code == 200:
                if data.get('success'):
                    result['success'] = True
                    result['message'] = data.get('message', '签到成功')

                    checkin_data = data.get('data', {})
                    result['checkin_date'] = checkin_data.get('checkin_date')
                    result['quota_awarded'] = checkin_data.get('quota_awarded')
                else:
                    message = data.get('message', '签到失败')
                    already_keywords = ['已签到', '已经签到', 'already', '重复签到']
                    already_checked_in = any(k in message for k in already_keywords)
                    if already_checked_in:
                        result['success'] = True
                        result['message'] = message
                    elif 'pow' in message.lower():
                        # 站点开启 PoW 工作量证明，本地直接解算后重签
                        print(f'[PoW] 站点要求工作量证明: {message}')
                        return self._checkin_with_pow(result)
                    elif 'turnstile' in message.lower():
                        # 站点开启 Turnstile 人机验证，走真实浏览器解验证后重签
                        print(f'[Turnstile] 站点要求人机验证: {message}')
                        return self._turnstile_checkin(result)
                    else:
                        result['message'] = message
            else:
                result['message'] = f'HTTP {resp.status_code}: {data.get("message", "未知错误")}'

        except requests.exceptions.Timeout:
            result['message'] = '请求超时'
        except requests.exceptions.RequestException as e:
            result['message'] = f'网络请求失败: {e}'
        except Exception as e:
            result['message'] = f'未知错误: {e}'

        return result

    @staticmethod
    def _solve_pow(prefix: str, difficulty: int) -> str:
        """计算 PoW nonce：SHA-256(prefix + nonce) 的前 difficulty 个比特全为 0"""
        import hashlib
        counter = 0
        full, rem = divmod(difficulty, 8)
        mask = ((0xFF << (8 - rem)) & 0xFF) if rem else 0
        prefix_bytes = prefix.encode()
        while True:
            nonce = f'{counter:08x}'
            digest = hashlib.sha256(prefix_bytes + nonce.encode()).digest()
            if all(b == 0 for b in digest[:full]):
                if rem == 0 or full >= len(digest) or (digest[full] & mask) == 0:
                    return nonce
            counter += 1
            if counter > 0xffffffff:
                raise RuntimeError('PoW 超过最大尝试次数')

    def _checkin_with_pow(self, result: dict) -> dict:
        """PoW 工作量证明签到（new-api 新版防滥用机制，pow_mode=replace 时替代 Turnstile）"""
        try:
            r = self.session.get(f'{self.base_url}/api/user/pow/challenge',
                                 params={'action': 'checkin'}, timeout=30)
            data = r.json()
            if not data.get('success'):
                result['message'] = f"获取 PoW 挑战失败: {data.get('message', '未知错误')}"
                return result
            ch = data['data']
            difficulty = int(ch['difficulty'])
            print(f'[PoW] 解算挑战 (difficulty={difficulty})...')
            nonce = self._solve_pow(ch['prefix'], difficulty)
            print(f'[PoW] 解算完成: nonce={nonce}')

            resp = self.session.post(
                f'{self.base_url}/api/user/checkin',
                params={'pow_challenge': ch['challenge_id'], 'pow_nonce': nonce},
                timeout=30)
            data = resp.json()
            message = data.get('message', '签到失败')
            already_keywords = ['已签到', '已经签到', 'already', '重复签到']
            if data.get('success') or any(k in message for k in already_keywords):
                result['success'] = True
                result['message'] = f'{message} (PoW)'
                cd = data.get('data', {})
                if isinstance(cd, dict):
                    result['checkin_date'] = cd.get('checkin_date')
                    result['quota_awarded'] = cd.get('quota_awarded')
            else:
                result['message'] = f'PoW 签到失败: {message}'
        except Exception as e:
            result['message'] = f'PoW 签到异常: {e}'
        return result

    def _turnstile_checkin(self, result: dict) -> dict:
        """
        Turnstile 人机验证回退流程

        站点开启 Turnstile 校验时（/api/user/checkin 返回「Turnstile token 为空」），
        用真实 Chrome 渲染验证组件并自动点击，在站点页面内携带 token 签到。
        浏览器内完成全部请求，requests 是否被 CF 拦均可（本地 / GitHub Actions 通吃）。
        """
        try:
            from turnstile_solver import solve_and_checkin
        except ImportError:
            result['message'] = '站点要求 Turnstile 验证但缺少依赖 (playwright + Chrome)'
            return result

        headers = {}
        if self.access_token:
            headers['Authorization'] = self.access_token
        if self.user_id:
            headers['New-Api-User'] = str(self.user_id)

        print('[Turnstile] 启动真实浏览器解验证（会弹出 Chrome 窗口）...')
        resp_data = solve_and_checkin(self.base_url, auth_headers=headers)

        if not resp_data:
            result['message'] = 'Turnstile 验证失败: 未能获取 token 或签到请求失败'
            return result

        message = resp_data.get('message', '签到失败')
        already_keywords = ['已签到', '已经签到', 'already', '重复签到']
        if resp_data.get('success') or any(k in message for k in already_keywords):
            result['success'] = True
            result['message'] = f'{message} (Turnstile)'
            checkin_data = resp_data.get('data', {})
            if isinstance(checkin_data, dict):
                result['checkin_date'] = checkin_data.get('checkin_date')
                result['quota_awarded'] = checkin_data.get('quota_awarded')
        else:
            result['message'] = f'Turnstile 验证后签到失败: {message}'

        return result

    def _cf_bypass_checkin(self) -> dict:
        """
        CF 绕过签到流程

        在同一个 Playwright 会话中完成 CF 绕过 + 签到，
        不拆分 cookie 提取和 requests 重试（因为 cf_clearance 绑定浏览器指纹）
        """
        result = {
            'success': False,
            'message': '',
            'checkin_date': None,
            'quota_awarded': None
        }

        if not CF_BYPASS_AVAILABLE or not CloudflareBypasser:
            result['message'] = 'Cloudflare 拦截: 需安装 Playwright 才能自动绕过 (pip install playwright && playwright install chromium)'
            return result

        bypasser = CloudflareBypasser(self.base_url, self.session_cookie, self.user_id, self.access_token)

        if not bypasser.is_available():
            result['message'] = 'Cloudflare 拦截: Playwright 未正确安装'
            return result

        print('[CF] 开始 Playwright 绕过流程...')
        browser_result = bypasser.bypass_and_checkin()

        if not browser_result:
            result['message'] = 'Cloudflare 绕过失败: 无法通过 CF 验证'
            return result

        self.cf_bypassed = True

        # CF 绕过后 POST 仍被拦截（要求 Turnstile / CF 挑战 HTML）→ 走真实浏览器求解器
        # 注意：必须放在 error 分支之前，否则拦截类 error 直接返回、回退永远不触发
        bypass_combined = (str(browser_result.get('message', '') or '') + ' ' +
                           str(browser_result.get('error', '') or '')).lower()
        if ('turnstile' in bypass_combined or 'response is not json' in bypass_combined
                or 'just a moment' in bypass_combined):
            print('[CF] 绕过后 POST 仍被 CF 拦截或要求 Turnstile，切换真实浏览器求解器...')
            return self._turnstile_checkin(result)

        if browser_result.get('error'):
            result['message'] = f'CF 绕过后签到失败: {browser_result["error"]}'
            return result

        if browser_result.get('alreadyCheckedIn'):
            result['success'] = True
            result['message'] = browser_result.get('message', '今日已签到 (CF绕过)')
        elif browser_result.get('success'):
            result['success'] = True
            result['message'] = browser_result.get('message', '签到成功 (CF绕过)')
            data = browser_result.get('data', {})
            if isinstance(data, dict):
                checkin_data = data.get('data', data)
                result['checkin_date'] = checkin_data.get('checkin_date')
                result['quota_awarded'] = checkin_data.get('quota_awarded')
        else:
            result['message'] = browser_result.get('message', 'CF 绕过后签到失败')

        return result

    def get_checkin_history(self, month: str = None) -> Optional[dict]:
        """
        获取签到历史

        Args:
            month: 月份，格式 YYYY-MM，默认当前月
        """
        if month is None:
            month = datetime.now().strftime('%Y-%m')

        try:
            resp = self.session.get(
                f'{self.base_url}/api/user/checkin',
                params={'month': month},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data')
            return None
        except Exception as e:
            print(f'[错误] 获取签到历史失败: {e}')
            return None


def parse_accounts(accounts_str: str) -> list:
    """
    解析账号配置

    支持格式:
    1. 单账号: BASE_URL#SESSION_COOKIE 或 BASE_URL#SESSION_COOKIE#ACCESS_TOKEN
    2. 多账号: BASE_URL1#SESSION1,BASE_URL2#SESSION2
    3. JSON格式: [{"url": "...", "session": "...", "access_token": "..."}]
    """
    accounts = []

    if not accounts_str:
        return accounts

    # 尝试 JSON 格式
    try:
        data = json.loads(accounts_str)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and 'url' in item and 'session' in item:
                    account = {
                        'url': item['url'],
                        'session': item['session'],
                        'name': item.get('name', '')
                    }
                    # 如果提供了 user_id，添加到账号信息中
                    if 'user_id' in item:
                        account['user_id'] = item['user_id']
                    # 如果提供了 cf_clearance，添加到账号信息中
                    if 'cf_clearance' in item:
                        account['cf_clearance'] = item['cf_clearance']
                    # 如果提供了登录账号密码，添加到账号信息中
                    if 'login_username' in item:
                        account['login_username'] = item['login_username']
                    if 'login_password' in item:
                        account['login_password'] = item['login_password']
                    # 如果提供了系统访问令牌，添加到账号信息中
                    if 'access_token' in item:
                        account['access_token'] = item['access_token']
                    accounts.append(account)
            return accounts
    except json.JSONDecodeError:
        pass

    # 简单格式: URL#SESSION 或 URL#SESSION#ACCESS_TOKEN，多账号用逗号分隔
    for part in accounts_str.split(','):
        part = part.strip()
        if '#' in part:
            fields = part.split('#')
            url = fields[0].strip()
            session = fields[1].strip() if len(fields) > 1 else ''
            access_token = fields[2].strip() if len(fields) > 2 else ''
            accounts.append({
                'url': url,
                'session': session,
                'name': ''
            })
            if access_token:
                accounts[-1]['access_token'] = access_token

    return accounts


def load_config_from_cloud(config_url: str, config_auth: str = None) -> Optional[str]:
    """
    从云端（WebDAV）加载配置

    支持:
    - 坚果云 WebDAV
    - 群晖 NAS WebDAV
    - NextCloud WebDAV
    - 任何支持 WebDAV/直接链接的云存储

    Args:
        config_url: 配置文件 URL (WebDAV 或直接下载链接)
        config_auth: 认证信息，格式:
            - Basic Auth: "username:password"
            - Token Auth: "token:your_token"
    """
    try:
        headers = {}

        if config_auth:
            if config_auth.startswith('token:'):
                headers['Authorization'] = 'Bearer ' + config_auth[6:]
            elif ':' in config_auth:
                import base64 as b64mod
                credentials = b64mod.b64encode(config_auth.encode('utf-8')).decode('utf-8')
                headers['Authorization'] = 'Basic ' + credentials

        print(f'[云端] 正在从云端加载配置: {NewAPICheckin._mask_url(config_url)}')

        resp = requests.get(config_url, headers=headers, timeout=30)

        if resp.status_code == 401:
            print('[云端] 认证失败: 请检查 CONFIG_AUTH 配置')
            return None
        elif resp.status_code == 404:
            print('[云端] 配置文件不存在: 请先通过配置生成器保存到云端')
            return None
        elif resp.status_code != 200:
            print(f'[云端] 加载失败: HTTP {resp.status_code}')
            return None

        data = resp.json()

        if isinstance(data, list):
            accounts_str = json.dumps(data)
            print(f'[云端] 成功加载 {len(data)} 个账号配置')
            return accounts_str
        elif isinstance(data, dict) and 'accounts' in data:
            accounts = data['accounts']
            accounts_str = json.dumps(accounts)
            print(f'[云端] 成功加载 {len(accounts)} 个账号配置')

            if data.get('dingtalk'):
                dt = data['dingtalk']
                if dt.get('webhook') and not os.environ.get('DINGTALK_WEBHOOK'):
                    os.environ['DINGTALK_WEBHOOK'] = dt['webhook']
                if dt.get('secret') and not os.environ.get('DINGTALK_SECRET'):
                    os.environ['DINGTALK_SECRET'] = dt['secret']
                if dt.get('webhook'):
                    print('[云端] 已从云端加载钉钉通知配置')

            if data.get('email'):
                em = data['email']
                if em.get('smtp_host') and not os.environ.get('EMAIL_SMTP_HOST'):
                    os.environ['EMAIL_SMTP_HOST'] = em['smtp_host']
                if em.get('smtp_port') and not os.environ.get('EMAIL_SMTP_PORT'):
                    os.environ['EMAIL_SMTP_PORT'] = str(em['smtp_port'])
                if em.get('user') and not os.environ.get('EMAIL_USER'):
                    os.environ['EMAIL_USER'] = em['user']
                if em.get('pass') and not os.environ.get('EMAIL_PASS'):
                    os.environ['EMAIL_PASS'] = em['pass']
                if em.get('to') and not os.environ.get('EMAIL_TO'):
                    os.environ['EMAIL_TO'] = em['to']
                if em.get('from_addr') and not os.environ.get('EMAIL_FROM'):
                    os.environ['EMAIL_FROM'] = em['from_addr']
                if em.get('smtp_host'):
                    print('[云端] 已从云端加载邮件通知配置')

            if data.get('serverchan'):
                sc = data['serverchan']
                if sc.get('sendkey') and not os.environ.get('SERVERCHAN_SENDKEY'):
                    os.environ['SERVERCHAN_SENDKEY'] = sc['sendkey']
                if sc.get('sendkey'):
                    print('[云端] 已从云端加载 ServerChan 通知配置')

            return accounts_str
        else:
            print('[云端] 配置格式错误: 无法解析账号列表')
            return None

    except json.JSONDecodeError:
        print('[云端] 配置文件不是有效的 JSON 格式')
        return None
    except requests.exceptions.Timeout:
        print('[云端] 请求超时')
        return None
    except requests.exceptions.RequestException as e:
        print(f'[云端] 网络请求失败: {e}')
        return None
    except Exception as e:
        print(f'[云端] 加载失败: {e}')
        return None


def load_env_file():
    """加载脚本同目录下的 .env 文件到环境变量"""
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.isfile(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                if key and value:
                    os.environ.setdefault(key, value)


def build_advice(message: str) -> str:
    """根据失败消息生成排查建议（随通知推送）"""
    m = message.lower()
    if 'turnstile' in m:
        return ('该站开启 Turnstile 人机验证，已自动点击求解；若反复失败，'
                '建议本地运行一次 python checkin.py')
    if 'just a moment' in m or 'cloudflare' in m or m.startswith('cf'):
        return ('CF 网络层拦截未能通过（数据中心 IP 可能被限制），'
                '建议本地运行一次 python checkin.py（自动走系统代理出口）')
    if 'pow' in m:
        return 'PoW 工作量证明解算异常，建议直接重试一次；持续失败请把日志发给维护者'
    if 'access token' in m or 'token 无效' in m or '认证失败' in m or '无权' in m:
        return ('请在站点「个人设置」重新生成系统访问令牌并更新配置'
                '（更新后可运行 python sync_config.py push 同步到云端）')
    if 'session' in m or '过期' in m:
        return 'Session 已失效：可配置账号密码自动续期，或改用系统访问令牌（推荐）'
    return ''


def main():
    """主函数"""
    load_env_file()
    import pytz
    beijing_tz = pytz.timezone('Asia/Shanghai')
    execution_time = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")
    print('=' * 50)
    print('NewAPI 自动签到')
    print(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 50)

    config_url = os.environ.get('CONFIG_URL', '')
    config_auth = os.environ.get('CONFIG_AUTH', '')

    accounts_str = ''

    if config_url:
        accounts_str = load_config_from_cloud(config_url, config_auth) or ''

    if not accounts_str:
        accounts_str = os.environ.get('NEWAPI_ACCOUNTS', '')

    from_env_file = False
    if not accounts_str:
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        if os.path.isfile(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('NEWAPI_ACCOUNTS='):
                        accounts_str = line[len('NEWAPI_ACCOUNTS='):]
                        from_env_file = True
                        break

    if not accounts_str:
        print('[错误] 未配置账号信息')
        print('请设置 CONFIG_URL（云端配置）或 NEWAPI_ACCOUNTS（本地配置）环境变量')
        sys.exit(1)

    accounts = parse_accounts(accounts_str)

    if not accounts:
        print('[错误] 账号配置解析失败')
        sys.exit(1)

    print(f'共 {len(accounts)} 个账号待签到\n')

    success_count = 0
    fail_count = 0
    checkin_results = []
    session_updated = False

    for i, account in enumerate(accounts, 1):
        url = account['url']
        session_cookie = account['session']
        user_id = account.get('user_id')
        cf_clearance = account.get('cf_clearance')
        login_username = account.get('login_username')
        login_password = account.get('login_password')
        access_token = account.get('access_token')
        name = account.get('name') or f'账号{i}'

        print(f'[{i}/{len(accounts)}] {name}')
        print(f'  站点: {NewAPICheckin._mask_url(url)}')
        if user_id:
            print(f'  用户ID: {NewAPICheckin._mask_user_id(user_id)}')

        client = NewAPICheckin(url, session_cookie, user_id, cf_clearance, login_username, login_password, access_token)

        # 获取用户信息（可能触发自动登录）
        user_info = client.get_user_info()
        if client.session_cookie != session_cookie:
            account['session'] = client.session_cookie
            session_updated = True
        if user_info:
            username = user_info.get('username', '未知')
            # 用户名也脱敏，只显示前3个字符
            masked_username = username[:3] + '***' if len(username) > 3 else '***'
            print(f'  用户: {masked_username}')
        else:
            print('  用户: 获取失败（可能 session 已过期）')

        # 执行签到
        result = client.checkin()
        if client.session_cookie != session_cookie:
            account['session'] = client.session_cookie
            session_updated = True
        checkin_count = 0  # 默认值，避免历史接口失败时未定义

        if result['success']:
            success_count += 1
            print(f'  结果: ✅ {result["message"]}')

            # 显示签到日期
            if result['checkin_date']:
                print(f'  日期: {result["checkin_date"]}')

            # 显示获得的额度（格式化显示）
            if result['quota_awarded']:
                quota = result['quota_awarded']
                # 格式化额度显示
                if quota >= 1000000:
                    quota_str = f'{quota / 1000000:.2f}M'
                elif quota >= 1000:
                    quota_str = f'{quota / 1000:.2f}K'
                else:
                    quota_str = str(quota)
                print(f'  奖励: +{quota_str} 额度 ({quota:,} tokens)')

            # 获取本月签到统计
            history = client.get_checkin_history()
            if history and history.get('stats'):
                stats = history['stats']
                checkin_count = stats.get('checkin_count', 0)
                total_quota = stats.get('total_quota', 0)
                if total_quota >= 1000000:
                    total_str = f'{total_quota / 1000000:.2f}M'
                elif total_quota >= 1000:
                    total_str = f'{total_quota / 1000:.2f}K'
                else:
                    total_str = str(total_quota)
                print(f'  统计: 本月已签 {checkin_count} 天，累计 {total_str} 额度')

            # 抽奖（仅 lanxiu.cc 本地运行，GitHub Actions 跳过 — 绑定映射无法持久化）
            lottery_items = []
            if 'lanxiu.cc' in url and lottery_run_for_account and not os.environ.get('GITHUB_ACTIONS'):
                display_name = (user_info or {}).get('username') or account.get('login_username')
                if display_name:
                    for rnd in range(2):
                        prize, err = lottery_run_for_account(
                            client.session, url, display_name)
                        if err:
                            lottery_items.append(f'⏭️ {err}')
                            print(f'  抽奖: ⏭️ {err}')
                            break
                        if prize:
                            q = prize.get('quota_awarded', 0)
                            qs = f'{q/1000000:.2f}M' if q >= 1000000 else f'{q/1000:.2f}K' if q >= 1000 else str(q)
                            line = f'🎉 {prize["prize_name"]} +{qs}'
                            lottery_items.append(line)
                            print(f'  抽奖: {line}')
                            if prize.get('remaining_times', 0) <= 0:
                                break

            # 维云翻卡（本地和 GitHub Actions 都运行，最多 3 次）
            if 'vsllm.com' in url and run_gwent_for_account:
                for rnd in range(3):
                    prize, err = run_gwent_for_account(client.session, url)
                    if err:
                        lottery_items.append(f'⏭️ {err}')
                        print(f'  翻卡: ⏭️ {err}')
                        break
                    if prize:
                        q = prize.get('quota_awarded', 0)
                        qs = f'{q/1000000:.2f}M' if q >= 1000000 else f'{q/1000:.2f}K' if q >= 1000 else str(q)
                        line = f'🎉 第{rnd+1}次 {prize["prize_name"]} +{qs}'
                        lottery_items.append(line)
                        print(f'  翻卡: {line}')

            # 收集结果用于钉钉通知
            account_result = {
                'name': name,
                'success': True,
                'message': result['message'],
                'quota_awarded': result.get('quota_awarded'),
                'checkin_count': checkin_count,
                'lottery': lottery_items
            }
            checkin_results.append(account_result)
        else:
            fail_count += 1
            print(f'  结果: ❌ {result["message"]}')

            # 收集结果用于钉钉通知
            message = result.get('message', '')
            advice = build_advice(message)
            if advice:
                print(f'  💡 建议: {advice}')
            account_result = {
                'name': name,
                'success': False,
                'message': message,
                'session_expired': 'session' in message.lower() or '认证' in message,
                'advice': advice
            }
            checkin_results.append(account_result)

        print()

    # 汇总
    print('=' * 50)
    print(f'签到完成: 成功 {success_count}, 失败 {fail_count}')
    print('=' * 50)
    
    # 通知发送（NOTIFY_ONLY_FAILURE=1 时全部成功则跳过）
    notify_only_fail = os.environ.get('NOTIFY_ONLY_FAILURE', '').strip().lower() in ('1', 'true', 'yes')
    if notify_only_fail and fail_count == 0:
        print('\n[通知] 全部签到成功，已开启「仅失败时推送」，跳过通知')
    elif True:
        pass

    if send_checkin_notification and not (notify_only_fail and fail_count == 0):
        print('正在发送钉钉通知...')
        send_checkin_notification(checkin_results, execution_time)
    elif os.environ.get('DINGTALK_WEBHOOK'):
        print('[警告] 已配置 DINGTALK_WEBHOOK 但无法导入通知模块')

    # 发送邮件通知
    if send_email_notification and os.environ.get('EMAIL_SMTP_HOST') and not (notify_only_fail and fail_count == 0):
        print('正在发送邮件通知...')
        send_email_notification(checkin_results, execution_time)
    elif os.environ.get('EMAIL_SMTP_HOST'):
        print('[警告] 已配置邮件参数但无法导入通知模块')

    # 发送 ServerChan 通知
    if send_serverchan_notification and not (notify_only_fail and fail_count == 0):
        print('正在发送 ServerChan 通知...')
        send_serverchan_notification(checkin_results, execution_time)
    elif os.environ.get('SERVERCHAN_SENDKEY'):
        print('[警告] 已配置 SERVERCHAN_SENDKEY 但无法导入通知模块')

    # 回写 .env（仅限从 .env 加载且 session 有更新的本地运行）
    if from_env_file and session_updated and not os.environ.get('GITHUB_ACTIONS'):
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        print('\n[Session] 检测到 session 已更新，正在回写 .env...')
        new_accounts_str = json.dumps(accounts, ensure_ascii=False)
        with open(env_file, 'r', encoding='utf-8') as f:
            content = f.read()
        marker = 'NEWAPI_ACCOUNTS='
        idx = content.find(marker)
        if idx != -1:
            line_end = content.find('\n', idx)
            if line_end == -1:
                line_end = len(content)
            new_line = marker + new_accounts_str
            new_content = content[:idx] + new_line + content[line_end:]
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print('[Session] .env 已更新')

    # 如果全部失败则返回错误码
    if fail_count == len(accounts):
        sys.exit(1)


if __name__ == '__main__':
    main()

# === DINGTALK NOTIFICATION PATCH ===
# This section was added to send DingTalk notifications