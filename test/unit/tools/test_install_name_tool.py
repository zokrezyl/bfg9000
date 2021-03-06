from . import *

from bfg9000.tools.install_name_tool import InstallNameTool


class TestInstallNameTool(ToolTestCase):
    tool_type = InstallNameTool

    def test_env(self):
        with mock.patch('bfg9000.shell.which', return_value=['command']):
            self.assertIsInstance(self.env.tool('install_name_tool'),
                                  InstallNameTool)

    def test_none(self):
        self.assertEqual(self.tool('path'), None)

    def test_id(self):
        self.assertEqual(self.tool('path', id='id'), [
            self.tool, '-id', 'id', 'path'
        ])

    def test_changes(self):
        self.assertEqual(self.tool('path', changes=['foo', 'bar']), [
            self.tool, '-change', 'foo', '-change', 'bar', 'path'
        ])

    def test_all(self):
        self.assertEqual(self.tool('path', id='id', changes=['changes']), [
            self.tool, '-id', 'id', '-change',
            'changes', 'path'
        ])
