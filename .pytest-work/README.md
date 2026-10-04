# .pytest-work/ — local scratch (git-ignored except this file)

This is the only place for disposable working files: pytest temp folders, one-off audit scripts,
downloaded pages and probes. Everything here except this README can be deleted at any time.

Run the test suite from the project root with a named subfolder. pytest deletes and recreates exactly
that subfolder:

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-work/tests
```

The test suite needs a temp folder inside the project. The pipeline's output policy
(`src/dc_locator/run_config.py`, `preflight`) accepts only `runs/<name>/` and `.pytest-work/...`.
With pytest's default system temp folder, the pipeline tests fail. Never pass
`--basetemp=.pytest-work` itself, because pytest would try to delete this whole folder.

pytest temp folders are private to the account that created them: Python's `mkdir(mode=0o700)` grants
access only to the owner, SYSTEM and Administrators. Delete your own scratch before you finish.
Folders left behind by a sandboxed agent account cannot be opened or deleted by the normal user.

## Locked leftovers

`old-root-wrapper-locked/` is the former `U.S. Sustainable Data Center Location Discovery Model/` wrapper
folder and contains six `.tmp-orchestrator-*` pytest folders. It sits next to thirteen
`review-phase1`…`review-phase4` pytest folders. A sandboxed reviewer account created all of these on
2026-10-02/03. They are old test temp data and nothing references their contents. To remove all scratch
subfolders, run this in a PowerShell window opened with **Run as administrator**. The Administrators
group has full control of these folders:

```powershell
Get-ChildItem -LiteralPath 'D:\locate-data-center\.pytest-work' -Directory -Force | Remove-Item -Recurse -Force
```
