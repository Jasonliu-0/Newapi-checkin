# -*- coding: utf-8 -*-
"""
通知推送模块
支持邮件推送和 ServerChan 推送
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import requests
except ImportError:
    requests = None


def format_quota(quota: int) -> str:
    """格式化额度显示"""
    if quota >= 1000000:
        return f'{quota / 1000000:.2f}M'
    elif quota >= 1000:
        return f'{quota / 1000:.2f}K'
    else:
        return str(quota)


def build_report_text(results: List[Dict[str, Any]], execution_time: str) -> str:
    """构建纯文本报告内容"""
    success_list = [r for r in results if r.get('success')]
    fail_list = [r for r in results if not r.get('success')]

    lines = [
        'NewAPI 签到报告',
        f'执行时间: {execution_time}',
        '',
        '-' * 40,
        ''
    ]

    if success_list:
        lines.append(f'✓ 成功 ({len(success_list)}个):')
        for r in success_list:
            name = r.get('name', '未知账号')
            quota = r.get('quota_awarded') or 0
            quota_str = f'+{format_quota(quota)}' if quota > 0 else '-'
            checkin_count = r.get('checkin_count')
            detail = f'已签 {checkin_count} 天' if checkin_count else r.get('message', '成功')
            lottery = ' / '.join(r.get('lottery', [])) or '-'
            lines.append(f'  {name} | {quota_str} | {detail} | {lottery}')
        lines.append('')

    if fail_list:
        lines.append(f'✗ 失败 ({len(fail_list)}个):')
        for r in fail_list:
            name = r.get('name', '未知账号')
            message = r.get('message', '未知错误')
            if r.get('session_expired') or 'session' in message.lower() or '认证' in message:
                message = f'[Session失效] {message}'
            lines.append(f'  {name} | {message}')
            if r.get('advice'):
                lines.append(f'  💡 建议: {r["advice"]}')
        lines.append('')

    lines.append('-' * 40)
    total = len(results)
    success_count = len(success_list)
    fail_count = len(fail_list)

    if fail_count == 0:
        lines.append(f'汇总: 全部成功 ({success_count}/{total})')
    elif success_count == 0:
        lines.append(f'汇总: 全部失败 ({fail_count}/{total})')
    else:
        lines.append(f'汇总: 成功 {success_count}，失败 {fail_count}')

    expired_accounts = [r for r in fail_list if r.get('session_expired') or
                        'session' in r.get('message', '').lower() or
                        '认证' in r.get('message', '')]
    if expired_accounts:
        lines.append('')
        lines.append('注意: 部分账号 Session 已失效，请及时更新 Cookie！')

    return '\n'.join(lines)


def build_report_html(results: List[Dict[str, Any]], execution_time: str) -> str:
    """构建 HTML 格式报告"""
    success_list = [r for r in results if r.get('success')]
    fail_list = [r for r in results if not r.get('success')]

    rows = ''

    if success_list:
        rows += '<tr><td colspan="3" style="background:#f0fff4;font-weight:bold;padding:6px 10px;">'
        rows += f'✅ 成功 ({len(success_list)}个)</td></tr>'
        for r in success_list:
            name = r.get('name', '未知账号')
            quota = r.get('quota_awarded') or 0
            quota_str = f'+{format_quota(quota)}' if quota > 0 else '-'
            checkin_count = r.get('checkin_count')
            detail = f'已签 {checkin_count} 天' if checkin_count else r.get('message', '成功')
            lottery = ' / '.join(r.get('lottery', [])) or '-'
            rows += f'<tr><td style="padding:4px 10px;">{name}</td>'
            rows += f'<td style="padding:4px 10px;">{quota_str}</td>'
            rows += f'<td style="padding:4px 10px;">{detail}</td>'
            rows += f'<td style="padding:4px 10px;">{lottery}</td></tr>'

    if fail_list:
        rows += '<tr><td colspan="4" style="background:#fff5f5;font-weight:bold;padding:6px 10px;">'
        rows += f'❌ 失败 ({len(fail_list)}个)</td></tr>'
        for r in fail_list:
            name = r.get('name', '未知账号')
            message = r.get('message', '未知错误')
            if r.get('session_expired') or 'session' in message.lower() or '认证' in message:
                message = f'⚠️ {message}'
            rows += f'<tr><td style="padding:4px 10px;">{name}</td>'
            rows += f'<td colspan="2" style="padding:4px 10px;color:#e53e3e;">{message}</td></tr>'
            if r.get('advice'):
                rows += (f'<tr><td colspan="3" style="padding:2px 10px 6px;color:#718096;font-size:12px;">'
                         f'💡 {r["advice"]}</td></tr>')

    total = len(results)
    success_count = len(success_list)
    fail_count = len(fail_list)

    if fail_count == 0:
        summary = f'✅ 全部成功 ({success_count}/{total})'
    elif success_count == 0:
        summary = f'❌ 全部失败 ({fail_count}/{total})'
    else:
        summary = f'成功 {success_count}，失败 {fail_count}'

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:20px;color:#333;">
<div style="max-width:600px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
<div style="background:#667eea;padding:16px 20px;">
<h2 style="margin:0;color:#fff;font-size:18px;">📋 NewAPI 签到报告</h2>
</div>
<div style="padding:16px 20px;">
<p style="color:#718096;font-size:14px;margin:0 0 12px 0;">执行时间: {execution_time}</p>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
{rows}
</table>
<hr style="border:none;border-top:1px solid #e2e8f0;margin:12px 0;">
<p style="font-size:14px;margin:0;"><strong>{summary}</strong></p>
'''
    expired_accounts = [r for r in fail_list if r.get('session_expired') or
                        'session' in r.get('message', '').lower() or
                        '认证' in r.get('message', '')]
    if expired_accounts:
        html += '<p style="color:#e53e3e;font-size:13px;margin:8px 0 0 0;">⚠️ 部分账号 Session 已失效，请及时更新 Cookie！</p>'

    html += '''
</div>
</div>
</body>
</html>'''
    return html


def send_email_notification(results: List[Dict[str, Any]], execution_time: Optional[str] = None) -> bool:
    """
    发送邮件通知

    环境变量配置:
        EMAIL_SMTP_HOST: SMTP 服务器地址
        EMAIL_SMTP_PORT: SMTP 服务器端口 (默认 465)
        EMAIL_USER: SMTP 用户名
        EMAIL_PASS: SMTP 密码/授权码
        EMAIL_TO: 收件人地址
        EMAIL_FROM: 发件人地址 (可选，默认与 EMAIL_USER 相同)
    """
    host = os.environ.get('EMAIL_SMTP_HOST', '')
    port_str = os.environ.get('EMAIL_SMTP_PORT', '465')
    port = int(port_str) if port_str else 465
    user = os.environ.get('EMAIL_USER', '')
    password = os.environ.get('EMAIL_PASS', '')
    to_addr = os.environ.get('EMAIL_TO', '')
    from_addr = os.environ.get('EMAIL_FROM', user)

    if not all([host, user, password, to_addr]):
        print('[邮件通知] 未完整配置邮件参数 (EMAIL_SMTP_HOST/USER/PASS/TO)，跳过通知')
        return False

    if not execution_time:
        execution_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    success_count = len([r for r in results if r.get('success')])
    fail_count = len([r for r in results if not r.get('success')])

    # 构建邮件标题
    if fail_count == 0:
        subject = f'✅ NewAPI 签到成功 ({success_count}个账号)'
    elif success_count == 0:
        subject = f'❌ NewAPI 签到失败 ({fail_count}个账号)'
    else:
        subject = f'📋 NewAPI 签到完成 (成功{success_count}/失败{fail_count})'

    text_content = build_report_text(results, execution_time)
    html_content = build_report_html(results, execution_time)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        print(f'[邮件通知] 发送成功 -> {to_addr}')
        return True
    except Exception as e:
        print(f'[邮件通知] 发送失败: {e}')
        return False


def send_serverchan_notification(results: List[Dict[str, Any]], execution_time: Optional[str] = None) -> bool:
    """
    发送 ServerChan 推送

    环境变量配置:
        SERVERCHAN_SENDKEY: ServerChan SendKey (https://sctapi.ftqq.com/SENDKEY.send)
    """
    send_key = os.environ.get('SERVERCHAN_SENDKEY', '')

    if not send_key:
        print('[ServerChan] 未配置 SERVERCHAN_SENDKEY，跳过通知')
        return False

    if requests is None:
        print('[ServerChan] 错误: 未安装 requests 库')
        return False

    if not execution_time:
        execution_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    success_count = len([r for r in results if r.get('success')])
    fail_count = len([r for r in results if not r.get('success')])

    # 构建标题
    if fail_count == 0:
        title = f'✅ NewAPI 签到成功 ({success_count}个账号)'
    elif success_count == 0:
        title = f'❌ NewAPI 签到失败 ({fail_count}个账号)'
    else:
        title = f'📋 NewAPI 签到完成 (成功{success_count}/失败{fail_count})'

    # 构建 Markdown 内容
    lines = []

    # 头部
    lines.append(f'**执行时间**: {execution_time}')
    lines.append('')

    # 成功列表
    success_list = [r for r in results if r.get('success')]
    if success_list:
        lines.append(f'### ✅ 成功 ({len(success_list)}个)')
        lines.append('')
        lines.append('| 账号 | 奖励 | 结果 | 已签 | 抽奖 |')
        lines.append('|------|------|------|------|------|')
        for r in success_list:
            name = r.get('name', '未知账号')
            quota = r.get('quota_awarded') or 0
            quota_str = f'+{format_quota(quota)}' if quota > 0 else '-'
            message = r.get('message', '成功')
            checkin_count = r.get('checkin_count')
            days = f'已签 {checkin_count} 天' if checkin_count else '-'
            lottery = ' / '.join(r.get('lottery', [])) or '-'
            lines.append(f'| {name} | {quota_str} | {message} | {days} | {lottery} |')
        lines.append('')

    # 失败列表
    fail_list_local = [r for r in results if not r.get('success')]
    if fail_list_local:
        lines.append(f'### ❌ 失败 ({len(fail_list_local)}个)')
        lines.append('')
        lines.append('| 账号 | 原因 |')
        lines.append('|------|------|')
        for r in fail_list_local:
            name = r.get('name', '未知账号')
            message = r.get('message', '未知错误')
            if r.get('session_expired') or 'session' in message.lower() or '认证' in message:
                message = f'⚠️ {message}'
            lines.append(f'| {name} | {message} |')
        lines.append('')

    # 汇总
    total = len(results)

    if fail_count == 0:
        lines.append(f'**汇总**: 全部成功 ✨ ({success_count}/{total})')
    elif success_count == 0:
        lines.append(f'**汇总**: 全部失败 ⚠️ ({fail_count}/{total})')
    else:
        lines.append(f'**汇总**: 成功 {success_count}，失败 {fail_count}')

    expired_accounts = [r for r in results if not r.get('success') and (
        r.get('session_expired') or
        'session' in r.get('message', '').lower() or
        '认证' in r.get('message', '')
    )]
    if expired_accounts:
        lines.append('')
        lines.append('> ⚠️ **注意**: 部分账号 Session 已失效，请及时更新 Cookie！')

    content = '\n'.join(lines)

    url = f'https://sctapi.ftqq.com/{send_key}.send'

    try:
        resp = requests.post(url, data={
            'title': title,
            'desp': content
        }, timeout=15)
        result = resp.json()
        if result.get('code') == 0:
            print(f'[ServerChan] 推送成功')
            return True
        else:
            print(f'[ServerChan] 推送失败: {result.get("message", "未知错误")}')
            return False
    except Exception as e:
        print(f'[ServerChan] 推送异常: {e}')
        return False
