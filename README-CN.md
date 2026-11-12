# GSAS2-MCP

**GSAS-II 引擎 + MCP 协议层 — Rietveld 精修与晶体学分析的 AI 智能体接口**

**A GSAS-II fork with a built-in MCP server — Rietveld refinement and crystallographic analysis for AI agents.**

本仓库包含两层，配合使用：

| 层 | 位置 | 说明 | 许可证 |
|------|------|------|--------|
| **MCP 协议层** | `mcp/` | MCP server，把 GSAS-II 暴露为 17 个标准工具 | BSD-3-Clause |
| **晶体学引擎** | `GSASII/` + `sources/` | 上游 [AdvancedPhotonSource/GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) 完整引擎（含本 fork 的 3 处修复与预编译扩展） | GSAS-II Open Source License（见 `LICENSE`） |

```
AI 智能体 (Claude / Copilot / Cursor …)
        │  MCP over stdio / SSE / streamable-http
        ▼
┌────────────────────┐   import    ┌────────────────────────┐
│  mcp/              │ ──────────→ │  GSASII/  (引擎)        │
│  gsas2_mcp_server  │             │  Rietveld / Le Bail    │
└────────────────────┘             └────────────────────────┘
```

---

## 快速开始

```bash
# 1. 安装 MCP 层（本仓库内的 mcp/ 目录）
pip install /path/to/GSAS2-MCP/mcp

# 2. 指向引擎（即本仓库的检出目录）
export GSAS2_MCP_ENGINE=/path/to/GSAS2-MCP     # Windows: set GSAS2_MCP_ENGINE=...

# 3. 自检：打印引擎位置、可用的 Fortran 扩展、已注册工具
gsas2-mcp --check

# 4. 启动（stdio 默认，适配 Claude Desktop / Cursor / Cline）
python -m gsas2_mcp_server
python -m gsas2_mcp_server --transport sse --port 8910
python -m gsas2_mcp_server --transport streamable-http
```

引擎也可安装进同一环境（pip install GSAS-II），server 优先读 `GSAS2_MCP_ENGINE`，其次找可导入的 `GSASII` 包。

### Claude Desktop / Cursor 配置

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

详细的安装、工具语义、变量命名（`':0:Scale'`、`'0::A0'`）见 [`mcp/README.md`](mcp/README.md)。

---

## MCP 工具清单（17 个）

| 类别 | 工具 | 功能 |
|------|------|------|
| **项目管理** | `create_project` | 创建新的 .gpx 项目 |
| | `load_project` | 加载已有 .gpx 项目 |
| | `project_summary` | 项目结构化摘要（直方图、物相、精修标志、能力） |
| | `save_project` | 保存项目（可另存） |
| **数据导入** | `add_powder_histogram` | 导入粉末衍射谱（+仪器参数文件） |
| | `add_phase` | 从 CIF 添加物相，或从晶胞参数构建 |
| | `add_image` | 载入 2D 探测器图像 |
| | `load_data` | 用导入器检查文件，不落盘 |
| **精修控制** | `set_refinement` | 开关精修参数（支持缩写名自动映射） |
| | `refine` | 执行 Rietveld / Le Bail 精修 |
| | `get_results` | Rwp、GoF、R 因子、晶胞参数与 ESD、位移 |
| | `hold_variable` | 固定参数 |
| | `free_variable` | 释放参数 |
| **智能诊断** | `auto_diagnose` | 检查项目，报告问题与修复建议 |
| | `suggest_best_strategy` | 推荐常规分步精修序列 |
| | `generate_report` | 生成报告（Markdown / HTML / JSON） |
| **可视化** | `generate_plot` | 观察/计算/差分拟合图 |

每个工具都返回 JSON：成功 `{"ok": true, ...}`；失败 `{"ok": false, "error": ..., "error_type": ..., "hint": ...}`——工具不抛异常，失败调用不会打断传输层。

---

## 本 Fork 相对上游的变更

| 变更 | 位置 | 说明 |
|------|------|------|
| **MCP 服务层** | `mcp/`（新增） | `gsas2_mcp_server` 10 模块 + 126 项测试；stdio / SSE / streamable-http 三种传输；兼容 mcp SDK 1.x 与 2.x（`FastMCP` → `MCPServer` 改名） |
| **空间群回退** | `GSASII/GSASIIspc.py` | `pyspg` 缺失时 `P 1` / `P -1` 走纯 Python 回退（1-based 索引、acentric `SGOps` + `SGInv` 反转，均按 GSAS-II 约定）；其他空间群返回指名 `pyspg` 的结构化错误，不再裸 `NameError` |
| **P1SGData 自包含** | `GSASII/GSASIIobj.py` | 原 `except: pass` 会留下未定义的 `P1SGData`，后续 `SetNewPhase()` 报 NameError；改为自包含字面量，测试与真实 `SpcGroup('P 1')` 逐字段对齐 |
| **精修标志静默丢弃修复** | `GSASII/GSASIIscriptable.py` | `set_refinements()`/`clear_refinements()` 布尔 `Background` 分支误用 `return`，同一调用中后续同族键被静默丢弃；改为 `continue`，附回归测试 |
| **Python 3.11 预编译扩展** | `GSASII/*.cpython-311-x86_64-linux-gnu.so` | 8 个 Fortran/C 扩展（conda-forge gfortran 15.2.0，Debian 12），Linux x86_64 开箱即用 |

### 引擎能力降级（无编译扩展时）

| 组件 | 无扩展时的行为 |
|------|----------------|
| `pyspg`（空间群表） | `P 1` / `P -1` 仍可解析（纯 Python 回退）；其他空间群的 CIF 导入返回指名 `pyspg` 的结构化错误 |
| `pypowder`（谱计算） | `refine` 返回结构化错误而非运行；其余工具全部可用 |

即：无编译器的平台（如 Windows 纯 pip 安装）仍可建项目、导数据、设标志、固定/释放变量、诊断、出报告和图——只是不能精修。

### stdout 隔离

GSAS-II 会把进度信息打到 stdout，而 stdio 传输上 stdout 就是 JSON-RPC 线路。所有引擎调用均经 `gsas2_mcp_server.engine.quiet` 把 Python 级 stdout 重定向到 stderr；测试套件断言完整工具循环后 stdout 完全为空。

---

## 代码结构

```
GSAS2-MCP/
├── mcp/                                 # MCP 协议层（本 fork 新增）
│   ├── src/gsas2_mcp_server/            # server / engine / state / 5 组 tools
│   ├── tests/                           # 126 项测试（含子进程端到端）
│   ├── pyproject.toml                   # gsas2-mcp 0.1.0, BSD-3-Clause
│   └── README.md                        # 协议层详细文档
├── GSASII/                              # GSAS-II 引擎（上游同步 + 3 处修复）
│   ├── GSASIIscriptable.py              # 脚本 API（MCP 层依赖）
│   ├── GSASIIobj.py / GSASIIspc.py      # 数据结构 / 空间群（含回退）
│   ├── imports/                         # 30+ 数据导入器
│   └── *.cpython-311-x86_64-linux-gnu.so  # 预编译 Fortran 扩展 ×8
├── sources/                             # Fortran/C 源码 + meson 构建
├── tests/testinp/                       # PbSO4 等测试数据
└── LICENSE                              # GSAS-II Open Source License
```

---

## 编译 Fortran 扩展

预编译 `.so` 仅覆盖 Linux x86_64 / Python 3.11。其他平台两种方式：

**方法一：meson（推荐，上游官方路径）**

```bash
pip install meson ninja numpy
cd sources
meson setup build
meson compile -C build
cp build/sources/*.so ../GSASII/
```

**方法二：手动 gfortran（无 meson）**

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
# 其余模块同法链接后 cp *.so ../GSASII/
```

**验证：**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from GSASII import GSASIIpath; GSASIIpath.SetBinaryPath()
from GSASII import pyspg, pypowder, pytexture
print('pyspg / pypowder / pytexture loaded')"
```

---

## 测试

```bash
cd mcp
pip install -e ".[test]"
pytest -q
```

**126 项测试全部通过**（Windows / 无编译扩展环境下实测 19.9 s），覆盖：引擎发现与 stdout 守卫、空间群回退与 `P1SGData` 字面量逐字段对齐、17 个工具含错误路径、以及以子进程启动 server、经真实 MCP 客户端走 stdio 的端到端套件。

引擎侧脚本 API 冒烟测试：

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

## 相关项目

| 项目 | 说明 | 仓库 |
|------|------|------|
| **FullProf-App-MCP** | FullProf Suite 应用层 MCP server | [FullPatt/FullProf-App-MCP](https://github.com/FullPatt/FullProf-App-MCP) |
| **Profex-MCP** | Profex/BGMN 物相分析 MCP server | [FullPatt/Profex-MCP](https://github.com/FullPatt/Profex-MCP) |
| **MAUD-MCP** | MAUD Rietveld 精修 MCP server | [FullPatt/MAUD-MCP](https://github.com/FullPatt/MAUD-MCP) |

---

## 许可证

- **`GSASII/` 引擎与 `sources/`**：GSAS-II Open Source License，Copyright 2010 UChicago Argonne, LLC（见 [`LICENSE`](LICENSE)）。本 fork 的修改均按该许可证要求以注释标明作者。
- **`mcp/` 协议层**：BSD-3-Clause（见 [`mcp/pyproject.toml`](mcp/pyproject.toml)）。

---

## 致谢

- **Advanced Photon Source, Argonne National Laboratory** — GSAS-II 开发团队（Robert B. Von Dreele, Brian H. Toby 等）
- GSAS-II 文档：<https://gsas-ii.readthedocs.io>；教程：<https://advancedphotonsource.github.io/GSAS-II-tutorials>
