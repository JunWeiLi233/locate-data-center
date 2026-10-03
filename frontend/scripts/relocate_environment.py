"""Repair only project-local virtualenv paths after moving the project root."""
from __future__ import annotations

import argparse
import ctypes
import io
import json
import os
import re
import zipfile
from pathlib import Path


def repair_uv_launcher(path: Path, old: str, backups: Path) -> bool:
    """Use Win32 resource updates for uv's documented UTF-8 interpreter path.

    https://github.com/astral-sh/uv/tree/main/crates/uv-trampoline
    https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-beginupdateresourcew
    """
    if os.name != "nt":
        return False
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    word = ctypes.c_ushort
    dword = ctypes.c_ulong
    language_callback = ctypes.WINFUNCTYPE(ctypes.c_int, handle, handle, handle, word, ctypes.c_ssize_t)
    prototypes = {
        "LoadLibraryExW": ([ctypes.c_wchar_p, handle, dword], handle),
        "FreeLibrary": ([handle], ctypes.c_int),
        "EnumResourceLanguagesW": ([handle, handle, ctypes.c_wchar_p, language_callback, ctypes.c_ssize_t], ctypes.c_int),
        "FindResourceExW": ([handle, handle, ctypes.c_wchar_p, word], handle),
        "SizeofResource": ([handle, handle], dword),
        "LoadResource": ([handle, handle], handle),
        "LockResource": ([handle], handle),
        "BeginUpdateResourceW": ([ctypes.c_wchar_p, ctypes.c_int], handle),
        "UpdateResourceW": ([handle, handle, ctypes.c_wchar_p, word, handle, dword], ctypes.c_int),
        "EndUpdateResourceW": ([handle, ctypes.c_int], ctypes.c_int),
    }
    for name, (args, result) in prototypes.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    module = api.LoadLibraryExW(str(path), None, 2)  # data only; never execute it
    if not module:
        raise ctypes.WinError(ctypes.get_last_error())
    languages: list[int] = []
    def collect(_module, _type, _name, language, _data):
        languages.append(language)
        return 1
    callback = language_callback(collect)
    matching: list[int] = []
    try:
        if not api.EnumResourceLanguagesW(module, 10, "UV_PYTHON_PATH", callback, 0):
            return False
        for language in languages:
            resource = api.FindResourceExW(module, 10, "UV_PYTHON_PATH", language)
            size = api.SizeofResource(module, resource)
            pointer = api.LockResource(api.LoadResource(module, resource))
            if not pointer or not size:
                raise ctypes.WinError(ctypes.get_last_error())
            interpreter = ctypes.string_at(pointer, size).decode("utf-8")
            if interpreter.startswith(old + "\\") or interpreter == "python.exe":
                matching.append(language)
    finally:
        api.FreeLibrary(module)
    if not matching:
        return False
    before = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(before)) as archive:
        original_script = archive.read("__main__.py")
    backup = backups / "Scripts" / path.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_bytes(before)
    update = api.BeginUpdateResourceW(str(path), 0)  # preserve other resources
    if not update:
        raise ctypes.WinError(ctypes.get_last_error())
    committed = False
    try:
        # Preserve this installed uv launcher's absolute-interpreter contract.
        interpreter_path = str(path.parent / "python.exe").encode("utf-8")
        value = ctypes.create_string_buffer(interpreter_path)
        for language in matching:
            if not api.UpdateResourceW(update, 10, "UV_PYTHON_PATH", language, value, len(interpreter_path)):
                raise ctypes.WinError(ctypes.get_last_error())
        if not api.EndUpdateResourceW(update, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        committed = True
    finally:
        if not committed:
            api.EndUpdateResourceW(update, 1)
            path.write_bytes(before)
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None or archive.read("__main__.py") != original_script:
                raise ValueError("Updated launcher changed its embedded Python script")
    except Exception:
        path.write_bytes(before)
        raise
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-root", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    old = str(args.old_root.resolve())
    new = str(root)
    environment = root / ".venv"
    if not environment.is_dir() or root == args.old_root.resolve():
        raise SystemExit("Expected an existing relocated project virtualenv.")
    replacements = [(old.replace("\\", "\\\\"), new.replace("\\", "\\\\")),
                    (old, new), (old.replace("\\", "/"), new.replace("\\", "/")),
                    (args.old_root.resolve().as_uri(), root.as_uri())]
    backups = root / "frontend" / "output" / "relocation_environment"
    backups.mkdir(parents=True, exist_ok=True)
    prior = backups / "repairs.json"
    changed: list[str] = list(dict.fromkeys(json.loads(prior.read_text(encoding="utf-8")).get("repaired_files", []))) if prior.exists() else []
    candidates = list((environment / "Lib" / "site-packages").glob("*.pth"))
    candidates += list((environment / "Lib" / "site-packages").glob("*.dist-info/direct_url.json"))
    candidates += list((environment / "Scripts").glob("activate*"))
    for path in candidates:
        before = path.read_bytes()
        text = before.decode("utf-8")
        for source, destination in replacements:
            text = text.replace(source, destination)
        after = text.encode("utf-8")
        if after != before:
            backup = backups / path.relative_to(environment)
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_bytes(before)
            path.write_bytes(after)
            if str(path.relative_to(root)) not in changed:
                changed.append(str(path.relative_to(root)))
    # Repair uv's interpreter resource first. Other console launchers may use
    # a shebang before the appended ZIP; preserve their stub and script.
    for path in (environment / "Scripts").glob("*.exe"):
        if path.name.lower() in {"python.exe", "pythonw.exe", "uv.exe"} or path.stat().st_size > 2_000_000:
            continue
        if repair_uv_launcher(path, old, backups):
            if str(path.relative_to(root)) not in changed:
                changed.append(str(path.relative_to(root)))
            continue
        before = path.read_bytes()
        match = re.search(rb"#![^\r\n]*python(?:w)?\.exe\r?\n(?=PK\x03\x04)", before)
        if not match:
            continue
        shebang = match.group().decode("utf-8")
        repaired = shebang.replace(old, new).replace(old.replace("\\", "/"), new.replace("\\", "/"))
        if repaired == shebang:
            continue
        after = before[:match.start()] + repaired.encode("utf-8") + before[match.end():]
        with zipfile.ZipFile(io.BytesIO(before)) as previous, zipfile.ZipFile(io.BytesIO(after)) as current:
            if current.testzip() is not None or previous.read("__main__.py") != current.read("__main__.py"):
                raise SystemExit(f"Refusing to change an invalid console launcher: {path.name}")
        backup = backups / "Scripts" / path.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(before)
        path.write_bytes(after)
        changed.append(str(path.relative_to(root)))
    evidence = {"old_root": old, "new_root": new, "repaired_files": changed,
                "dependency_versions_changed": False}
    (backups / "repairs.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
