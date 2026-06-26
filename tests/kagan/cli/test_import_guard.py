"""Import / byte-compile tripwire for the sole prompt_toolkit module (§1.1).

The format tests import ``format/*`` directly and never touch ``cli/_interactive``
(the only importer of prompt_toolkit and the home of ``render_to_ansi``), so a
Py2-shaped ``except E, F:`` there would parse on the 3.14 floor but break under
any stray 3.13 toolchain — and slip past the suite. These guards fail the moment
that module (or any of ``src/``) stops byte-compiling, or stops importing.
"""

import compileall
import importlib
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"


def test_interactive_imports():
    # The sole prompt_toolkit importer must import cleanly (no syntax/Py2 except).
    module = importlib.import_module("kagan.cli._interactive")
    assert hasattr(module, "render_to_ansi")
    assert hasattr(module, "show_until_dismiss")


def test_src_byte_compiles():
    # Byte-compile the whole tree under the running interpreter; a Py2-shaped
    # except (or any syntax error) fails compilation and trips this test.
    assert compileall.compile_dir(str(_SRC), quiet=1, force=True), (
        f"src/ failed to byte-compile under this interpreter; see {_SRC}"
    )
