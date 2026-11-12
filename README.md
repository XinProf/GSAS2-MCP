# GSAS2-MCP

> [Chinese (Simplified)](README-CN.md) · English

**A GSAS-II fork with a built-in MCP server — Rietveld refinement and crystallographic analysis for AI agents.**

This repository contains two layers, used together:

| Layer | Location | Description | License |
|------|------|------|--------|
| **MCP protocol layer** | `mcp/` | MCP server that exposes GSAS-II as 17 standard tools | BSD-3-Clause |
| **Crystallographic engine** | `GSASII/` + `sources/` | The complete upstream [AdvancedPhotonSource/GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) engine (including 3 fixes in this fork and prebuilt extensions) | GSAS-II Open Source License (see `LICENSE`) |

```
AI Agent (Claude / Copilot / Cursor …)
        │  MCP over stdio / SSE / streamable-http
        ▼
┌────────────────────┐   import    ┌────────────────────────┐
│  mcp/              │ ──────────→ │  GSASII/  (engine)     │
│  gsas2_mcp_server  │             │  Rietveld / Le Bail    │
└────────────────────┘             └────────────────────────┘
```

---

## Quick Start

```bash
# 1. Install the MCP layer (the mcp/ directory in this repo)
pip install /path/to/GSAS2-MCP/mcp

# 2. Point to the engine (i.e., this repo's checkout directory)
export GSAS2_MCP_ENGINE=/path/to/GSAS2-MCP     # Windows: set GSAS2_MCP_ENGINE=...

# 3. Self-check: print the engine location, available Fortran extensions, and registered tools
gsas2-mcp --check

# 4. Launch (stdio by default, for Claude Desktop / Cursor / Cline)
python -m gsas2_mcp_server
python -m gsas2_mcp_server --transport sse --port 8910
python -m gsas2_mcp_server --transport streamable-http
```

The engine can also be installed into the same environment (pip install GSAS-II); the server reads `GSAS2_MCP_ENGINE` first, then falls back to an importable `GSASII` package.

### Claude Desktop / Cursor Configuration

```json
{
  "mcpServers": {
    "gsas2-mcp": {
      "command": "python",
      "args": ["-m", "gsas2_mcp_server"],
      "env": {
        "GSAS2_MCP_ENGINE": "/path/to/GSAS2-MCP"
      }
    }
  }
}
```

For detailed installation, tool semantics, and variable naming (`':0:Scale'`, `'0::A0'`), see [`mcp/README.md`](mcp/README.md).

---

## MCP Tool List (17)

| Category | Tool | Description |
|------|------|------|
| **Project management** | `create_project` | Create a new .gpx project |
| | `load_project` | Load an existing .gpx project |
| | `project_summary` | Structured project summary (histograms, phases, refinement flags, capabilities) |
| | `save_project` | Save the project (optionally under a new name) |
| **Data import** | `add_powder_histogram` | Import a powder diffraction pattern (+ instrument parameter file) |
| | `add_phase` | Add a phase from a CIF, or build one from unit-cell parameters |
| | `add_image` | Load a 2D detector image |
| | `load_data` | Inspect a file with the importer without writing to disk |
| **Refinement control** | `set_refinement` | Toggle refinement parameters (with automatic abbreviation mapping) |
| | `refine` | Run Rietveld / Le Bail refinement |
| | `get_results` | Rwp, GoF, R factors, unit-cell parameters with ESDs, displacements |
| | `hold_variable` | Hold (fix) a parameter |
| | `free_variable` | Free (release) a parameter |
| **Smart diagnostics** | `auto_diagnose` | Inspect the project, report problems and fix suggestions |
| | `suggest_best_strategy` | Recommend a standard stepwise refinement sequence |
| | `generate_report` | Generate a report (Markdown / HTML / JSON) |
| **Visualization** | `generate_plot` | Observed / calculated / difference fit plot |

Every tool returns JSON: on success `{"ok": true, ...}`; on failure `{"ok": false, "error": ..., "error_type": ..., "hint": ...}` — tools never raise exceptions, and a failed call does not break the transport layer.

---

## Changes in This Fork vs Upstream

| Change | Location | Description |
|------|------|------|
| **MCP server layer** | `mcp/` (added) | `gsas2_mcp_server` 10 modules + 126 tests; three transports: stdio / SSE / streamable-http; compatible with mcp SDK 1.x and 2.x (`FastMCP` → `MCPServer` rename) |
| **Space-group fallback** | `GSASII/GSASIIspc.py` | When `pyspg` is missing, `P 1` / `P -1` fall back to pure Python (1-based indexing, acentric `SGOps` + `SGInv` inversion, all per GSAS-II conventions); other space groups return a structured error naming `pyspg`, instead of a bare `NameError` |
| **Self-contained P1SGData** | `GSASII/GSASIIobj.py` | The original `except: pass` left `P1SGData` undefined, so a later `SetNewPhase()` raised NameError; replaced with a self-contained literal, aligned field-by-field in tests against a real `SpcGroup('P 1')` |
| **Fix for silently dropped refinement flags** | `GSASII/GSASIIscriptable.py` | In `set_refinements()`/`clear_refinements()`, the boolean `Background` branch mistakenly used `return`, silently dropping subsequent keys of the same family in the same call; changed to `continue`, with a regression test |
| **Python 3.11 prebuilt extensions** | `GSASII/*.cpython-311-x86_64-linux-gnu.so` | 8 Fortran/C extensions (conda-forge gfortran 15.2.0, Debian 12), ready out of the box on Linux x86_64 |

### Degraded Engine Capabilities (Without Compiled Extensions)

| Component | Behavior without extensions |
|------|----------------|
| `pyspg` (space-group tables) | `P 1` / `P -1` still parse (pure-Python fallback); CIF imports for other space groups return a structured error naming `pyspg` |
| `pypowder` (pattern computation) | `refine` returns a structured error instead of running; all other tools remain available |

In short: platforms without a compiler (e.g., a pip-only install on Windows) can still create projects, import data, set flags, hold/free variables, diagnose, and produce reports and plots — only refinement is unavailable.

### stdout Isolation

GSAS-II writes progress messages to stdout, but over the stdio transport stdout is the JSON-RPC channel. All engine calls go through `gsas2_mcp_server.engine.quiet` to redirect Python-level stdout to stderr; the test suite asserts that stdout is completely empty after a full tool loop.

---

## Code Structure

```
GSAS2-MCP/
├── mcp/                                 # MCP protocol layer (added in this fork)
│   ├── src/gsas2_mcp_server/            # server / engine / state / 5 tool groups
│   ├── tests/                           # 126 tests (incl. subprocess end-to-end)
│   ├── pyproject.toml                   # gsas2-mcp 0.1.0, BSD-3-Clause
│   └── README.md                        # Detailed protocol-layer docs
├── GSASII/                              # GSAS-II engine (upstream sync + 3 fixes)
│   ├── GSASIIscriptable.py              # Scripting API (MCP layer dependency)
│   ├── GSASIIobj.py / GSASIIspc.py      # Data structures / space groups (incl. fallback)
│   ├── imports/                         # 30+ data importers
│   └── *.cpython-311-x86_64-linux-gnu.so  # Prebuilt Fortran extensions ×8
├── sources/                             # Fortran/C sources + meson build
├── tests/testinp/                       # PbSO4 and other test data
└── LICENSE                              # GSAS-II Open Source License
```

---

## Building the Fortran Extensions

The prebuilt `.so` files only cover Linux x86_64 / Python 3.11. On other platforms there are two options:

**Method 1: meson (Recommended, Upstream Official Path)**

```bash
pip install meson ninja numpy
cd sources
meson setup build
meson compile -C build
cp build/sources/*.so ../GSASII/
```

**Method 2: Manual gfortran (without meson)**

```bash
micromamba create -y -p ./gfortran-env -c conda-forge gfortran_linux-64
export PATH="./gfortran-env/bin:$PATH" && export LD_LIBRARY_PATH="./gfortran-env/lib"
cd sources
gfortran -fPIC -O2 -c spsubs/*.for NISTlatsubs/*.f powsubs/*.for powsubs/*.f90 \
    texturesubs/*.for INCLDS/COPYRIGT.FOR DIFFaXsubs/DIFFaXsubs.for
for mod in pyspg pypowder pytexture pydiffax pack_f unpack_cbf histogram2d; do
    gfortran -fPIC -O2 -c ${mod}.for -o ${mod}.o
    gcc -fPIC -O2 -c ${mod}module.c -o ${mod}_mod.o
    [ -f "${mod}-f2pywrappers.f" ] && gfortran -fPIC -O2 -c ${mod}-f2pywrappers.f -o ${mod}_wrap.o
done
gcc -fPIC -O2 -c fortranobject.c fmask.c
gfortran -shared -o pyspg.cpython-311-x86_64-linux-gnu.so pyspg*.o spsubs/*.o NISTlatsubs/*.o -lm
# Link the remaining modules the same way, then cp *.so ../GSASII/
```

**Verification:**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from GSASII import GSASIIpath; GSASIIpath.SetBinaryPath()
from GSASII import pyspg, pypowder, pytexture
print('pyspg / pypowder / pytexture loaded')"
```

---

## Testing

```bash
cd mcp
pip install -e ".[test]"
pytest -q
```

**All 126 tests pass** (measured 19.9 s on Windows / an environment without compiled extensions), covering: engine discovery and the stdout guard, space-group fallback and field-by-field alignment of the `P1SGData` literal, all 17 tools including error paths, and an end-to-end suite that launches the server as a subprocess and drives it over stdio with a real MCP client.

Engine-side scripting API smoke test:

```bash
python3 -c "
import sys, os
sys.path.insert(0, '.')
os.environ['GSASII_HEADLESS'] = 'true'; os.environ['MPLBACKEND'] = 'Agg'
from GSASII import GSASIIscriptable as G2sc
gpx = G2sc.G2Project(newgpx='/tmp/test.gpx')
hist = gpx.add_powder_histogram('tests/testinp/PBSO4.XRA', iparams='tests/testinp/INST_XRY.PRM')
phase = gpx.add_phase('tests/testinp/PbSO4-Wyckoff.cif', histograms=[hist.name])
print('project created:', phase.name)"
```

---

## Related Projects

| Project | Description | Repository |
|------|------|------|
| **FullProf-App-MCP** | Application-layer MCP server for the FullProf Suite | [FullPatt/FullProf-App-MCP](https://github.com/FullPatt/FullProf-App-MCP) |
| **Profex-MCP** | Profex/BGMN phase-analysis MCP server | [FullPatt/Profex-MCP](https://github.com/FullPatt/Profex-MCP) |
| **MAUD-MCP** | MAUD Rietveld refinement MCP server | [FullPatt/MAUD-MCP](https://github.com/FullPatt/MAUD-MCP) |

---

## License

- **`GSASII/` engine and `sources/`**: GSAS-II Open Source License, Copyright 2010 UChicago Argonne, LLC (see [`LICENSE`](LICENSE)). All modifications in this fork mark their authors in comments as required by that license.
- **`mcp/` protocol layer**: BSD-3-Clause (see [`mcp/pyproject.toml`](mcp/pyproject.toml)).

---

## Acknowledgements

- **Advanced Photon Source, Argonne National Laboratory** — GSAS-II development team (Robert B. Von Dreele, Brian H. Toby, et al.)
- GSAS-II documentation: <https://gsas-ii.readthedocs.io>; tutorials: <https://advancedphotonsource.github.io/GSAS-II-tutorials>
