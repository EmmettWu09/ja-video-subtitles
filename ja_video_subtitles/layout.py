"""Per-video output layout for `run`: one folder per video, <out>/<stem>/.

Every consumer (CLI target checks, overwrite confirmation, preflight, the
pipeline stages, highlights, and the run report) derives paths through these
helpers so the layout stays consistent everywhere.
"""

from pathlib import Path


def video_output_dir(out_dir: Path, stem: str) -> Path:
    """The per-video product directory <out>/<stem>/."""
    return out_dir / stem


def highlights_dir(video_dir: Path) -> Path:
    """The highlights artifact directory inside a video folder."""
    return video_dir / "highlights"


def essence_path(video_dir: Path, stem: str) -> Path:
    """The essence video, next to the burned <stem>.mp4 in the video folder."""
    return video_dir / f"{stem}.highlights.mp4"
