import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location("overlay", Path(__file__).resolve().parents[1] / "apply-lab-overlay.py")
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


class OverlayTest(unittest.TestCase):
    def test_resource_merge_retains_new_upstream_strings_and_lab_overrides(self):
        current = ET.fromstring('<resources><string name="lab_empty_no_source">Empty</string><string name="title">Upstream</string></resources>')
        lab = ET.fromstring('<resources><string name="title">Lab</string><string name="extra">Extra</string></resources>')
        merged = overlay.merge_values(current, lab)
        self.assertEqual({e.get('name'): e.text for e in merged}, {'lab_empty_no_source': 'Empty', 'title': 'Lab', 'extra': 'Extra'})

    def test_manifest_preserves_new_pages_and_merges_lab_entries(self):
        current = ET.fromstring('<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name=".FollowingActivity"/><service android:name=".LabService" android:exported="false"/></application><queries><package android:name="existing"/></queries></manifest>')
        lab = ET.fromstring('<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name=".LabActivity"/><service android:name=".LabService" android:exported="true"/></application><queries><package android:name="extra"/><package android:name="existing"/></queries></manifest>')
        merged = overlay.merge_manifest(current, lab)
        app = merged.find('application')
        self.assertEqual({e.get(overlay.ANDROID+'name') for e in app}, {'.FollowingActivity', '.LabService', '.LabActivity'})
        self.assertEqual(app.find('service').get(overlay.ANDROID+'exported'), 'false')
        self.assertEqual(len(merged.find('queries')), 2)

    def test_application_and_binary_assets_survive_overlay_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            app = source / overlay.APP
            app.parent.mkdir(parents=True)
            original = b'public static boolean isForeground() { return foregroundActivities > 0; }'
            app.write_bytes(original)
            bundle = root / 'overlay.zip'
            with ZipFile(bundle, 'w') as archive:
                archive.writestr(overlay.APP.as_posix(), b'old incompatible App')
                archive.writestr('app/src/main/assets/lab/7zz', b'\x7fELF\x00\xff')
            overlay.apply_overlay(bundle, source)
            self.assertEqual(app.read_bytes(), original)
            self.assertEqual((source / 'app/src/main/assets/lab/7zz').read_bytes(), b'\x7fELF\x00\xff')


if __name__ == '__main__':
    unittest.main()
