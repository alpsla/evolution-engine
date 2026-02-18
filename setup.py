"""Setup script for Cython compilation of proprietary phase engines.

When EVO_CYTHON_BUILD=1 is set, compiles phase engines into .so/.pyd files.
Otherwise, builds a pure Python wheel (no compilation).

This enables cibuildwheel to produce platform-specific wheels with embedded
signing keys, while `pip install .` still works without a C compiler.
"""

import os
from pathlib import Path

from setuptools import setup

ext_modules = []

if os.environ.get("EVO_CYTHON_BUILD") == "1":
    try:
        from Cython.Build import cythonize
        from setuptools import Extension

        CYTHON_MODULES = [
            "evolution/phase2_engine.py",
            "evolution/phase3_engine.py",
            "evolution/phase4_engine.py",
            "evolution/phase5_engine.py",
            "evolution/knowledge_store.py",
            "evolution/license.py",
        ]

        # Inject production signing key before compilation
        key = os.environ.get("EVO_LICENSE_SIGNING_KEY")
        license_py = Path("evolution/license.py")
        original_content = None
        if key and license_py.exists():
            original_content = license_py.read_text()
            marker = '_DEV_SIGNING_KEY = b"evo-license-v1-dev-key-replace-in-production"'
            if marker in original_content:
                modified = original_content.replace(
                    marker, f'_DEV_SIGNING_KEY = b"{key}"'
                )
                license_py.write_text(modified)
                print("  Injected production signing key into license.py")

        # Build extensions
        extensions = []
        for mod_path in CYTHON_MODULES:
            mod_name = mod_path.replace("/", ".").replace("\\", ".").removesuffix(".py")
            extensions.append(Extension(mod_name, [mod_path]))

        ext_modules = cythonize(
            extensions,
            compiler_directives={
                "language_level": "3",
                "boundscheck": False,
                "wraparound": False,
            },
        )

        # Restore original license.py (key only lives in compiled binary)
        if original_content is not None:
            license_py.write_text(original_content)
            print("  Restored original license.py")

    except ImportError:
        print("Warning: Cython not available, building pure Python wheel")

setup(ext_modules=ext_modules)
