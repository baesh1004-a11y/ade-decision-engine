from . import integrated as _integrated
from .kis_history import load_reference_history as _load_reference_history

# Use the resilient KIS/Naver/KRX historical loader in the integrated workbench.
# The function is looked up at run time by ReplayTargetIntegratedService.run_live.
_integrated._load_reference_history = _load_reference_history

from .integrated import IntegratedWatchConfig, IntegratedWatchResult, ReplayTargetIntegratedService
from .path_watch import PathDailyMatch, PathWatchConfig, PathWatchSnapshot, build_path_snapshot
from .watch import TargetWatchConfig, TargetWatchSnapshot, build_snapshot, classify_state

__all__ = [
    "IntegratedWatchConfig",
    "IntegratedWatchResult",
    "ReplayTargetIntegratedService",
    "PathDailyMatch",
    "PathWatchConfig",
    "PathWatchSnapshot",
    "TargetWatchConfig",
    "TargetWatchSnapshot",
    "build_path_snapshot",
    "build_snapshot",
    "classify_state",
]
