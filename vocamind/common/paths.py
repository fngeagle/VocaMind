"""VocaMind 项目路径常量。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REF_DIR = PROJECT_ROOT / "ref_audio"
