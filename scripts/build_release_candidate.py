"""Build a Windows-only release *candidate*, failing closed on any test or GUI error.

Never publishes a GitHub/Nexus release. The frozen executable is actually
launched to test Tcl/Tk initialization and translation payload integrity.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*argv, timeout=240):
    subprocess.run([str(arg) for arg in argv], cwd=ROOT, check=True, timeout=timeout)


def main():
    if sys.platform != "win32":
        raise SystemExit("Release candidate EXE must be built and tested on Windows")

    from PyInstaller.utils.hooks.tcl_tk import tcltk_info
    # PyInstaller 6.20 reports data directories but no longer exposes the
    # legacy `*_data_missing` attributes that some older versions offered.
    tcl_missing = getattr(tcltk_info, "tcl_data_missing", None)
    tk_missing = getattr(tcltk_info, "tk_data_missing", None)
    if tcl_missing is None:
        tcl_missing = not Path(getattr(tcltk_info, "tcl_data_dir", "") or ".").is_dir()
    if tk_missing is None:
        tk_missing = not Path(getattr(tcltk_info, "tk_data_dir", "") or ".").is_dir()
    if not tcltk_info.available or tcl_missing or tk_missing:
        raise RuntimeError("Build Python Tcl/Tk is unavailable or its data files are missing")

    run(sys.executable, "-m", "unittest", "discover", "-p", "test_*.py", "-q")
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        source_check = base / "source-check.json"
        frozen_check = base / "frozen-check.json"
        gui_check = base / "gui-check.json"
        run(sys.executable, "patcher_app.py", "--self-check", source_check)

        manifest = json.loads((ROOT / "installer-data" / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version") != "0.2.8" or manifest.get("target_version") != "8.8.41":
            raise RuntimeError("Unexpected Genesis 8.8.41/v0.2.8 manifest metadata")
        if manifest.get("release_state") != "RELEASE_CANDIDATE" or len(manifest.get("operations", [])) != 183:
            raise RuntimeError("Invalid expected v0.2.8 release candidate payload")
        if manifest.get("in_game_verified") is not False:
            raise RuntimeError("Release candidate must not claim in-game verification")
        targets = {item["target"]: item for item in manifest["operations"]}
        hud = targets.get("mods/Star Wars - HUD Overhaul/interface/playerhudcomponents.gfx")
        if hud is None or hud["kind"] != "hud_recipe_v2":
            raise RuntimeError("Genesis 8.8.41 HUD patch is missing")
        output_version = "v" + manifest["version"]

        run(sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile",
            "--windowed", "--noupx", "--name", "GenesisKRPatcher",
            "--add-data", "installer-data;installer-data", "patcher_app.py", timeout=300)
        exe = ROOT / "dist" / "GenesisKRPatcher.exe"
        if not exe.is_file() or exe.read_bytes()[:2] != b"MZ":
            raise RuntimeError("Windows EXE missing or invalid")

        # Both checks run inside the *frozen* binary, exercising the Tk runtime hook.
        # Use a marker file, not stdout, as --windowed disconnects stdio on Windows.
        run(exe, "--self-check", frozen_check, timeout=90)
        a = json.loads(source_check.read_text(encoding="utf-8"))
        b = json.loads(frozen_check.read_text(encoding="utf-8"))
        if a != b or not b["embedded_payload_verified"]:
            raise RuntimeError("Frozen payload did not match verified source")
        run(exe, "--gui-self-check", gui_check, timeout=90)
        ui = json.loads(gui_check.read_text(encoding="utf-8"))
        if ui.get("version") != manifest["version"] or ui.get("gui_initialized") is not True:
            raise RuntimeError("Frozen Tk GUI initialization failed")
        if not ui.get("tcl") or not ui.get("tk"):
            raise RuntimeError("Frozen Tcl/Tk versions are empty")

        output = ROOT / ("GenesisKRPatcher-" + output_version + ".zip")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(exe, "GenesisKRPatcher.exe")
            archive.write(ROOT / "README.md", "사용방법.txt")
            archive.write(ROOT / "docs" / "Pretendard-LICENSE.txt", "Pretendard-LICENSE.txt")
        with zipfile.ZipFile(output, "r") as archive:
            if archive.testzip() is not None or set(archive.namelist()) != {
                "GenesisKRPatcher.exe", "사용방법.txt", "Pretendard-LICENSE.txt"
            }:
                raise RuntimeError("Candidate ZIP failed integrity checks")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        (ROOT / ("SHA256SUMS-" + output_version + ".txt")).write_text(
            digest + "  " + output.name + "\n", encoding="ascii"
        )
        print("v0.2.8 RC verified: payload, frozen Tcl/Tk GUI, ZIP, SHA-256")


if __name__ == "__main__":
    main()
