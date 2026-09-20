"""GSAS-II engine discovery and bootstrap.

Two problems have to be solved before any tool can do useful work:

1. **Where is GSAS-II?**  This server ships as the protocol layer only; the
   crystallographic engine is the ``GSASII`` package.  It is either installed
   into the same environment or lives in a checkout of the GSAS2-MCP
   repository.  :func:`bootstrap` finds it and puts it on ``sys.path``.

2. **Keep stdout clean.**  GSAS-II prints a lot of progress information to
   stdout (``GSASIIfiles.G2Print``).  Under the MCP *stdio* transport stdout is
   the JSON-RPC wire, so every byte of engine chatter would corrupt the
   protocol.  :func:`quiet` redirects ``sys.stdout`` to ``sys.stderr`` for the
   duration of an engine call, which is where diagnostics belong.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import threading
from typing import Any, Dict, List, Optional

__all__ = [
    "bootstrap",
    "quiet",
    "get_engine_root",
    "capabilities",
    "is_bootstrapped",
    "require_engine",
    "ok",
    "fail",
    "ENGINE_ENV_VAR",
]

#: Environment variable pointing at a directory that contains ``GSASII/``.
ENGINE_ENV_VAR = "GSAS2_MCP_ENGINE"

_bootstrapped = False
_engine_root: Optional[pathlib.Path] = None
_capabilities: Dict[str, bool] = {}
_bootstrap_error: Optional[str] = None
_lock = threading.Lock()

# The compiled Fortran/C extensions GSAS-II uses.  None of them are required to
# import the engine, but refinement and profile calculation need ``pypowder``,
# and anything touching a space group needs ``pyspg``.
_EXTENSION_MODULES = ("pyspg", "pypowder", "pytexture", "pydiffax", "pack_f",
                      "unpack_cbf", "histogram2d", "fmask")


@contextlib.contextmanager
def quiet():
    """Redirect Python-level stdout to stderr for the duration of the block.

    Used around engine imports and engine calls so that GSAS-II's progress
    output cannot be mistaken for protocol traffic on a stdio transport.
    """
    original = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = original


def _looks_like_engine_root(path: pathlib.Path) -> bool:
    """True when *path* contains an importable GSAS-II checkout."""
    try:
        return (path / "GSASII" / "GSASIIscriptable.py").is_file()
    except OSError:
        return False


def _search_roots() -> List[pathlib.Path]:
    """Directories that may contain the ``GSASII`` package, most specific first."""
    roots: List[pathlib.Path] = []

    env = os.environ.get(ENGINE_ENV_VAR)
    if env:
        roots.append(pathlib.Path(env).expanduser())

    # Inside a PyInstaller bundle, look next to the executable as well.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(pathlib.Path(meipass))
    if getattr(sys, "frozen", False):
        roots.append(pathlib.Path(sys.executable).resolve().parent)

    # Walking up from this file covers the "running from a source checkout"
    # case: <repo>/mcp/src/gsas2_mcp_server/engine.py -> <repo>
    here = pathlib.Path(__file__).resolve()
    roots.extend(here.parents)

    cwd = pathlib.Path.cwd()
    roots.append(cwd)
    roots.extend(cwd.parents)

    seen = set()
    unique = []
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique.append(root)
    return unique


def get_engine_root() -> Optional[pathlib.Path]:
    """Directory holding the ``GSASII`` package, or None if it was not found."""
    return _engine_root


def is_bootstrapped() -> bool:
    """True once :func:`bootstrap` has imported the engine successfully."""
    return _bootstrapped


def bootstrap(force: bool = False) -> Dict[str, Any]:
    """Locate GSAS-II, put it on ``sys.path`` and import it headless.

    Safe to call repeatedly; the work is done once.  Raises :class:`RuntimeError`
    when the engine cannot be found or imported, with a message that explains
    how to point the server at a checkout.
    """
    global _bootstrapped, _engine_root, _capabilities, _bootstrap_error

    with _lock:
        if _bootstrapped and not force:
            return dict(_capabilities)
        if _bootstrap_error and not force:
            raise RuntimeError(_bootstrap_error)

    with quiet():
        # GSAS-II opens a GUI unless told otherwise, and matplotlib needs a
        # non-interactive backend in a server process.
        os.environ.setdefault("GSASII_HEADLESS", "true")
        os.environ.setdefault("MPLBACKEND", "Agg")

        root = None
        for candidate in _search_roots():
            if _looks_like_engine_root(candidate):
                root = candidate
                break

        if root is not None:
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            _engine_root = root
        else:
            # Not a checkout: maybe GSAS-II is pip-installed.
            import importlib.util
            if importlib.util.find_spec("GSASII") is None:
                message = (
                    "GSAS-II was not found. Set the {0} environment variable to "
                    "the directory that contains the GSASII/ package (for "
                    "example the root of a GSAS2-MCP checkout), or install "
                    "GSAS-II into this environment.".format(ENGINE_ENV_VAR))
                _bootstrap_error = message
                raise RuntimeError(message)

        try:
            from GSASII import GSASIIpath
            GSASIIpath.SetBinaryPath()

            # Make the compiled extensions importable as ``GSASII.<mod>``.
            # Conda/installer distributions keep the .pyd/.so files in a
            # version-specific subdirectory (e.g. ``GSASII-bin/win_64_p3.13_n2.2``)
            # and expose it only through ``GSASIIpath.binaryPath`` -- upstream
            # GSAS-II loads them via ``GSASIIpath.ImportModule`` instead of a
            # plain import.  Without this, ``from GSASII import pyspg`` fails
            # even though the extension is present and loadable.
            _binpath = getattr(GSASIIpath, "binaryPath", None)
            if _binpath:
                import GSASII as _GSASII_pkg
                for _p in (_binpath, str(_binpath)):
                    if _p not in sys.path:
                        sys.path.insert(0, _p)
                    _pkgpath = getattr(_GSASII_pkg, "__path__", None)
                    if _pkgpath is not None and _p not in list(_pkgpath):
                        _pkgpath.append(_p)

            from GSASII import (GSASIIscriptable, GSASIIobj, GSASIIspc,
                                GSASIIlattice)
        except Exception as exc:  # pragma: no cover - depends on the install
            message = "GSAS-II was found at {0} but could not be imported: {1}: {2}".format(
                _engine_root or "<installed>", type(exc).__name__, exc)
            _bootstrap_error = message
            raise RuntimeError(message) from exc

        caps: Dict[str, bool] = {"engine": True}
        for name in _EXTENSION_MODULES:
            try:
                __import__("GSASII." + name)
                caps[name] = True
            except Exception:
                caps[name] = False
        caps["refinement_available"] = bool(caps.get("pypowder"))
        caps["spacegroup_tables_available"] = bool(caps.get("pyspg"))

        with _lock:
            _capabilities = caps
            _bootstrapped = True
            _bootstrap_error = None
        return dict(caps)


def capabilities() -> Dict[str, Any]:
    """Feature flags describing what this engine build can actually do.

    ``refinement_available`` is False when the compiled ``pypowder`` extension
    is missing (a platform without a Fortran toolchain); refinement tools then
    return a structured error instead of crashing.
    """
    caps = dict(_capabilities)
    caps["engine_root"] = str(_engine_root) if _engine_root else None
    caps["engine_env_var"] = ENGINE_ENV_VAR
    return caps


def require_engine() -> Any:
    """Import and return ``GSASII.GSASIIscriptable``, bootstrapping first."""
    if not _bootstrapped:
        bootstrap()
    from GSASII import GSASIIscriptable
    return GSASIIscriptable


# --------------------------------------------------------------------------
# Uniform tool results
# --------------------------------------------------------------------------

def ok(**payload: Any) -> Dict[str, Any]:
    """Build a successful tool result."""
    result: Dict[str, Any] = {"ok": True}
    result.update(payload)
    return result


def fail(exc: Any, hint: Optional[str] = None, **payload: Any) -> Dict[str, Any]:
    """Build a failed tool result.

    Tools never raise: an agent driving the server gets a machine-readable
    failure instead of a broken transport, and can retry or change strategy.
    """
    result: Dict[str, Any] = {
        "ok": False,
        "error": str(exc),
        "error_type": type(exc).__name__ if not isinstance(exc, str) else "Error",
    }
    if hint:
        result["hint"] = hint
    result.update(payload)
    return result
