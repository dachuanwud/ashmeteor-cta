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

        self.assertIn('"title": "账户拓扑"', schema)
        self.assertIn('/admin/schema', html)
        self.assertNotIn('let amisJSON = {', html)


if __name__ == '__main__':
    unittest.main()
