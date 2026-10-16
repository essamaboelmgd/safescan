"""Explicit configuration; all default runtime writes stay in the project."""
from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = ROOT / 'models' / 'shoes_exploratory_v1.npz'


def project_path(value: str) -> Path:
    """Resolve relative configuration paths against the project, not the shell cwd."""
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


@dataclass
class Settings:
    data_dir: Path = ROOT / 'runtime'
    model_path: Path = DEFAULT_MODEL_PATH
    network_metadata: bool = False
    enable_estimates: bool = False
    max_upload_bytes: int = 8 * 1024 * 1024
    max_pixels: int = 12_000_000

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=project_path(os.getenv('SAFESCAN_DATA_DIR', str(ROOT / 'runtime'))),
            model_path=project_path(os.getenv('SAFESCAN_MODEL_PATH', str(DEFAULT_MODEL_PATH))),
            network_metadata=os.getenv('SAFESCAN_NETWORK_METADATA') == '1',
            enable_estimates=os.getenv('SAFESCAN_ENABLE_ESTIMATES') == '1',
        )
