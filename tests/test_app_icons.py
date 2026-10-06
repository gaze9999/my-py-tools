from pathlib import Path
import tempfile
import unittest

from gui.packaging.icons import SOURCE, prepare_icons


class AppIconTests(unittest.TestCase):
    def test_native_formats_sizes_and_transparency(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Install build requirements for native icon exports")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_icons(root)
            with Image.open(root / "app.ico") as icon:
                self.assertEqual(icon.ico.sizes(), {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)})
                self.assertEqual(icon.convert("RGBA").getpixel((0, 0))[3], 0)
                for size in icon.ico.sizes():
                    small = icon.ico.getimage(size).convert("RGBA")
                    self.assertGreater(small.getpixel((round(size[0] * 0.28), round(size[1] * 0.31)))[1], 150)
            with Image.open(root / "app.icns") as icon:
                self.assertEqual(icon.format, "ICNS")
                self.assertEqual(icon.size, (1024, 1024))
                decoded = icon.convert("RGBA")
                self.assertEqual(decoded.getpixel((0, 0))[3], 0)
                self.assertEqual(decoded.getpixel((512, 128)), (23, 49, 59, 255))
            with Image.open(root / "app.png") as icon:
                self.assertEqual(icon.size, (1024, 1024))
                self.assertEqual(icon.getpixel((512, 128)), (23, 49, 59, 255))

    def test_unsupported_artwork_fails_instead_of_silently_disappearing(self):
        try:
            import PIL
        except ImportError:
            self.skipTest("Install build requirements for native icon exports")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "bad.svg"
            source.write_text(SOURCE.read_text().replace("<title>My Py Tools</title>", "<path d='M0 0' />"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                prepare_icons(root / "output", source)
            self.assertFalse((root / "output").exists())
