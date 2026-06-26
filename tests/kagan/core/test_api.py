from kagan.core.api import DriftConcern, NeedsYou
from kagan.core.models import DriftConcern as ModelsDriftConcern
from kagan.core.models import NeedsYou as ModelsNeedsYou


def test_public_api_reexports_canonical_report_models():
    # Surfaces (CLI/TUI/MCP) import report models from the api facade, not the
    # internal module; the re-export must be the same class, not a shadow.
    assert NeedsYou is ModelsNeedsYou
    assert DriftConcern is ModelsDriftConcern
