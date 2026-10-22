"""
Lazy Profiler Framework Loader - Load frameworks on-demand.
Reduces startup memory by ~30MB by loading only when needed.

The frameworks live as Python modules under ``src/prompts/frameworks`` (not as
markdown files). This loader resolves them by name and caches the text.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Framework name -> (module, class) inside src/prompts/frameworks
_FRAMEWORK_MODULES: dict[str, tuple[str, str]] = {
    "fbi_bau": ("fbi_bau", "FBIBAUFramework"),
    "ekman_facs": ("ekman_facs", "EkmanFACSFramework"),
    "navarro": ("navarro", "NavarroBodyLanguageFramework"),
    "color_psychology": ("color_psychology", "ColorPsychologyFramework"),
    "facellava": ("facellava", "FaceLLaVAFramework"),
}


class FrameworkLoader:
    """Lazy loader for profiler frameworks."""

    _frameworks: dict[str, str | None] = {}
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
            content = cls._load_framework_text(name)
            if content:
                cls._frameworks[name] = content
                logger.debug(f"✅ Loaded {name}: {len(content)} chars")
                return content

            logger.warning(f"⚠️ Framework not found: {name}")
            cls._frameworks[name] = None
            return ""
        except Exception as e:
            logger.error(f"❌ Error loading {name}: {e}")
            cls._frameworks[name] = None
            return ""

    @classmethod
    def _load_framework_text(cls, name: str) -> str:
        """Resolve a framework module and return its text content."""
        target = _FRAMEWORK_MODULES.get(name)
        if not target:
            return ""

        module_name, class_name = target
        module_path = cls._base_path / f"{module_name}.py"
        if not module_path.exists():
            return ""

        # Import the module directly from its path so the loader keeps working
        # regardless of how the package is installed.
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"_profiler_framework_{module_name}", module_path)
        if spec is None or spec.loader is None:
            return ""

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        framework_class = getattr(module, class_name, None)
        if framework_class is None:
            return ""

        getter = getattr(framework_class, "get_for_analysis_type", None)
        if callable(getter):
            return getter("full")

        full = getattr(framework_class, "get_full", None)
        return full() if callable(full) else ""

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
