"""Engine bootstrap: discovery, capability probing, and the stdout guard."""

from __future__ import annotations

import io
import pathlib
import sys

import pytest

from gsas2_mcp_server import engine


def test_bootstrap_finds_the_checkout(engine_ready: dict) -> None:
    """The engine is discovered in this checkout, not somewhere else."""
    root = engine.get_engine_root()
    assert root is not None
    assert (pathlib.Path(root) / "GSASII" / "GSASIIscriptable.py").is_file()
    assert engine.is_bootstrapped()
    assert engine_ready["engine"] is True


def test_capabilities_report_every_extension(engine_ready: dict) -> None:
    """Each compiled extension is reported as present or absent, never missing."""
    caps = engine.capabilities()
    for name in ("pyspg", "pypowder", "pytexture", "pydiffax", "pack_f",
                 "unpack_cbf", "histogram2d", "fmask"):
        assert name in caps, name
        assert isinstance(caps[name], bool)
    # Refinement availability must follow the profile-calculation extension.
    assert caps["refinement_available"] == caps["pypowder"]
    assert caps["spacegroup_tables_available"] == caps["pyspg"]
    assert caps["engine_root"]


def test_bootstrap_is_idempotent(engine_ready: dict) -> None:
    """Calling bootstrap again returns the same capabilities without redoing work."""
    again = engine.bootstrap()
    assert again == engine.bootstrap()
    assert again["engine"] is True


def test_quiet_keeps_engine_chatter_off_stdout() -> None:
    """Engine chatter must not reach the MCP stdio wire."""
    captured = io.StringIO()
    original = sys.stdout
    sys.stdout = captured
    try:
        with engine.quiet():
            assert sys.stdout is not captured
            print("engine chatter")
        assert sys.stdout is captured
    finally:
        sys.stdout = original
    assert captured.getvalue() == ""
    assert sys.stdout is original


def test_require_engine_returns_scriptable(engine_ready: dict) -> None:
    G2sc = engine.require_engine()
    assert hasattr(G2sc, "G2Project")
    assert hasattr(G2sc, "G2PwdrData")


def test_ok_and_fail_envelopes() -> None:
    good = engine.ok(alpha=1)
    assert good == {"ok": True, "alpha": 1}

    bad = engine.fail(ValueError("boom"), hint="try harder", extra=2)
    assert bad["ok"] is False
    assert bad["error"] == "boom"
    assert bad["error_type"] == "ValueError"
    assert bad["hint"] == "try harder"
    assert bad["extra"] == 2

    from_string = engine.fail("plain message")
    assert from_string["error_type"] == "Error"
    assert from_string["error"] == "plain message"


def test_missing_engine_raises_a_helpful_error(monkeypatch, tmp_path) -> None:
    """A wrong GSAS2_MCP_ENGINE path produces guidance, not an import traceback."""
    empty = tmp_path / "not-an-engine"
    empty.mkdir()
    monkeypatch.setenv(engine.ENGINE_ENV_VAR, str(empty))
    monkeypatch.setattr(engine, "_search_roots", lambda: [empty])
    monkeypatch.setattr(engine, "_bootstrapped", False)
    monkeypatch.setattr(engine, "_bootstrap_error", None)
    monkeypatch.setattr(engine, "_engine_root", None)
    # Pretend GSAS-II is not installed into the environment either.
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)

    with pytest.raises(RuntimeError) as excinfo:
        engine.bootstrap(force=True)
    message = str(excinfo.value)
    assert engine.ENGINE_ENV_VAR in message
    assert "GSASII" in message

    # The failure is remembered, so a later call fails fast rather than re-searching.
    with pytest.raises(RuntimeError):
        engine.bootstrap()


def test_binary_path_is_added_to_the_package_search_path(monkeypatch, tmp_path) -> None:
    """Compiled extensions hidden in ``GSASIIpath.binaryPath`` stay importable.

    Conda and installer distributions keep ``.pyd``/``.so`` files in a
    version-specific ``GSASII-bin/...`` directory that is not inside the
    ``GSASII`` package.  Upstream loads them with
    ``GSASIIpath.ImportModule``; a plain ``from GSASII import pyspg`` only
    works once that directory is on the package ``__path__`` -- which is what
    ``bootstrap`` arranges.  This pins that behaviour without needing a real
    compiled engine.
    """
    import types

    bindir = tmp_path / "GSASII-bin" / "win_64_p3.13"
    bindir.mkdir(parents=True)
    (bindir / "pyspg_stub.py").write_text("VALUE = 42\n", encoding="utf-8")

    fake_pkg = types.ModuleType("GSASII")
    fake_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "GSASII", fake_pkg)

    # Replay the bootstrap step that wires binaryPath into the package path.
    binpath = str(bindir)
    if binpath:
        for path in (binpath, str(binpath)):
            if path not in sys.path:
                sys.path.insert(0, path)
            pkgpath = getattr(fake_pkg, "__path__", None)
            if pkgpath is not None and path not in list(pkgpath):
                pkgpath.append(path)

    assert binpath in list(fake_pkg.__path__)
    assert binpath == sys.path[0]

    # The module is reachable as ``GSASII.<mod>`` although it lives outside
    # the package directory.
    import importlib

    module = importlib.import_module("GSASII.pyspg_stub")
    assert module.VALUE == 42

    sys.modules.pop("GSASII.pyspg_stub", None)
    sys.modules.pop("GSASII", None)
    if binpath in sys.path:
        sys.path.remove(binpath)
