"""redlines — data pipeline for the Automated Catastrophic Risk Forecasting dashboard.

Layout:
    config.py     paths (env-overridable), round pins, thresholds, stable subset
    registry.py   the single model table: ids, labels, ECI, colors, architecture
    stats.py      deciles / brier / bss / spearman / wilson — one implementation each
    runlog.py     forecast run-log loading with the clean_forecasts read guard
    questions.py  schema-checked question-set loaders
    hydrate.py    window.__NAME__ blob injection into the dashboard pages
    views/        pure blob builders: (runlog, questions, config) -> dict

Build everything with:  python3 -m redlines build
"""
