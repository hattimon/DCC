import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_info(path: Path) -> tuple[int, int, int, int]:
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise AssertionError(f"Invalid PNG: {path}")
    width, height = struct.unpack(">II", data[16:24])
    bit_depth = data[24]
    color_type = data[25]
    return width, height, bit_depth, color_type


def ico_entries(path: Path) -> list[dict[str, int]]:
    data = path.read_bytes()
    if len(data) < 6:
        raise AssertionError(f"Invalid ICO: {path}")
    reserved, icon_type, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or icon_type != 1 or count <= 0:
        raise AssertionError(f"Invalid ICO header: {path}")
    entries = []
    for index in range(count):
        offset = 6 + index * 16
        width, height, colors, reserved_byte, planes, bpp, size, image_offset = struct.unpack(
            "<BBBBHHII", data[offset : offset + 16]
        )
        entries.append(
            {
                "width": 256 if width == 0 else width,
                "height": 256 if height == 0 else height,
                "colors": colors,
                "reserved": reserved_byte,
                "planes": planes,
                "bpp": bpp,
                "size": size,
                "offset": image_offset,
            }
        )
    return entries


def ico_payload(path: Path, entry: dict[str, int]) -> bytes:
    data = path.read_bytes()
    start = entry["offset"]
    end = start + entry["size"]
    return data[start:end]


class IconAssetTests(unittest.TestCase):
    def test_generator_uses_glass_master_as_source_of_truth(self):
        generator = (ROOT / "tools" / "generate_icon_assets.py").read_text(encoding="utf-8")
        self.assertIn('"dcc_icon_glass_master.png"', generator)
        self.assertNotIn('"icon_master.svg"', generator)
        self.assertNotIn('"icon_master.png"', generator)

    def test_source_and_linux_pngs_are_present_and_valid(self):
        source = ROOT / "assets" / "dcc_icon_glass_master.png"
        self.assertTrue(source.is_file())
        source_width, source_height, source_bit_depth, source_color_type = png_info(source)
        self.assertEqual(source_width, source_height)
        self.assertGreaterEqual(source_width, 512)
        self.assertEqual(source_bit_depth, 8)
        self.assertIn(source_color_type, (2, 6))

        for size in PNG_SIZES:
            path = ROOT / "assets" / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "docker-control-center.png"
            self.assertTrue(path.is_file(), path)
            self.assertEqual(png_info(path), (size, size, 8, 6))

        self.assertEqual(png_info(ROOT / "icon.png"), (512, 512, 8, 6))
        self.assertEqual(png_info(ROOT / "upstream_assets" / "icon.png"), (512, 512, 8, 6))

    def test_windows_ico_contains_required_rgba_sizes(self):
        for path in (ROOT / "icon.ico", ROOT / "upstream_assets" / "icon.ico"):
            self.assertTrue(path.is_file(), path)
            entries = ico_entries(path)
            sizes = {(entry["width"], entry["height"]) for entry in entries}
            self.assertEqual(sizes, {(size, size) for size in ICO_SIZES})
            for entry in entries:
                self.assertIn(entry["planes"], (0, 1))
                self.assertEqual(entry["bpp"], 32)
                self.assertGreater(entry["size"], 0)
                payload = ico_payload(path, entry)
                if payload.startswith(PNG_SIGNATURE):
                    self.assertEqual(payload[24], 8)
                    self.assertEqual(payload[25], 6)
                else:
                    self.assertGreaterEqual(len(payload), 40)
                    self.assertEqual(struct.unpack("<H", payload[14:16])[0], 32)

    def test_windows_builds_reference_final_ico(self):
        main_spec = (ROOT / "DockerControlCenter.spec").read_text(encoding="utf-8")
        debug_spec = (ROOT / "DockerControlCenterDebug.spec").read_text(encoding="utf-8")
        repo_spec = (ROOT / "RepoBuilder.spec").read_text(encoding="utf-8")
        for text in (main_spec, debug_spec, repo_spec):
            self.assertIn("icon=['upstream_assets/icon.ico']", text)
            self.assertIn("('upstream_assets/icon.png', '.')", text)

        for linux_spec_name in ("DockerControlCenter-linux.spec", "RepoBuilder-linux.spec"):
            linux_spec = (ROOT / "packaging" / "linux" / linux_spec_name).read_text(encoding="utf-8")
            self.assertIn("upstream_assets/icon.png", linux_spec)

        for nsi_path in (ROOT / "DockerControlCenter.nsi", ROOT / "upstream_assets" / "DockerControlCenter.nsi"):
            nsi = nsi_path.read_text(encoding="utf-8-sig")
            self.assertIn('Icon "icon.ico"', nsi)
            self.assertIn('UninstallIcon "icon.ico"', nsi)

    def test_linux_packaging_and_desktop_entries_reference_hicolor_icon(self):
        build = (ROOT / "packaging" / "linux" / "build_deb.sh").read_text(encoding="utf-8")
        self.assertIn('ICON_SIZES=(16 24 32 48 64 128 256 512)', build)
        self.assertIn('assets/icons/hicolor/${size}x${size}/apps/docker-control-center.png', build)
        for desktop_name in ("docker-control-center.desktop", "dcc-repo-builder.desktop"):
            desktop = (ROOT / "packaging" / "linux" / desktop_name).read_text(encoding="utf-8")
            self.assertIn("Icon=docker-control-center", desktop)

    def test_qt_runtime_uses_bundled_icon_resource(self):
        dcc = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        repo = (ROOT / "RepoBuilder.py").read_text(encoding="utf-8")
        self.assertIn('ICON_FILE = RESOURCE_DIR / "icon.png"', dcc)
        self.assertIn("setWindowIcon(QIcon(str(ICON_FILE)))", dcc)
        self.assertIn("setWindowIcon(QIcon(str(dcc.ICON_FILE)))", repo)


if __name__ == "__main__":
    unittest.main()
