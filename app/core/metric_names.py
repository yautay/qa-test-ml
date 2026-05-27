# Static list of known metric names — no torch/ML imports.
# Used by the API process (health endpoint) instead of importing the full registry,
# which would transitively load torch into the API server process.
# Workers use app.core.registry directly for actual metric instantiation.
KNOWN_METRIC_NAMES: list[str] = ["dists", "lpips"]
