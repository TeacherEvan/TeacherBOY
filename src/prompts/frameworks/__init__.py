"""Frameworks package - Reusable knowledge modules for vision analysis."""

from .ekman_facs import EkmanFACSFramework
from .fbi_bau import FBIBAUFramework
from .navarro import NavarroBodyLanguageFramework
from .facellava import FaceLLaVAFramework
from .color_psychology import ColorPsychologyFramework

__all__ = [
    "EkmanFACSFramework",
    "FBIBAUFramework",
    "NavarroBodyLanguageFramework",
    "FaceLLaVAFramework",
    "ColorPsychologyFramework",
]
