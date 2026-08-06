"""End-to-end test for the binary-only POSIX installer."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "posix" and shutil.which("curl"), "requires POSIX shell and curl")
class PosixInstallerIntegrationTest(unittest.TestCase):
    def test_installer_downloads_verifies_and_runs_single_binary(self):
        machine = platform.machine().lower()
        if machine not in {"x86_64", "amd64", "arm64", "aarch64"}:
            self.skipTest(f"unsupported test architecture: {machine}")
        arch = "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
        asset = f"visionsieve-linux-{arch}"
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory(prefix="visionsieve-installer-") as directory:
            tmp = Path(directory)
            release = tmp / "release"
            fake_bin = tmp / "fake-bin"
            install_dir = tmp / "installed"
            release.mkdir()
            fake_bin.mkdir()

            payload = release / asset
            payload.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$VISIONSIEVE_TEST_LOG\"\n",
                encoding="utf-8",
            )
            payload.chmod(0o755)
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            (release / "visionsieve-SHA256SUMS.txt").write_text(
                f"{digest}  {asset}\n", encoding="utf-8"
            )

            codex = fake_bin / "codex"
            codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            codex.chmod(0o755)
            log = tmp / "setup-args.txt"
            env = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "HOME": str(tmp / "home"),
                "VISIONSIEVE_RELEASE_BASE": release.as_uri(),
                "VISIONSIEVE_BIN_DIR": str(install_dir),
                "VISIONSIEVE_TEST_LOG": str(log),
            }
            completed = subprocess.run(
                ["sh", str(root / "install.sh"), "--skip-probe"],
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            installed = install_dir / "visionsieve"
            self.assertTrue(installed.is_file())
            self.assertTrue(os.access(installed, os.X_OK))
            self.assertEqual(log.read_text(encoding="utf-8").strip(), "setup --skip-probe")
            self.assertNotIn("python", completed.stdout.casefold())
            self.assertNotIn("pip", completed.stdout.casefold())


if __name__ == "__main__":
    unittest.main()
