from .chapter1_generator import Chapter1Generator
from .chapter2_generator import Chapter2Generator
from .chapter3_generator import Chapter3Generator
from .chapter4_generator import Chapter4Generator
from .chapter5_generator import Chapter5Generator


def __getattr__(name):
    if name == "ReportManager":
        from .report_manager import ReportManager

        return ReportManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
