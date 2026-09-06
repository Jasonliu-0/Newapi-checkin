#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GoRouter 单独签到脚本

gorouter.app 的签到接口要求 Cloudflare Turnstile token（交互式人机验证），
在真实 Chrome 中完成: 打开站点 -> 过 CF -> 渲染验证组件 -> 自动点击 -> 页面内签到。
一般情况直接运行 checkin.py 即可（已集成 Turnstile 回退），此脚本用于单独调试。
"""
import io
import json
import os
import re
import sys

from turnstile_solver import solve_and_checkin

BASE = 'https://gorouter.app'


def main():
    with io.open(os.path.join(os.path.dirname(__file__), '.env'), encoding='utf-8') as f:
        env_content = f.read()
    m = re.search(r'^NEWAPI_ACCOUNTS=(.*)$', env_content, re.M)
    accounts = json.loads(m.group(1))
    acc = next((a for a in accounts if 'gorouter' in a.get('url', '')), None)
    if not acc:
        print('.env 中未找到 gorouter 账号')
        sys.exit(1)

    headers = {
        'Authorization': acc['access_token'],
        'New-Api-User': str(acc['user_id']),
    }

    print('[1/2] 启动真实 Chrome（会弹出窗口，自动过 CF + 点击验证框）...')
    result = solve_and_checkin(BASE, auth_headers=headers)

    if not result:
        print('结果: ❌ 未能完成验证或请求失败')
        sys.exit(1)

    message = result.get('message', '未知')
    if result.get('success') or '已签到' in message:
        print(f'[2/2] 结果: ✅ {message}')
        print('数据:', json.dumps(result.get('data', {}), ensure_ascii=False)[:200])
    else:
        print(f'[2/2] 结果: ❌ {message}')
        sys.exit(1)


if __name__ == '__main__':
    main()
