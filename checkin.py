#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewAPI 自动签到脚本
支持多账号签到，通过 GitHub Actions 定时执行
"""

import os
import sys
import json
import base64
import math
import requests
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

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
            domain_parts = (parsed.hostname or '').split('.')
            if len(domain_parts) >= 2:
                # 保留第一部分和最后一部分，中间用 *** 代替
                masked_domain = f"{domain_parts[0]}.***." + '.'.join(domain_parts[-1:])
            else:
                masked_domain = '***'
            port = f':{parsed.port}' if parsed.port else ''
            return f"{parsed.scheme}://{masked_domain}{port}"
        except Exception:
            return 'https://***'

    @staticmethod
    def _mask_user_id(user_id: str) -> str:
        """
        脱敏用户ID
        例如: 1429 -> ****
        """
        return '****'

    def __init__(self, base_url: str, session_cookie: str, user_id: str = None, cf_clearance: str = None):
        if not isinstance(base_url, str):
            raise ValueError('站点 URL 必须是字符串')
        parsed_url = urlparse(base_url.strip())
        if parsed_url.scheme not in ('http', 'https') or not parsed_url.hostname:
            raise ValueError('站点 URL 必须是有效的 HTTP(S) 地址')
        if not isinstance(session_cookie, str) or not session_cookie.strip():
            raise ValueError('Session Cookie 不能为空')

        self.base_url = f'{parsed_url.scheme}://{parsed_url.netloc}'
        self.session_cookie = session_cookie
        self.user_id = str(user_id).strip() if user_id is not None and str(user_id).strip() else None
        self.original_cf_clearance = cf_clearance
        self.cf_bypassed = False
        self.last_user_info_error = None
        self.session = requests.Session()
        cookie_domain = parsed_url.hostname if ('.' in parsed_url.hostname or ':' in parsed_url.hostname) else f'{parsed_url.hostname}.local'
        cookie_options = {
            'domain': cookie_domain,
            'path': '/',
            'secure': parsed_url.scheme == 'https',
        }
        self.session.cookies.set('session', session_cookie, **cookie_options)

        if cf_clearance:
            self.session.cookies.set('cf_clearance', cf_clearance, **cookie_options)

        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-store',
            'Pragma': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
            'X-Requested-With': 'XMLHttpRequest',
        })

        if self.user_id:
            self.session.headers.update({'new-api-user': self.user_id})

    def _extract_user_id_from_session(self, session_cookie: str) -> Optional[str]:
        """
        从 Session Cookie 中提取用户ID

        Session Cookie 格式通常是 Base64 编码的数据
        """
        try:
            # 尝试解码 Session Cookie
            # Session 格式类似：MTc2NzQxMzYzM3xE...
            # 解码后可能包含用户信息
            decoded = base64.b64decode(session_cookie + '==')  # 添加 padding
            decoded_str = decoded.decode('utf-8', errors='ignore')

            # 查找可能的用户ID模式
            # 例如：linuxdo_988 中的 988
            import re
            # 查找 "linuxdo_数字" 或 "id"=数字 等模式
            patterns = [
                r'linuxdo[_-](\d+)',  # linuxdo_988
                r'"id"[:\s]+(\d+)',    # "id": 988
                r'user[_-](\d+)',      # user_988
                r'userid[:\s]+(\d+)',  # userid: 988
            ]

            for pattern in patterns:
                match = re.search(pattern, decoded_str, re.IGNORECASE)
                if match:
                    return match.group(1)

        except Exception:
            pass

        return None

    @staticmethod
    def _already_checked_in(message) -> bool:
        if message is None:
            return False
        msg = message if isinstance(message, str) else str(message)
        keywords = (
            '已签到', '已经签到', '今日已签', '重复签到',
            'already checked', 'already check-in', 'already checkin',
        )
        lower = msg.lower()
        return any((k.lower() in lower) if all(ord(c) < 128 for c in k) else (k in msg) for k in keywords)

    @staticmethod
    def _normalize_checkin_payload(data) -> dict:
        """统一解析签到接口，兼容 data=null、嵌套 data 与「已签到」伪失败。"""
        result = {
            'success': False,
            'message': '',
            'checkin_date': None,
            'quota_awarded': None,
            'already_checked_in': False,
        }
        if not isinstance(data, dict):
            result['message'] = f'响应格式错误: {type(data).__name__}'
            return result

        message = data.get('message')
        if message is None:
            message = data.get('msg')
        if message is None and not isinstance(data.get('data'), (dict, list, type(None))):
            message = data.get('data')
        if message is None:
            message = ''
        if not isinstance(message, str):
            try:
                message = json.dumps(message, ensure_ascii=False)
            except Exception:
                message = str(message)

        success_flag = (
            data.get('success') is True
            or data.get('status') == 'success'
            or data.get('ret') == 1
            or data.get('code') == 0
        )
        already = NewAPICheckin._already_checked_in(message)
        result['already_checked_in'] = already
        result['success'] = bool(success_flag or already)
        result['message'] = message or ('签到成功' if result['success'] else '签到失败')

        candidates = []
        payload = data.get('data')
        if isinstance(payload, dict):
            candidates.append(payload)
            if isinstance(payload.get('data'), dict):
                candidates.append(payload['data'])
        candidates.append(data)
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if result['checkin_date'] is None and item.get('checkin_date') is not None:
                result['checkin_date'] = item.get('checkin_date')
            if result['quota_awarded'] is None and item.get('quota_awarded') is not None:
                result['quota_awarded'] = NewAPICheckin._coerce_number(item.get('quota_awarded'))
        return result

    @staticmethod
    def _coerce_number(value, default=None):
        if value is None or isinstance(value, bool):
            return default
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        return int(number) if number.is_integer() else number

    def get_user_info(self, verbose: bool = False) -> Optional[dict]:
        """
        获取用户信息

        自动设置 new-api-user 请求头

        Args:
            verbose: 是否显示详细调试信息
        """
        self.last_user_info_error = None
        try:
            resp = self.session.get(f'{self.base_url}/api/user/self', timeout=30, allow_redirects=False)

            if verbose:
                print(f'  [调试] HTTP 状态码: {resp.status_code}')
                print(f'  [调试] 响应内容预览: {resp.text[:200]}...')

            # 检查认证失败
            if resp.status_code == 401:
                self.last_user_info_error = 'session'
                print(f'[错误] 认证失败 (401): Session 可能已过期')
                if verbose:
                    print(f'  [调试] 完整响应: {resp.text[:500]}')
                return None

            # 尝试解析 JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                # 检测是否是 Cloudflare 拦截
                if detect_cloudflare_block:
                    is_blocked, reason = detect_cloudflare_block(resp.status_code, resp.text)
                    if is_blocked:
                        self.last_user_info_error = 'cloudflare'
                        print(f'[CF] 获取用户信息时检测到 Cloudflare 拦截: {reason}')
                        print(f'[CF] 该站点需要 CF 绕过才能访问')
                        return None
                print(f'[错误] 响应格式错误 (HTTP {resp.status_code}): 无法解析 JSON')
                self.last_user_info_error = 'response'
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
                    self.last_user_info_error = 'api'
                    if verbose:
                        print(f'  [调试] API 返回失败: {data.get("message", "未知错误")}')
            else:
                self.last_user_info_error = 'http'
                print(f'[错误] HTTP {resp.status_code}: {data.get("message", "未知错误")}')

            return None

        except requests.exceptions.Timeout:
            self.last_user_info_error = 'network'
            print(f'[错误] 请求超时')
            return None
        except requests.exceptions.RequestException as e:
            self.last_user_info_error = 'network'
            print(f'[错误] 网络请求失败: {e}')
            return None
        except Exception as e:
            self.last_user_info_error = 'unknown'
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

        if not self.user_id:
            result['message'] = '缺少用户 ID：请在控制台填写浏览器请求头 new-api-user 的值后重试'
            return result

        try:
            # NewAPI/OneAPI 的标准签到端点是 sign_in；checkin 仅保留给旧实现。
            for path in ('/api/user/sign_in', '/api/user/checkin'):
                resp = self.session.post(f'{self.base_url}{path}', timeout=30, allow_redirects=False)

                if resp.status_code in (404, 405) and path == '/api/user/sign_in':
                    continue
                if resp.status_code == 401:
                    result['message'] = '认证失败: Session 可能已过期或用户 ID 不匹配，请重新获取'
                    return result

                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    if detect_cloudflare_block:
                        is_blocked, reason = detect_cloudflare_block(resp.status_code, resp.text)
                        if is_blocked:
                            print(f'[CF] 签到接口被 Cloudflare 拦截: {reason}')
                            return self._cf_bypass_checkin(path)
                    content_preview = resp.text[:200] if resp.text else '(空响应)'
                    result['message'] = f'响应格式错误 (HTTP {resp.status_code}): {content_preview}'
                    return result

                if resp.status_code == 200:
                    normalized = self._normalize_checkin_payload(data)
                    result['success'] = normalized['success']
                    result['message'] = normalized['message']
                    result['checkin_date'] = normalized['checkin_date']
                    result['quota_awarded'] = normalized['quota_awarded']
                    return result

                message = data.get('message') or data.get('msg') or '未知错误'
                if self._already_checked_in(message):
                    result['success'] = True
                    result['message'] = message
                else:
                    result['message'] = f'HTTP {resp.status_code}: {message}'
                return result

        except requests.exceptions.Timeout:
            result['message'] = '请求超时'
        except requests.exceptions.RequestException as e:
            result['message'] = f'网络请求失败: {e}'
        except Exception as e:
            result['message'] = f'未知错误: {e}'

        return result

    def _cf_bypass_checkin(self, path: str = '/api/user/sign_in') -> dict:
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

        bypasser = CloudflareBypasser(self.base_url, self.session_cookie, self.user_id)

        if not bypasser.is_available():
            result['message'] = 'Cloudflare 拦截: Playwright 未正确安装'
            return result

        print('[CF] 开始 Playwright 绕过流程...')
        browser_result = bypasser.bypass_and_checkin(path)

        if not browser_result:
            result['message'] = 'Cloudflare 绕过失败: 无法通过 CF 验证'
            return result

        self.cf_bypassed = True

        if browser_result.get('error'):
            error = browser_result['error']
            if 'Just a moment' in error or 'challenge-platform' in error or 'cf-challenge' in error:
                result['message'] = 'Cloudflare 验证仍在进行：签到接口返回挑战页 HTML'
            else:
                result['message'] = f'CF 回退后签到失败: {error}'
            return result

        # Playwright 返回: {success, alreadyCheckedIn, message, data: <API JSON>}
        api_data = browser_result.get('data')
        if not isinstance(api_data, dict):
            api_data = {
                'success': browser_result.get('success'),
                'message': browser_result.get('message'),
            }

        normalized = self._normalize_checkin_payload(api_data)
        if browser_result.get('alreadyCheckedIn') or browser_result.get('success') or normalized['success']:
            result['success'] = True
            result['message'] = (
                browser_result.get('message')
                or normalized['message']
                or ('今日已签到 (CF绕过)' if browser_result.get('alreadyCheckedIn') else '签到成功 (CF绕过)')
            )
            result['checkin_date'] = normalized['checkin_date']
            result['quota_awarded'] = normalized['quota_awarded']
        else:
            result['message'] = browser_result.get('message') or normalized['message'] or 'CF 绕过后签到失败'

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
                timeout=30,
                allow_redirects=False,
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
    1. 单账号: BASE_URL#SESSION_COOKIE
    2. 多账号: BASE_URL1#SESSION1,BASE_URL2#SESSION2
    3. JSON格式: [{"url": "...", "session": "..."}]
    """
    accounts = []

    def valid_account(url, session) -> bool:
        if not isinstance(url, str) or not url.strip() or not isinstance(session, str) or not session.strip():
            return False
        try:
            parsed = urlparse(url.strip())
            return parsed.scheme in ('http', 'https') and bool(parsed.hostname)
        except ValueError:
            return False

    if not accounts_str:
        return accounts

    # 尝试 JSON 格式
    try:
        data = json.loads(accounts_str)
        if isinstance(data, list):
            for item in data:
                if (
                    isinstance(item, dict)
                    and valid_account(item.get('url'), item.get('session'))
                ):
                    account = {
                        'url': item['url'].strip(),
                        'session': item['session'].strip(),
                        'name': str(item.get('name') or '')
                    }
                    # 如果提供了 user_id，添加到账号信息中
                    if item.get('user_id') is not None:
                        account['user_id'] = str(item['user_id']).strip()
                    # 如果提供了 cf_clearance，添加到账号信息中
                    if isinstance(item.get('cf_clearance'), str) and item['cf_clearance'].strip():
                        account['cf_clearance'] = item['cf_clearance'].strip()
                    accounts.append(account)
            return accounts
    except json.JSONDecodeError:
        pass

    # 简单格式: URL#SESSION,URL#SESSION
    for part in accounts_str.split(','):
        part = part.strip()
        if '#' in part:
            url, session = part.split('#', 1)
            if valid_account(url, session):
                accounts.append({
                    'url': url.strip(),
                    'session': session.strip(),
                    'name': ''
                })

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


def load_config_from_worker(worker_url: str, runner_token: str) -> Optional[str]:
    """从 Cloudflare Worker 获取加密保存的账号配置。"""
    if not worker_url or not runner_token:
        return None

    try:
        print('[Worker] 正在获取启用账号配置...')
        resp = requests.get(
            f'{worker_url.rstrip("/")}/api/runner/config',
            headers={'Authorization': f'Bearer {runner_token}'},
            timeout=30
        )
        if resp.status_code != 200:
            try:
                error = resp.json().get('error', resp.text[:200])
            except json.JSONDecodeError:
                error = resp.text[:200]
            print(f'[Worker] 获取配置失败: HTTP {resp.status_code} - {error}')
            return None
        data = resp.json()
        accounts = data.get('accounts') if isinstance(data, dict) else None
        if not isinstance(accounts, list):
            print('[Worker] 配置响应格式错误')
            return None
        if not accounts:
            print('[Worker] 没有启用的签到账号，请先在 Worker 控制台添加或启用账号')
            return None
        print(f'[Worker] 成功获取 {len(accounts)} 个账号配置')
        return json.dumps(accounts)
    except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
        print(f'[Worker] 获取配置失败: {exc}')
        return None


def report_results_to_worker(worker_url: str, runner_token: str, execution_time: str,
                             results: list, total: int, success_count: int,
                             fail_count: int) -> bool:
    """将本次执行结果上报到 Cloudflare Worker。"""
    if not worker_url or not runner_token:
        return False

    payload = {
        'execution_time': execution_time,
        'total': total,
        'success_count': success_count,
        'fail_count': fail_count,
        'results': results,
    }
    try:
        resp = requests.post(
            f'{worker_url.rstrip("/")}/api/runner/report',
            headers={
                'Authorization': f'Bearer {runner_token}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=30
        )
        if resp.status_code in (200, 201):
            print('[Worker] 签到结果上报成功')
            return True
        try:
            error = resp.json().get('error', resp.text[:200])
        except json.JSONDecodeError:
            error = resp.text[:200]
        print(f'[Worker] 签到结果上报失败: HTTP {resp.status_code} - {error}')
    except requests.exceptions.RequestException as exc:
        print(f'[Worker] 签到结果上报失败: {exc}')
    return False


def main():
    """主函数"""
    import pytz
    beijing_tz = pytz.timezone('Asia/Shanghai')
    execution_time = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")
    print('=' * 50)
    print('NewAPI 自动签到')
    print(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 50)

    config_url = os.environ.get('CONFIG_URL', '')
    config_auth = os.environ.get('CONFIG_AUTH', '')
    worker_url = os.environ.get('CHECKIN_WORKER_URL', '')
    runner_token = os.environ.get('CHECKIN_RUNNER_TOKEN', '')

    accounts_str = ''

    if worker_url and runner_token:
        accounts_str = load_config_from_worker(worker_url, runner_token) or ''

    if not accounts_str and config_url:
        accounts_str = load_config_from_cloud(config_url, config_auth) or ''

    if not accounts_str:
        accounts_str = os.environ.get('NEWAPI_ACCOUNTS', '')

    if not accounts_str:
        print('[错误] 未配置账号信息')
        print('请设置 CHECKIN_WORKER_URL 和 CHECKIN_RUNNER_TOKEN 环境变量')
        sys.exit(1)

    accounts = parse_accounts(accounts_str)

    if not accounts:
        print('[错误] 账号配置解析失败')
        sys.exit(1)

    print(f'共 {len(accounts)} 个账号待签到\n')

    success_count = 0
    fail_count = 0
    checkin_results = []

    for i, account in enumerate(accounts, 1):
        url = account['url']
        session_cookie = account['session']
        user_id = account.get('user_id')  # 获取用户ID（如果提供）
        cf_clearance = account.get('cf_clearance')  # 获取 CF clearance（如果提供）
        name = account.get('name') or f'账号{i}'

        print(f'[{i}/{len(accounts)}] {name}')
        print(f'  站点: {NewAPICheckin._mask_url(url)}')
        if user_id:
            print(f'  用户ID: {NewAPICheckin._mask_user_id(user_id)}')

        client = NewAPICheckin(url, session_cookie, user_id, cf_clearance)

        # 获取用户信息
        user_info = client.get_user_info()
        if user_info:
            username = user_info.get('username', '未知')
            # 用户名也脱敏，只显示前3个字符
            masked_username = username[:3] + '***' if len(username) > 3 else '***'
            print(f'  用户: {masked_username}')
        else:
            if client.last_user_info_error == 'cloudflare':
                print('  用户: 获取失败（Cloudflare 拦截）')
            elif client.last_user_info_error == 'session':
                print('  用户: 获取失败（Session 已失效或用户 ID 不匹配）')
            else:
                print('  用户: 获取失败（用户信息接口异常）')

        # 执行签到
        result = client.checkin()
        checkin_count = 0  # 默认值，避免历史接口失败时未定义

        if result['success']:
            success_count += 1
            print(f'  结果: ✅ {result["message"]}')

            # 显示签到日期
            if result['checkin_date']:
                print(f'  日期: {result["checkin_date"]}')

            # 显示获得的额度（格式化显示）
            quota = NewAPICheckin._coerce_number(result.get('quota_awarded'))
            if quota:
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
                checkin_count = NewAPICheckin._coerce_number(stats.get('checkin_count'), 0)
                total_quota = NewAPICheckin._coerce_number(stats.get('total_quota'), 0)
                if total_quota >= 1000000:
                    total_str = f'{total_quota / 1000000:.2f}M'
                elif total_quota >= 1000:
                    total_str = f'{total_quota / 1000:.2f}K'
                else:
                    total_str = str(total_quota)
                print(f'  统计: 本月已签 {checkin_count} 天，累计 {total_str} 额度')

            # 收集结果用于钉钉通知
            account_result = {
                'account_id': account.get('account_id'),
                'name': name,
                'success': True,
                'message': str(result.get('message') or ''),
                'quota_awarded': quota,
                'checkin_count': checkin_count
            }
            checkin_results.append(account_result)
        else:
            fail_count += 1
            print(f'  结果: ❌ {result["message"]}')

            # 收集结果用于钉钉通知
            message = str(result.get('message') or '')
            account_result = {
                'account_id': account.get('account_id'),
                'name': name,
                'success': False,
                'message': message,
                'session_expired': 'session' in message.lower() or '认证' in message
            }
            checkin_results.append(account_result)

        print()

    # 汇总
    print('=' * 50)
    print(f'签到完成: 成功 {success_count}, 失败 {fail_count}')
    print('=' * 50)
    
    # 发送钉钉通知
    if send_checkin_notification:
        print('正在发送钉钉通知...')
        send_checkin_notification(checkin_results, execution_time)
    elif os.environ.get('DINGTALK_WEBHOOK'):
        print('[警告] 已配置 DINGTALK_WEBHOOK 但无法导入通知模块')

    report_results_to_worker(
        worker_url, runner_token, execution_time, checkin_results,
        len(accounts), success_count, fail_count
    )

    # 如果全部失败则返回错误码
    if fail_count == len(accounts):
        sys.exit(1)


if __name__ == '__main__':
    main()
