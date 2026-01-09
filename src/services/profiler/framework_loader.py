"""
Lazy Profiler Framework Loader - Load frameworks on-demand.
Reduces startup memory by ~30MB by loading only when needed.
"""

import logging
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameworkLoader:
    """Lazy loader for profiler frameworks."""

    _frameworks: Dict[str, Optional[str]] = {}
    _base_path = Path(__file__).parent.parent.parent / "prompts" / "frameworks"

    @classmethod
    def get_framework(cls, name: str) -> str:
        """
        Load framework content on-demand.

        Args:
            name: Framework name (fbi_bau, ekman_facs, navarro, color_psychology)

        Returns:
            Framework content as string (empty if not found)
        """
        # Check cache first
        if name in cls._frameworks:
            cached = cls._frameworks[name]
            return cached if cached is not None else ""

        logger.info(f"🔧 Loading framework: {name}")

        try:
            file_path = cls._base_path / f"{name}.md"
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                cls._frameworks[name] = content
                logger.debug(f"✅ Loaded {name}: {len(content)} chars")
                return content
            else:
                logger.warning(f"⚠️ Framework not found: {file_path}")
                cls._frameworks[name] = None
                return ""
        except Exception as e:
            logger.error(f"❌ Error loading {name}: {e}")
            cls._frameworks[name] = None
            return ""

    @classmethod
    def get_multiple(cls, *names: str) -> str:
        """
        Load multiple frameworks and concatenate.

        Args:
            *names: Framework names to load

        Returns:
            Combined framework content
        """
        frameworks = []
        for name in names:
            content = cls.get_framework(name)
            if content:
                frameworks.append(content)

        return "\n\n".join(frameworks)

    @classmethod
    def clear_cache(cls):
        """Clear loaded frameworks (useful for testing)."""
        cls._frameworks.clear()
        logger.debug("🗑️ Cleared framework cache")

    @classmethod
    def preload_all(cls):
        """
        Preload all frameworks (optional optimization).
        Use when you know profiling will be heavily used.
        """
        framework_names = ["fbi_bau", "ekman_facs", "navarro", "color_psychology"]
        for name in framework_names:
            cls.get_framework(name)
        logger.info(f"✅ Preloaded {len(framework_names)} frameworks")


# Framework name constants for type safety
FBI_BAU = "fbi_bau"
EKMAN_FACS = "ekman_facs"
NAVARRO = "navarro"
COLOR_PSYCHOLOGY = "color_psychology"
