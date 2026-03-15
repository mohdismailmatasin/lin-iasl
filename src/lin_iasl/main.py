# backward compatibility shim for the package

from .window import LinIaslWindow, main

# expose version and metadata from __init__ if needed
from . import __version__, __author__, __license__

__all__ = ['LinIaslWindow', 'main', '__version__', '__author__', '__license__']

