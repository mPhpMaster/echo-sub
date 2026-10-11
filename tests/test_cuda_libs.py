# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""NVIDIA's libraries: only on an NVIDIA PC, only from the pinned packages, only if they check out."""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import config, cuda_libs, downloads, gpu  # noqa: E402


def wheel_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("nvidia/cublas/bin/cublas64_12.dll", b"MZ dll")
        z.writestr("nvidia/cublas/bin/nested/other.dll", b"not kept")
        z.writestr("nvidia/cublas/include/cublas.h", b"not kept")
        z.writestr("nvidia_cublas_cu12-1.dist-info/METADATA", b"not kept")
    return buffer.getvalue()


WHEEL = wheel_bytes()


class FakeDownloader:
    def __init__(self, body=WHEEL):
        self.body, self.titles = body, []

    def _remote_size(self, url):
        return len(self.body)

    def _run(self, title, files, total):
        self.titles.append(title)
        for _url, dest, _size, _name in files:
            with open(dest, "wb") as f:
                f.write(self.body)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        real = cuda_libs.folder
        cuda_libs.folder = lambda: self.root
        self.addCleanup(lambda: setattr(cuda_libs, "folder", real))

    def package(self, sha=None):
        return [("cublas", "https://files.pythonhosted.org/x/nvidia_cublas_cu12-1-py3-none-win_amd64.whl",
                 sha or hashlib.sha256(WHEEL).hexdigest())]

    def test_only_the_dlls_are_kept(self):
        cuda_libs.download(FakeDownloader(), self.package())
        kept = os.listdir(os.path.join(self.root, "nvidia", "cublas", "bin"))
        self.assertEqual(kept, ["cublas64_12.dll"])
        self.assertFalse([f for f in os.listdir(self.root) if f.endswith(".whl")], "the package itself is deleted")

    def test_a_package_that_does_not_match_is_refused_and_deleted(self):
        with self.assertRaises(downloads.DownloadFailed):
            cuda_libs.download(FakeDownloader(), self.package(sha="0" * 64))
        self.assertFalse(os.path.exists(os.path.join(self.root, "nvidia")))
        self.assertFalse([f for f in os.listdir(self.root) if f.endswith(".whl")])

    def test_done_once(self):
        downloader = FakeDownloader()
        cuda_libs.download(downloader, self.package())
        cuda_libs.download(downloader, self.package())
        self.assertEqual(len(downloader.titles), 1)

    def test_the_pinned_packages_are_nvidias_own_on_pypi(self):
        for name, url, sha in cuda_libs.PACKAGES:
            with self.subTest(name=name):
                self.assertTrue(url.startswith("https://files.pythonhosted.org/packages/"))
                self.assertIn(name.replace("cuda_", ""), url)
                self.assertRegex(sha, r"^[0-9a-f]{64}$")


class NeededTest(unittest.TestCase):
    def setUp(self):
        self.vendor, self.available = gpu.vendor, cuda_libs.available
        self.addCleanup(lambda: setattr(gpu, "vendor", self.vendor))
        self.addCleanup(lambda: setattr(cuda_libs, "available", self.available))
        cuda_libs.available = lambda: False

    def test_only_an_nvidia_pc_fetches_them(self):
        cfg = dict(config.DEFAULTS, device="cuda")
        for make, wanted in (("nvidia", True), ("amd", False), ("intel", False), (None, False)):
            with self.subTest(make=make):
                gpu.vendor = lambda names=None, m=make: m
                self.assertEqual(cuda_libs.needed(cfg), wanted)

    def test_not_when_switched_off_or_another_engine_is_chosen(self):
        gpu.vendor = lambda names=None: "nvidia"
        self.assertFalse(cuda_libs.needed(dict(config.DEFAULTS, device="cuda", cuda_download=False)))
        self.assertFalse(cuda_libs.needed(dict(config.DEFAULTS, device="cpu")))
        self.assertFalse(cuda_libs.needed(dict(config.DEFAULTS, device="vulkan")))

    def test_not_when_they_are_already_here(self):
        gpu.vendor = lambda names=None: "nvidia"
        cuda_libs.available = lambda: True
        self.assertFalse(cuda_libs.needed(dict(config.DEFAULTS, device="cuda")))


class BuildTest(unittest.TestCase):
    def test_the_installer_leaves_them_out_by_default(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "EchoSub.spec"),
                  encoding="utf-8") as f:
            self.assertIn('os.environ.get("ECHOSUB_BUNDLE_CUDA") == "1"', f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
