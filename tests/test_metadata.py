"""Validate the metadata shipped with Easy-Github-Uploader."""
import unittest
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
APP_ID = 'io.github.LionheartTim.EasyGithubUploader'

class MetadataTests(unittest.TestCase):
    def test_license_is_full_gpl_version_three(self):
        text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertIn('GNU GENERAL PUBLIC LICENSE', text)
        self.assertIn('Version 3, 29 June 2007', text)
        self.assertIn('END OF TERMS AND CONDITIONS', text)

    def test_metainfo_is_parseable_and_consistent(self):
        root = ElementTree.parse(ROOT / (APP_ID + '.metainfo.xml')).getroot()
        self.assertEqual(root.attrib.get('type'), 'desktop-application')
        self.assertEqual(root.findtext('id'), APP_ID)
        self.assertEqual(root.findtext('metadata_license'), 'CC0-1.0')
        self.assertEqual(root.findtext('project_license'), 'GPL-3.0-only')
        self.assertEqual(root.find('launchable').get('type'), 'desktop-id')
        self.assertEqual(root.findtext('launchable'), 'easy-github-uploader.desktop')
        self.assertEqual(root.find('releases/release').get('version'), '1.0.0')
        self.assertIn('Name=Easy-Github-Uploader', (ROOT / 'install-launcher.sh').read_text())
        self.assertIn('easy-github-uploader.desktop', (ROOT / 'install-launcher.sh').read_text())

    def test_version_and_clickable_author_footer(self):
        ui_source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn("APP_VERSION = '1.0.0'", ui_source)
        self.assertIn('Made by <a href=', ui_source)
        self.assertIn("AUTHOR_GITHUB_URL = 'https://github.com/LionheartTim'", ui_source)
        self.assertIn('author_label.setOpenExternalLinks(True)', ui_source)
        self.assertIn('main.addLayout(footer)', ui_source)

if __name__ == '__main__':
    unittest.main()
