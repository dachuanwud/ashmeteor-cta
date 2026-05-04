import os
import unittest


class AdminTemplateSchemaTest(unittest.TestCase):
    def test_admin_html_loads_shared_admin_schema(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        admin_html = os.path.join(project_root, 'templates', 'admin.html')
        admin_json = os.path.join(project_root, 'templates', 'admin.json')

        with open(admin_html, encoding='utf-8') as f:
            html = f.read()
        with open(admin_json, encoding='utf-8') as f:
            schema = f.read()

        self.assertIn('"title": "统一账户驾驶舱"', schema)
        self.assertIn('"title": "账户资金"', schema)
        self.assertIn('"title": "资产归属"', schema)
        self.assertIn('"title": "杠杆负债"', schema)
        self.assertIn('"title": "半套与 CTA 风险"', schema)
        self.assertIn('现货/杠杆底仓', schema)
        self.assertIn('当前半套和 CTA 仍是两套逻辑', schema)
        self.assertIn('"id": "u:unified_base_asset_buy_wizard"', schema)
        self.assertIn('"title": "1 预览"', schema)
        self.assertIn('"title": "2 确认执行"', schema)
        self.assertIn('启动统一账户半套', schema)
        self.assertIn('停止统一账户半套', schema)
        self.assertIn('强制半套', schema)
        self.assertIn('/cta/unified/margin_rebalance/start', schema)
        self.assertIn('/cta/unified/margin_rebalance/stop', schema)
        self.assertIn('/cta/unified/margin_rebalance/force', schema)
        self.assertIn('"name": "rebalance_running"', schema)
        self.assertIn('"name": "live_trade_enabled"', schema)
        self.assertIn('"name": "last_rebalance_time"', schema)
        self.assertIn('"name": "position_gap"', schema)
        self.assertIn('"name": "next_action_hint"', schema)
        self.assertNotIn('统一账户底仓买入 - 先预览', schema)
        self.assertNotIn('统一账户底仓买入 - 确认执行', schema)
        self.assertNotIn('"title": "账户拓扑"', schema)
        self.assertNotIn('"title": "钱包拓扑"', schema)
        self.assertNotIn('"title": "资产桶明细"', schema)
        self.assertNotIn('"title": "现货/杠杆负债"', schema)
        self.assertNotIn('"title": "半套与策略暴露"', schema)
        self.assertIn('/admin/schema', html)
        self.assertNotIn('let amisJSON = {', html)


if __name__ == '__main__':
    unittest.main()
