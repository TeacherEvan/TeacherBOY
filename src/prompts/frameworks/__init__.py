"""Frameworks package - Reusable knowledge modules for vision analysis."""

from .color_psychology import ColorPsychologyFramework
from .ekman_facs import EkmanFACSFramework
from .facellava import FaceLLaVAFramework
from .fbi_bau import FBIBAUFramework
from .navarro import NavarroBodyLanguageFramework

__all__ = [
    "EkmanFACSFramework",
    "FBIBAUFramework",
    "NavarroBodyLanguageFramework",
    "FaceLLaVAFramework",
    "ColorPsychologyFramework",
]
