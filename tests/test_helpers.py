import json
import unittest
from unittest.mock import patch

from config_helper import generate_config, test_account as validate_account
from dingtalk_notifier import build_checkin_report


class NotificationTests(unittest.TestCase):
    def test_report_handles_type_drift_and_escapes_table_cells(self):
        report = build_checkin_report([
            {
                'name': 'main|account',
                'success': True,
                'message': None,
                'quota_awarded': '1000',
                'checkin_count': '2',
            },
            {
                'name': 'backup',
                'success': 'false',
                'message': None,
                'session_expired': 'false',
            },
        ], '2026-07-25 08:10:00')

        self.assertIn('main\\|account', report)
        self.assertIn('+1.00K', report)
        self.assertIn('已签 2 天', report)
        self.assertIn('未知错误', report)
        self.assertNotIn('部分账号 Session 已失效', report)


class ConfigHelperTests(unittest.TestCase):
    @patch('checkin.NewAPICheckin')
    def test_account_validation_passes_user_id(self, client_class):
        client_class.return_value.get_user_info.return_value = {'username': 'tester'}

        self.assertTrue(validate_account('https://api.example.com', 'session', '123'))
        client_class.assert_called_once_with('https://api.example.com', 'session', '123')

    def test_generated_config_preserves_user_id(self):
        config = generate_config([{
            'url': 'https://api.example.com',
            'session': 'session',
            'user_id': '123',
            'name': 'main',
        }])

        self.assertEqual(json.loads(config)[0]['user_id'], '123')


if __name__ == '__main__':
    unittest.main()
