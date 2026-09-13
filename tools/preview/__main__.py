import argparse
from pathlib import Path
from .render import render_preview

parser = argparse.ArgumentParser(description="Render labeled field PNG/GIF previews from a processed package.")
parser.add_argument("directory", type=Path)
render_preview(parser.parse_args().directory)
