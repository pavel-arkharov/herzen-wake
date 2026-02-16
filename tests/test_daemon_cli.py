from __future__ import annotations

from herzen_wake.daemon import parse_args


def test_parse_args_defaults() -> None:
    args = parse_args([])

    assert args.check_config is False
    assert args.debug_mode is False
    assert args.debug_score_floor == 0.05
    assert args.debug_log_interval_ms == 500


def test_parse_args_debug_mode_and_overrides() -> None:
    args = parse_args(
        [
            "--debug-mode",
            "--debug-score-floor",
            "0.15",
            "--debug-log-interval-ms",
            "250",
        ]
    )

    assert args.debug_mode is True
    assert args.debug_score_floor == 0.15
    assert args.debug_log_interval_ms == 250
