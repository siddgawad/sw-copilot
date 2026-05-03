# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for SwCopilotBackend.exe
#
# Build from inside agent-backend/ with:
#   .venv\Scripts\pyinstaller sw_copilot_backend.spec --noconfirm
#
# Output lands in dist/SwCopilotBackend/  (onedir, not onefile)
# The Build-BetaPackage.ps1 script copies this directory into the package.

import sys
from pathlib import Path

block_cipher = None

# Collect all chromadb data files (migrations, sql schemas, etc.)
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

chroma_datas, chroma_binaries, chroma_hiddenimports = collect_all("chromadb")
pydantic_datas, pydantic_binaries, pydantic_hiddenimports = collect_all("pydantic")
onnx_datas, onnx_binaries, onnx_hiddenimports = collect_all("onnxruntime")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=chroma_binaries + onnx_binaries,
    datas=(
        chroma_datas
        + pydantic_datas
        + onnx_datas
    ),
    hiddenimports=(
        chroma_hiddenimports
        + pydantic_hiddenimports
        + onnx_hiddenimports
        + [
            # FastAPI / Starlette internals not always auto-detected
            "uvicorn.logging",
            "uvicorn.loops",
            "uvicorn.loops.auto",
            "uvicorn.loops.asyncio",
            "uvicorn.protocols",
            "uvicorn.protocols.http",
            "uvicorn.protocols.http.auto",
            "uvicorn.protocols.websockets",
            "uvicorn.protocols.websockets.auto",
            "uvicorn.lifespan",
            "uvicorn.lifespan.on",
            "starlette.routing",
            "starlette.middleware",
            "starlette.middleware.cors",
            # groq SDK
            "groq",
            "groq._exceptions",
            # Our app packages
            "agents.macro_engineer",
            "agents.macro_templates",
            "agents.rag_agent",
            "agents.solidworks_api_reference",
            "rag.vector_store",
            "rag.ingestion",
            "rag.noop_telemetry",
            "models.schemas",
            "config",
            # sentence-transformers is NOT included; DefaultEmbeddingFunction uses ONNX only.
        ]
    ),
    excludes=[
        # torch is 485 MB — excluded because DefaultEmbeddingFunction uses ONNX not torch.
        "torch",
        "torchvision",
        "torchaudio",
        "sentence_transformers",
        "transformers",
        # test / dev only
        "pytest",
        "IPython",
        "jupyter",
        "matplotlib",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SwCopilotBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX disabled: chromadb native libs can break with UPX compression
    console=True,       # console=True so log output is visible when debugging startup
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SwCopilotBackend",
)
