# -*- coding: utf-8 -*-
"""
钉钉通知模块
用于发送签到结果到钉钉群机器人
"""

import hmac
import hashlib
import base64
import time
import urllib.parse
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import requests
except ImportError:
    requests = None

from notifier import format_quota


class DingTalkNotifier:
    """钉钉机器人通知类"""
    
    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        """
        初始化钉钉通知器
        
        Args:
            webhook_url: 钉钉机器人的 Webhook URL
            secret: 可选的签名密钥（如果机器人开启了加签安全设置）
        """
        self.webhook_url = webhook_url
        self.secret = secret
    
    def _get_sign(self) -> tuple:
        """
        生成签名
        
        Returns:
            (timestamp, sign) 元组
        """
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign
    
    def _get_url(self) -> str:
        """
        获取完整的请求 URL（包含签名参数）
        
        Returns:
            完整的 Webhook URL
        """
        if self.secret:
            timestamp, sign = self._get_sign()
            return f'{self.webhook_url}&timestamp={timestamp}&sign={sign}'
        return self.webhook_url
    
    def send_text(self, content: str, at_mobiles: Optional[List[str]] = None, at_all: bool = False) -> bool:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            at_mobiles: 需要 @ 的手机号列表
            at_all: 是否 @ 所有人
            
        Returns:
            是否发送成功
        """
        if requests is None:
            print('[钉钉通知] 错误: 未安装 requests 库')
            return False
            
        data = {
            'msgtype': 'text',
            'text': {
                'content': content
            },
            'at': {
                'atMobiles': at_mobiles or [],
                'isAtAll': at_all
            }
        }
        return self._send(data)
    
    def send_markdown(self, title: str, text: str, at_mobiles: Optional[List[str]] = None, at_all: bool = False) -> bool:
        """
        发送 Markdown 消息
        
        Args:
            title: 消息标题（会话列表显示）
            text: Markdown 格式的消息内容
            at_mobiles: 需要 @ 的手机号列表
            at_all: 是否 @ 所有人
            
        Returns:
            是否发送成功
        """
        if requests is None:
            print('[钉钉通知] 错误: 未安装 requests 库')
            return False
            
        data = {
            'msgtype': 'markdown',
            'markdown': {
                'title': title,
                'text': text
            },
            'at': {
                'atMobiles': at_mobiles or [],
                'isAtAll': at_all
            }
        }
        return self._send(data)
    
    def _send(self, data: dict) -> bool:
        """
        发送消息到钉钉
        
        Args:
            data: 消息数据
            
        Returns:
            是否发送成功
        """
        try:
            url = self._get_url()
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                print('[钉钉通知] 消息发送成功')
                return True
            else:
                print(f'[钉钉通知] 发送失败: {result.get("errmsg", "未知错误")}')
                return False
        except Exception as e:
            print(f'[钉钉通知] 发送异常: {e}')
            return False


def build_checkin_report(results: List[Dict[str, Any]], execution_time: str) -> str:
    """
    构建签到报告 Markdown 内容
    
    Args:
        results: 签到结果列表，每个结果包含:
            - name: 账号名称
            - success: 是否成功
            - message: 结果消息
            - quota_awarded: 获得的额度（可选）
            - checkin_count: 本月签到天数（可选）
            - session_expired: 是否 session 失效（可选）
        execution_time: 执行时间字符串
        
    Returns:
        Markdown 格式的报告内容
    """
    success_list = [r for r in results if r.get('success')]
    fail_list = [r for r in results if not r.get('success')]
    
    # 标题
    lines = [
        '# 📋 NewAPI 签到报告',
        '',
        f'**执行时间**: {execution_time}',
        '',
        '---',
        ''
    ]
    
    # 成功列表
    if success_list:
        lines.append(f'## ✅ 成功 ({len(success_list)}个)')
        lines.append('')
        lines.append('| 账号 | 奖励 | 详情 | 抽奖 |')
        lines.append('|------|------|------|------|')
        for r in success_list:
            name = r.get('name', '未知账号')
            quota = r.get('quota_awarded', 0)
            quota_str = f'+{format_quota(quota)}' if quota else '-'
            checkin_count = r.get('checkin_count')
            detail = f'已签 {checkin_count} 天' if checkin_count else r.get('message', '成功')
            lottery = '<br/>'.join(r.get('lottery', [])) or '-'
            lines.append(f'| {name} | {quota_str} | {detail} | {lottery} |')
        lines.append('')
    
    # 失败列表
    if fail_list:
        lines.append(f'## ❌ 失败 ({len(fail_list)}个)')
        lines.append('')
        lines.append('| 账号 | 原因 |')
        lines.append('|------|------|')
        for r in fail_list:
            name = r.get('name', '未知账号')
            message = r.get('message', '未知错误')
            # 标注 session 失效
            if r.get('session_expired') or 'session' in message.lower() or '认证' in message or '过期' in message:
                message = f'⚠️ {message}'
            lines.append(f'| {name} | {message} |')
            if r.get('advice'):
                lines.append(f'> 💡 {r["advice"]}')
        lines.append('')
    
    # 汇总
    lines.append('---')
    lines.append('')
    
    total = len(results)
    success_count = len(success_list)
    fail_count = len(fail_list)
    
    if fail_count == 0:
        lines.append(f'**汇总**: 全部成功 ✨ ({success_count}/{total})')
    elif success_count == 0:
        lines.append(f'**汇总**: 全部失败 ⚠️ ({fail_count}/{total})')
    else:
        lines.append(f'**汇总**: 成功 {success_count}，失败 {fail_count}')
    
    # 如果有 session 失效的账号，添加提醒
    expired_accounts = [r for r in fail_list if r.get('session_expired') or 
                       'session' in r.get('message', '').lower() or 
                       '认证' in r.get('message', '') or 
                       '过期' in r.get('message', '')]
    if expired_accounts:
        lines.append('')
        lines.append('> ⚠️ **注意**: 部分账号 Session 已失效，请及时更新 Cookie！')
    
    return '\n'.join(lines)


def send_checkin_notification(results: List[Dict[str, Any]], execution_time: Optional[str] = None) -> bool:
    """
    发送签到通知到钉钉
    
    Args:
        results: 签到结果列表
        execution_time: 执行时间（可选，默认使用当前时间）
        
    Returns:
        是否发送成功
    """
    # 从环境变量获取配置
    webhook_url = os.environ.get('DINGTALK_WEBHOOK', '')
    secret = os.environ.get('DINGTALK_SECRET', '')
    
    if not webhook_url:
        print('[钉钉通知] 未配置 DINGTALK_WEBHOOK，跳过通知')
        return False
    
    # 默认执行时间
    if not execution_time:
        execution_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 构建报告
    report = build_checkin_report(results, execution_time)
    
    # 生成标题（用于消息列表预览）
    success_count = len([r for r in results if r.get('success')])
    fail_count = len([r for r in results if not r.get('success')])
    
    if fail_count == 0:
        title = f'✅ 签到成功 ({success_count}个账号)'
    elif success_count == 0:
        title = f'❌ 签到失败 ({fail_count}个账号)'
    else:
        title = f'📋 签到完成 (成功{success_count}/失败{fail_count})'
    
    # 发送通知
    notifier = DingTalkNotifier(webhook_url, secret if secret else None)
    return notifier.send_markdown(title, report)



