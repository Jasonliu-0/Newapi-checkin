import json
import unittest
from unittest.mock import Mock, patch

from requests import Request

from cf_bypass import detect_cloudflare_block
from checkin import NewAPICheckin, parse_accounts


class NewAPICheckinTests(unittest.TestCase):
    def test_cookies_are_scoped_to_configured_host(self):
        client = NewAPICheckin(
            'https://api.example.com/console',
            'SESSION_SECRET',
            '123',
            'CLEARANCE_SECRET',
        )

        same_host = client.session.prepare_request(Request('GET', 'https://api.example.com/api/user/self'))
        other_host = client.session.prepare_request(Request('GET', 'https://example.org/api/user/self'))

        self.assertEqual(client.base_url, 'https://api.example.com')
        self.assertIn('session=SESSION_SECRET', same_host.headers.get('Cookie', ''))
        self.assertIn('cf_clearance=CLEARANCE_SECRET', same_host.headers.get('Cookie', ''))
        self.assertNotIn('Cookie', other_host.headers)

    def test_rejects_invalid_account_values(self):
        with self.assertRaises(ValueError):
            NewAPICheckin(None, 'session')
        with self.assertRaises(ValueError):
            NewAPICheckin('invalid-url', 'session')
        with self.assertRaises(ValueError):
            NewAPICheckin('https://api.example.com', '')

    def test_localhost_cookie_is_sent_only_to_localhost(self):
        client = NewAPICheckin('http://localhost:8000', 'LOCAL_SESSION', '123')

        local = client.session.prepare_request(Request('GET', 'http://localhost:8000/api/user/self'))
        remote = client.session.prepare_request(Request('GET', 'http://example.org/api/user/self'))

        self.assertIn('session=LOCAL_SESSION', local.headers.get('Cookie', ''))
        self.assertNotIn('Cookie', remote.headers)

    def test_parse_accounts_skips_malformed_items(self):
        accounts = parse_accounts(
            '[{"url": null, "session": "bad"}, '
            '{"url": "https://api.example.com", "session": "good", "user_id": 12}]'
        )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]['user_id'], '12')
        self.assertEqual(parse_accounts('invalid#session,https://api.example.com#,http://[::1#session'), [])

    def test_parse_accounts_preserves_worker_account_id_for_result_reporting(self):
        accounts = parse_accounts(
            '[{"account_id": 42, "name": "主账号", "url": "https://api.example.com", "session": "good"}]'
        )

        self.assertEqual(accounts[0]['account_id'], 42)

    def test_standard_endpoint_falls_back_only_for_not_found(self):
        client = NewAPICheckin('https://api.example.com', 'session', '123')
        missing = Mock(status_code=404)
        missing.json.return_value = {'message': 'not found'}
        success = Mock(status_code=200)
        success.json.return_value = {'success': True, 'message': '签到成功'}
        client.session.post = Mock(side_effect=[missing, success])

        result = client.checkin()

        self.assertTrue(result['success'])
        self.assertEqual(
            [call.args[0] for call in client.session.post.call_args_list],
            [
                'https://api.example.com/api/user/sign_in',
                'https://api.example.com/api/user/checkin',
            ],
        )
        for call in client.session.post.call_args_list:
            self.assertFalse(call.kwargs['allow_redirects'])

    def test_normalizes_string_quota(self):
        result = NewAPICheckin._normalize_checkin_payload({
            'success': True,
            'message': None,
            'data': {'quota_awarded': '1000'},
        })

        self.assertTrue(result['success'])
        self.assertEqual(result['quota_awarded'], 1000)
        self.assertEqual(result['message'], '签到成功')

    @patch('checkin.detect_cloudflare_block', return_value=(True, 'challenge'))
    def test_cloudflare_fallback_receives_blocked_endpoint(self, _detect):
        client = NewAPICheckin('https://api.example.com', 'session', '123')
        blocked = Mock(status_code=403, text='<!doctype html>challenge')
        blocked.json.side_effect = json.JSONDecodeError('not json', '', 0)
        client.session.post = Mock(return_value=blocked)
        client._cf_bypass_checkin = Mock(return_value={'success': False, 'message': 'blocked'})

        client.checkin()

        client._cf_bypass_checkin.assert_called_once_with('/api/user/sign_in')

    @patch('checkin.CloudflareBypasser')
    @patch('checkin.CF_BYPASS_AVAILABLE', True)
    def test_cloudflare_fallback_passes_clearance_cookie_to_browser(self, bypasser_class):
        bypasser = bypasser_class.return_value
        bypasser.is_available.return_value = True
        bypasser.bypass_and_checkin.return_value = {'success': True, 'message': '签到成功'}
        client = NewAPICheckin('https://api.example.com', 'session', '123', 'clearance')

        result = client._cf_bypass_checkin()

        self.assertTrue(result['success'])
        bypasser_class.assert_called_once_with(
            'https://api.example.com', 'session', '123', 'clearance'
        )


class CloudflareDetectionTests(unittest.TestCase):
    def test_detects_doctype_case_variants(self):
        for doctype in ('<!DOCTYPE html>', '<!doctype html>'):
            with self.subTest(doctype=doctype):
                blocked, _ = detect_cloudflare_block(403, f'{doctype}<p>Cloudflare challenge</p>')
                self.assertTrue(blocked)


if __name__ == '__main__':
    unittest.main()
