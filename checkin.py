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
import requests
from datetime import datetime
from typing import Optional


class NewAPICheckin:
    """NewAPI 签到类"""

    def __init__(self, base_url: str, session_cookie: str, user_id: str = None):
        """
        初始化签到实例

        Args:
            base_url: API 基础地址，如 https://example.com
            session_cookie: session cookie 值
            user_id: 用户ID（可选，如果不提供会尝试自动提取）
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.cookies.set('session', session_cookie)
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-store',
            'Pragma': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

        # 设置用户ID
        if user_id:
            self.user_id = user_id
            self.session.headers.update({'new-api-user': str(user_id)})
        else:
            # 尝试从 Session Cookie 中提取用户ID
            self.user_id = self._extract_user_id_from_session(session_cookie)
            if self.user_id:
                self.session.headers.update({'new-api-user': str(self.user_id)})

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
                return None

            # 尝试解析 JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
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

        Returns:
            签到结果字典，包含：
            - success: 是否成功
            - message: 返回消息
            - checkin_date: 签到日期
            - quota_awarded: 获得的额度
        """
        result = {
            'success': False,
            'message': '',
            'checkin_date': None,
            'quota_awarded': None
        }

        try:
            resp = self.session.post(f'{self.base_url}/api/user/checkin', timeout=30)

            # 先检查状态码
            if resp.status_code == 401:
                result['message'] = '认证失败: Session 可能已过期，请重新获取'
                return result

            # 尝试解析 JSON
            try:
                data = resp.json()
            except json.JSONDecodeError:
                # JSON 解析失败，显示原始响应内容
                content_preview = resp.text[:200] if resp.text else '(空响应)'
                result['message'] = f'响应格式错误 (HTTP {resp.status_code}): {content_preview}'
                return result

            if resp.status_code == 200:
                # 根据 API 响应的 success 字段判断
                if data.get('success'):
                    result['success'] = True
                    result['message'] = data.get('message', '签到成功')

                    # 解析签到数据
                    checkin_data = data.get('data', {})
                    result['checkin_date'] = checkin_data.get('checkin_date')
                    result['quota_awarded'] = checkin_data.get('quota_awarded')
                else:
                    result['message'] = data.get('message', '签到失败')
            else:
                result['message'] = f'HTTP {resp.status_code}: {data.get("message", "未知错误")}'

        except requests.exceptions.Timeout:
            result['message'] = '请求超时'
        except requests.exceptions.RequestException as e:
            result['message'] = f'网络请求失败: {e}'
        except Exception as e:
            result['message'] = f'未知错误: {e}'

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
    1. 单账号: BASE_URL#SESSION_COOKIE
    2. 多账号: BASE_URL1#SESSION1,BASE_URL2#SESSION2
    3. JSON格式: [{"url": "...", "session": "..."}]
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
                    accounts.append(account)
            return accounts
    except json.JSONDecodeError:
        pass

    # 简单格式: URL#SESSION,URL#SESSION
    for part in accounts_str.split(','):
        part = part.strip()
        if '#' in part:
            url, session = part.split('#', 1)
            accounts.append({
                'url': url.strip(),
                'session': session.strip(),
                'name': ''
            })

    return accounts


def main():
    """主函数"""
    print('=' * 50)
    print('NewAPI 自动签到')
    print(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 50)

    # 从环境变量获取账号配置
    accounts_str = os.environ.get('NEWAPI_ACCOUNTS', '')

    if not accounts_str:
        print('[错误] 未配置 NEWAPI_ACCOUNTS 环境变量')
        print('配置格式: BASE_URL#SESSION_COOKIE')
        print('多账号用逗号分隔: URL1#SESSION1,URL2#SESSION2')
        sys.exit(1)

    accounts = parse_accounts(accounts_str)

    if not accounts:
        print('[错误] 账号配置解析失败')
        sys.exit(1)

    print(f'共 {len(accounts)} 个账号待签到\n')

    success_count = 0
    fail_count = 0

    for i, account in enumerate(accounts, 1):
        url = account['url']
        session_cookie = account['session']
        user_id = account.get('user_id')  # 获取用户ID（如果提供）
        name = account.get('name') or f'账号{i}'

        print(f'[{i}/{len(accounts)}] {name}')
        print(f'  站点: {url}')
        if user_id:
            print(f'  用户ID: {user_id}')

        client = NewAPICheckin(url, session_cookie, user_id)

        # 获取用户信息
        user_info = client.get_user_info()
        if user_info:
            username = user_info.get('username', '未知')
            print(f'  用户: {username}')
        else:
            print('  用户: 获取失败（可能 session 已过期）')

        # 执行签到
        result = client.checkin()

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
        else:
            fail_count += 1
            print(f'  结果: ❌ {result["message"]}')

        print()

    # 汇总
    print('=' * 50)
    print(f'签到完成: 成功 {success_count}, 失败 {fail_count}')
    print('=' * 50)

    # 如果全部失败则返回错误码
    if fail_count == len(accounts):
        sys.exit(1)


if __name__ == '__main__':
    main()
