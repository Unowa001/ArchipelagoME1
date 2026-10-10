"""Build the player release of Archipelago for Mass Effect 1 (LE) into games/masseffect1/build/release-<version>/.

usage: python tools/release/build_release.py <version> <mod staging dir> <bridge .asi>
  e.g. python tools/release/build_release.py 0.1.0 games/masseffect1/build/testK tools/le1apbridge/build/installed/LE1APBridge-v8.asi
Contents: mass_effect_le1.apworld, ArchipelagoME1-mod.zip (ME3Tweaks Mod Manager import: moddesc.ini +
DLC_MOD_ArchipelagoME1), ASI/ (bridge + checks table), install-bridge.ps1, SETUP.md, the YAML template, SHA256SUMS.
Everything is read from the repo and the given build inputs; nothing under the game folder is touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORLD = os.path.join(REPO, "games", "masseffect1", "world", "mass_effect_le1")
MOD_FOLDER = "DLC_MOD_ArchipelagoME1"
MODDESC = """[ModManager]
cmmver = 8.0

[ModInfo]
game = LE1
modname = Archipelago for Mass Effect 1
moddesc = Archipelago multiworld randomizer support for Mass Effect 1 (LE). Start a NEW career after installing. Also install the LE1APBridge ASI (install-bridge.ps1) and run the Mass Effect LE1 Client from the Archipelago Launcher. See SETUP.md.
modver = {version}
moddev = Jerrod

[CUSTOMDLC]
sourcedirs = {mod}
destdirs = {mod}
"""


def zip_dir(src: str, zip_path: str, arc_root: str, skip=lambda rel: False) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if not skip(os.path.relpath(os.path.join(base, d), src)))
            for f in sorted(files):
                rel = os.path.relpath(os.path.join(base, f), src)
                if not skip(rel):
                    z.write(os.path.join(base, f), os.path.join(arc_root, rel).replace("\\", "/"))


def main(version: str, mod_staging: str, bridge: str) -> None:
    out = os.path.join(REPO, "games", "masseffect1", "build", f"release-{version}", f"ArchipelagoME1-{version}")
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "ASI"))

    def world_skip(rel: str) -> bool:
        parts = rel.replace("\\", "/").split("/")
        return "__pycache__" in parts or parts[0] == "test"
    apworld = os.path.join(out, "mass_effect_le1.apworld")
    zip_dir(WORLD, apworld, "mass_effect_le1", lambda rel: world_skip(rel) or rel == "archipelago.json")
    # .apworld manifest: the folder's archipelago.json plus the container fields Archipelago's own packer writes
    # (APWorldContainer.get_manifest: compatible_version 7, container version 7).
    with open(os.path.join(WORLD, "archipelago.json"), encoding="utf-8-sig") as f:
        manifest = {**json.load(f), "compatible_version": 7, "version": 7}
    with zipfile.ZipFile(apworld, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mass_effect_le1/archipelago.json", json.dumps(manifest, indent=4))

    mod_src = os.path.join(mod_staging, MOD_FOLDER)
    if not os.path.isfile(os.path.join(mod_src, "AutoLoad.ini")):
        raise SystemExit(f"no {MOD_FOLDER}/AutoLoad.ini in {mod_staging}")
    tmp = os.path.join(out, "_mod")
    shutil.copytree(mod_src, os.path.join(tmp, MOD_FOLDER))
    with open(os.path.join(tmp, "moddesc.ini"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(MODDESC.format(version=version, mod=MOD_FOLDER))
    zip_dir(tmp, os.path.join(out, "ArchipelagoME1-mod.zip"), "ArchipelagoME1")
    shutil.rmtree(tmp)

    shutil.copyfile(bridge, os.path.join(out, "ASI", "LE1APBridge.asi"))
    shutil.copyfile(os.path.join(REPO, "tools", "le1apbridge", "LE1APBridge.checks.tsv"),
                    os.path.join(out, "ASI", "LE1APBridge.checks.tsv"))
    shutil.copyfile(os.path.join(REPO, "tools", "release", "install-bridge.ps1"), os.path.join(out, "install-bridge.ps1"))
    shutil.copyfile(os.path.join(WORLD, "docs", "setup_en.md"), os.path.join(out, "SETUP.md"))

    # YAML template from the vendored Archipelago (same generator the Launcher uses).
    ap = os.path.join(REPO, "vendor", "Archipelago")
    templates = os.path.join(out, "_templates")
    subprocess.run([os.path.join(ap, ".venv", "Scripts", "python.exe"), "-c",
                    f"from Options import generate_yaml_templates; generate_yaml_templates(r'{templates}', False)"],
                   cwd=ap, check=True, env={**os.environ, "SKIP_REQUIREMENTS_UPDATE": "1"}, capture_output=True)
    shutil.copyfile(os.path.join(templates, "Mass Effect Legendary Edition 1.yaml"),
                    os.path.join(out, "Mass Effect Legendary Edition 1.yaml"))
    shutil.rmtree(templates)

    sums = []
    for base, _dirs, files in os.walk(out):
        for f in sorted(files):
            path = os.path.join(base, f)
            sums.append(f"{hashlib.sha256(open(path, 'rb').read()).hexdigest()}  {os.path.relpath(path, out)}")
    with open(os.path.join(out, "SHA256SUMS"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(sorted(sums, key=lambda s: s.split("  ")[1])) + "\n")
    archive = shutil.make_archive(out, "zip", os.path.dirname(out), os.path.basename(out))
    print("\n".join(sums))
    print(f"release: {archive}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
