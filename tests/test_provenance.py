"""Open-source identity: licence files, About box, the note for reverse engineers, packaging metadata."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSettings  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import paintapp  # noqa: E402
from paintapp import brand, provenance  # noqa: E402
from paintapp.document import Document  # noqa: E402
from paintapp.mainwindow import MainWindow, main  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = QApplication.instance() or QApplication([])


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestIdentity(unittest.TestCase):
    def test_brand_json_matches_brand_py(self):
        meta = json.load(open(os.path.join(ROOT, "packaging", "brand.json")))
        self.assertEqual(meta["name"], brand.NAME)
        self.assertEqual(meta["slug"], brand.SLUG)
        self.assertEqual(meta["app_id"], brand.APP_ID)
        self.assertEqual(meta["author"], brand.AUTHOR)
        self.assertEqual(meta["source_url"], brand.SOURCE_URL)
        self.assertEqual(meta["license"], brand.LICENSE)
        self.assertEqual(meta["tagline"], brand.TAGLINE)

    def test_package_dunders_match_brand(self):
        self.assertEqual((paintapp.__author__, paintapp.__source__, paintapp.__license__),
                         (brand.AUTHOR, brand.SOURCE_URL, brand.LICENSE))
        self.assertTrue(brand.SOURCE_URL.endswith("/" + brand.AUTHOR + "/Paint"))

    def test_licence_files_exist_and_say_what_they_should(self):
        lic = open(os.path.join(ROOT, "LICENSE"), encoding="utf-8").read()
        self.assertIn("GNU GENERAL PUBLIC LICENSE", lic)
        self.assertIn("Version 3", lic)
        self.assertIn(brand.AUTHOR, lic)
        notices = open(os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), encoding="utf-8").read()
        for needle in ("PyQt5", "Stable Diffusion", "ControlNet", "CLIP", "OpenRAIL", brand.SOURCE_URL):
            self.assertIn(needle, notices)

    def test_message_for_reverse_engineers(self):
        text = provenance.hello()
        for needle in (brand.SOURCE_URL, brand.AUTHOR, brand.LICENSE, "reverse engineer", "OPEN SOURCE"):
            self.assertIn(needle, text)
        self.assertIn("مهندس", text)                      # the Persian line too
        self.assertNotIn("Hand-written", text)                                      # keep the message honest

    def test_source_flag_prints_it_without_opening_a_window(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["paintram", "--source"])
        self.assertEqual(code, 0)
        self.assertIn(brand.SOURCE_URL, out.getvalue())


class TestAbout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.win = MainWindow(Document(40, 40), QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.IniFormat))

    def tearDown(self):
        self.win.close()
        self.tmp.cleanup()

    def test_about_box_links_to_the_source_and_names_the_licence(self):
        box = self.win.about_box()
        text = box.text()
        for needle in (brand.NAME, brand.SOURCE_URL, brand.LICENSE, brand.AUTHOR, paintapp.__version__):
            self.assertIn(needle, text)
        self.assertEqual(box.source_button.text(), "Source code")
        self.assertEqual(box.licence_button.text(), "Licences…")

    def test_licence_text_contains_licence_and_credits(self):
        text = self.win.licence_text()
        self.assertIn("GNU GENERAL PUBLIC LICENSE", text)
        self.assertIn("Stable Diffusion", text)

    def test_help_menu_has_source_and_licence_entries(self):
        labels = [a.text() for m in self.win.menuBar().findChildren(type(self.win.menuBar().addMenu("x")))
                  for a in m.actions()]
        self.assertTrue(any("Source Code" in t for t in labels))
        self.assertTrue(any("Licences" in t for t in labels))


class TestEntryPoint(unittest.TestCase):
    def test_windows_loads_torch_before_qt(self):
        src = open(os.path.join(ROOT, "paintram.py"), encoding="utf-8").read()
        self.assertIn("import torch", src)
        self.assertLess(src.index("_load_torch_before_qt()"), src.index("from paintapp.mainwindow import main"))
        self.assertIn('sys.platform != "win32"', src)


class TestPackagingMetadata(unittest.TestCase):
    def test_note_is_appended_to_a_binary_without_touching_it(self):
        protect = load("packaging/protect.py", "protect")
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "mod.so")
            original = b"\x7fELF" + os.urandom(2000)
            open(path, "wb").write(original)
            protect.append_message(path)
            data = open(path, "rb").read()
        self.assertTrue(data.startswith(original))
        self.assertIn(brand.SOURCE_URL.encode(), data[len(original):])
        self.assertIn(b"reverse engineer", data)

    def test_windows_version_resource_carries_the_project_identity(self):
        build = load("packaging/build.py", "build")
        meta = json.load(open(os.path.join(ROOT, "packaging", "brand.json")))
        text = build.windows_version_file(meta, "2.1.0")
        for needle in (brand.SOURCE_URL, brand.AUTHOR, "GPL-3.0-or-later", "2.1.0.0", "Paintram.exe"):
            self.assertIn(needle, text)
        compile(text.replace("VSVersionInfo", "dict").replace("FixedFileInfo", "dict").replace("StringFileInfo", "list")
                .replace("StringTable", "tuple").replace("StringStruct", "tuple").replace("VarFileInfo", "list")
                .replace("VarStruct", "tuple"), "version", "eval")                      # syntactically valid

    def test_installer_scripts_point_to_the_source_and_license(self):
        iss = open(os.path.join(ROOT, "packaging", "paintram.iss"), encoding="utf-8").read()
        self.assertIn("LicenseFile=..\\LICENSE", iss)
        self.assertIn(brand.SOURCE_URL, iss)
        header = open(os.path.join(ROOT, "packaging", "linux", "header.sh"), encoding="utf-8").read()
        self.assertIn("__SOURCE__", header)


if __name__ == "__main__":
    unittest.main()
