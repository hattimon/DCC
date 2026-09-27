import struct
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def ico_entries(path: Path) -> list[dict[str, int]]:
    data = path.read_bytes()
    reserved, icon_type, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or icon_type != 1 or count <= 0:
        raise AssertionError(f"Invalid ICO header: {path}")
    entries = []
    for index in range(count):
        offset = 6 + index * 16
        width, height, _colors, _reserved, planes, bpp, size, image_offset = struct.unpack(
            "<BBBBHHII", data[offset : offset + 16]
        )
        entries.append(
            {
                "width": 256 if width == 0 else width,
                "height": 256 if height == 0 else height,
                "planes": planes,
                "bpp": bpp,
                "size": size,
                "offset": image_offset,
            }
        )
    return entries


class IconAssetTests(unittest.TestCase):
    def test_generator_uses_only_final_dcc_icon_source(self):
        generator = (ROOT / "tools" / "generate_icon_assets.py").read_text(encoding="utf-8")
        self.assertIn('SOURCE = ROOT / "assets" / "dcc_icon.png"', generator)
        for old_source in ("dcc_icon_glass_master", "dcc_icon-best", "icon_master.svg", "icon_master.png"):
            self.assertNotIn(old_source, generator)
        self.assertIn("premultiplied", generator)
        self.assertIn("size not in {16, 24, 32}", generator)

    def test_source_is_rgba_with_meaningful_alpha_and_target_occupancy(self):
        source = ROOT / "assets" / "dcc_icon.png"
        self.assertTrue(source.is_file())
        with Image.open(source) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.width, image.height)
            minimum, maximum = image.getchannel("A").getextrema()
            self.assertLess(minimum, 255)
            self.assertEqual(maximum, 255)
            bbox = image.getchannel("A").point(lambda value: 255 if value >= 24 else 0).getbbox()
            occupancy = max((bbox[2] - bbox[0]) / image.width, (bbox[3] - bbox[1]) / image.height)
            self.assertGreaterEqual(occupancy, 0.92)
            self.assertLessEqual(occupancy, 0.96)

    def test_runtime_and_hicolor_outputs_are_rgba_with_alpha(self):
        runtime_paths = (
            ROOT / "icon.png",
            ROOT / "upstream_assets" / "icon.png",
            ROOT / "repo_builder_icon.png",
            ROOT / "upstream_assets" / "repo_builder_icon.png",
        )
        for path in runtime_paths:
            with Image.open(path) as image:
                self.assertEqual(image.size, (512, 512), path)
                self.assertEqual(image.mode, "RGBA", path)
                minimum, maximum = image.getchannel("A").getextrema()
                self.assertLess(minimum, 255, path)
                self.assertEqual(maximum, 255, path)
        self.assertEqual(len({path.read_bytes() for path in runtime_paths}), 1)

        for size in PNG_SIZES:
            app_dir = ROOT / "assets" / "icons" / "hicolor" / f"{size}x{size}" / "apps"
            main_icon = app_dir / "docker-control-center.png"
            repo_icon = app_dir / "dcc-repo-builder.png"
            for path in (main_icon, repo_icon):
                with Image.open(path) as image:
                    self.assertEqual(image.size, (size, size), path)
                    self.assertEqual(image.mode, "RGBA", path)
                    self.assertLess(image.getchannel("A").getextrema()[0], 255, path)
            self.assertEqual(main_icon.read_bytes(), repo_icon.read_bytes())

    def test_windows_ico_contains_required_direct_rgba_sizes(self):
        paths = (
            ROOT / "icon.ico",
            ROOT / "upstream_assets" / "icon.ico",
            ROOT / "repo_builder_icon.ico",
            ROOT / "upstream_assets" / "repo_builder_icon.ico",
        )
        for path in paths:
            data = path.read_bytes()
            entries = ico_entries(path)
            self.assertEqual(
                {(entry["width"], entry["height"]) for entry in entries},
                {(size, size) for size in ICO_SIZES},
            )
            for entry in entries:
                self.assertIn(entry["planes"], (0, 1))
                self.assertEqual(entry["bpp"], 32)
                payload = data[entry["offset"] : entry["offset"] + entry["size"]]
                self.assertTrue(payload.startswith(PNG_SIGNATURE))
                with Image.open(BytesIO(payload)) as image:
                    self.assertEqual(image.size, (entry["width"], entry["height"]))
                    rgba = image.convert("RGBA")
                    self.assertLess(rgba.getchannel("A").getextrema()[0], 255)
        self.assertEqual(len({path.read_bytes() for path in paths}), 1)

    def test_windows_linux_and_qt_configs_reference_generated_assets(self):
        main_spec = (ROOT / "DockerControlCenter.spec").read_text(encoding="utf-8")
        debug_spec = (ROOT / "DockerControlCenterDebug.spec").read_text(encoding="utf-8")
        repo_spec = (ROOT / "RepoBuilder.spec").read_text(encoding="utf-8")
        for text in (main_spec, debug_spec):
            self.assertIn("icon=['upstream_assets/icon.ico']", text)
            self.assertIn("('upstream_assets/icon.png', '.')", text)
        self.assertIn("icon=['upstream_assets/repo_builder_icon.ico']", repo_spec)
        self.assertIn("('upstream_assets/repo_builder_icon.png', '.')", repo_spec)

        for linux_spec_name in ("DockerControlCenter-linux.spec", "RepoBuilder-linux.spec"):
            linux_spec = (ROOT / "packaging" / "linux" / linux_spec_name).read_text(encoding="utf-8")
            self.assertIn("upstream_assets/icon.png", linux_spec)

        build = (ROOT / "packaging" / "linux" / "build_deb.sh").read_text(encoding="utf-8")
        self.assertIn('ICON_SIZES=(16 24 32 48 64 128 256 512)', build)
        self.assertIn('assets/icons/hicolor/${size}x${size}/apps/docker-control-center.png', build)
        self.assertIn('assets/icons/hicolor/${size}x${size}/apps/dcc-repo-builder.png', build)

        dcc = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        repo = (ROOT / "RepoBuilder.py").read_text(encoding="utf-8")
        self.assertIn('ICON_FILE = RESOURCE_DIR / "icon.png"', dcc)
        self.assertIn('REPO_BUILDER_ICON_FILE = RESOURCE_DIR / "repo_builder_icon.png"', dcc)
        self.assertIn("setWindowIcon(QIcon(str(ICON_FILE)))", dcc)
        self.assertIn("dcc.REPO_BUILDER_ICON_FILE", repo)


if __name__ == "__main__":
    unittest.main()
