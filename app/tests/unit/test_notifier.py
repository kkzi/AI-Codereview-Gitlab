"""单元测试：通知系统"""
import os
import unittest
from unittest.mock import Mock, patch
from app.infra.notify.notifier import send_notification


class TestNotifier(unittest.TestCase):
    @patch('app.infra.notify.notifier.DingTalkNotifier')
    @patch('app.infra.notify.notifier.WeComNotifier')
    @patch('app.infra.notify.notifier.FeishuNotifier')
    @patch('app.infra.notify.notifier.ExtraWebhookNotifier')
    def test_all_notifications_succeed(self, mock_extra, mock_feishu, mock_wecom, mock_dingtalk):
        """测试所有通知成功"""
        os.environ["EXTRA_WEBHOOK_ENABLED"] = "1"
        # 模拟所有通知器成功
        for mock_notifier_class in [mock_dingtalk, mock_wecom, mock_feishu, mock_extra]:
            mock_instance = Mock()
            mock_notifier_class.return_value = mock_instance

        results = send_notification(
            content="Test message",
            msg_type="text",
            title="Test",
        )

        # 验证所有通知都成功
        self.assertEqual(results["dingtalk"], True)
        self.assertEqual(results["wecom"], True)
        self.assertEqual(results["feishu"], True)
        self.assertEqual(results["extra_webhook"], True)

    @patch('app.infra.notify.notifier.DingTalkNotifier')
    @patch('app.infra.notify.notifier.WeComNotifier')
    @patch('app.infra.notify.notifier.FeishuNotifier')
    @patch('app.infra.notify.notifier.ExtraWebhookNotifier')
    def test_partial_notification_failure(self, mock_extra, mock_feishu, mock_wecom, mock_dingtalk):
        """测试部分通知失败"""
        os.environ["EXTRA_WEBHOOK_ENABLED"] = "1"
        # DingTalk 成功
        mock_dingtalk_instance = Mock()
        mock_dingtalk.return_value = mock_dingtalk_instance

        # WeChat 失败
        mock_wecom_instance = Mock()
        mock_wecom_instance.send_message.side_effect = Exception("WeChat error")
        mock_wecom.return_value = mock_wecom_instance

        # Feishu 成功
        mock_feishu_instance = Mock()
        mock_feishu.return_value = mock_feishu_instance

        # Extra webhook 成功
        mock_extra_instance = Mock()
        mock_extra.return_value = mock_extra_instance

        results = send_notification(
            content="Test message",
            msg_type="text",
            title="Test",
        )

        # 验证结果
        self.assertEqual(results["dingtalk"], True)
        self.assertEqual(results["wecom"], False)  # 失败
        self.assertEqual(results["feishu"], True)
        self.assertEqual(results["extra_webhook"], True)

    @patch('app.infra.notify.notifier.DingTalkNotifier')
    @patch('app.infra.notify.notifier.WeComNotifier')
    @patch('app.infra.notify.notifier.FeishuNotifier')
    @patch('app.infra.notify.notifier.ExtraWebhookNotifier')
    def test_all_notifications_fail(self, mock_extra, mock_feishu, mock_wecom, mock_dingtalk):
        """测试所有通知失败"""
        os.environ["EXTRA_WEBHOOK_ENABLED"] = "1"
        # 所有通知器都失败
        for mock_notifier_class in [mock_dingtalk, mock_wecom, mock_feishu, mock_extra]:
            mock_instance = Mock()
            mock_instance.send_message.side_effect = Exception("Network error")
            mock_notifier_class.return_value = mock_instance

        results = send_notification(
            content="Test message",
            msg_type="text",
            title="Test",
        )

        # 验证所有通知都失败
        self.assertEqual(results["dingtalk"], False)
        self.assertEqual(results["wecom"], False)
        self.assertEqual(results["feishu"], False)
        self.assertEqual(results["extra_webhook"], False)


if __name__ == "__main__":
    unittest.main()
