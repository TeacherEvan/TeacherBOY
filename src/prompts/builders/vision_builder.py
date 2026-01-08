"""Vision Prompt Builder - Dynamic composition of vision analysis prompts.

This builder enables token-efficient prompt construction by selectively
loading only the frameworks needed for a specific analysis task.

Example usage:
    # Quick analysis (~800 tokens)
    prompt = (
        VisionPromptBuilder()
        .set_analysis_type("quick")
        .add_framework("ekman")
        .add_framework("navarro")
        .build()
    )
    
    # Full analysis (~2400 tokens)
    prompt = (
        VisionPromptBuilder()
        .set_analysis_type("full")
        .add_framework("ekman")
        .add_framework("fbi")
        .add_framework("navarro")
        .add_framework("color")
        .build()
    )
"""

import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class VisionPromptBuilder:
    """
    Builder for vision analysis prompts with modular framework loading.
    
    Supports:
    - Selective framework loading (only include what's needed)
    - Multiple analysis depths (quick/standard/full)
    - Token estimation before API call
    - Custom instructions injection
    """
    
    def __init__(self):
        """Initialize empty builder."""
        self.analysis_type = "standard"
        self.frameworks: List[str] = []
        self.custom_instructions = ""
        self._framework_content: List[str] = []
        self._estimated_tokens = 0
    
    def set_analysis_type(self, analysis_type: str) -> 'VisionPromptBuilder':
        """
        Set analysis depth.
        
        Args:
            analysis_type: "quick", "standard", or "full"
            
        Returns:
            Self for method chaining
        """
        if analysis_type not in ["quick", "standard", "full"]:
            logger.warning(
                f"Unknown analysis type '{analysis_type}', using 'standard'"
            )
            self.analysis_type = "standard"
        else:
            self.analysis_type = analysis_type
        
        return self
    
    def add_framework(self, framework_name: str) -> 'VisionPromptBuilder':
        """
        Add a framework to the prompt.
        
        Available frameworks:
        - "ekman": Paul Ekman's FACS (facial expressions)
        - "fbi": FBI BAU behavioral profiling
        - "navarro": Joe Navarro's body language
        - "color": Color psychology
        - "facellava": FaceLLaVA methodology
        
        Args:
            framework_name: Framework identifier
            
        Returns:
            Self for method chaining
        """
        # Lazy import to avoid circular dependencies
        from src.prompts.frameworks.ekman_facs import EkmanFACSFramework
        from src.prompts.frameworks.fbi_bau import FBIBAUFramework
        
        framework_map: Dict[str, tuple] = {
            "ekman": (EkmanFACSFramework, "Ekman FACS"),
            "fbi": (FBIBAUFramework, "FBI BAU"),
            # Add other frameworks as they're implemented
        }
        
        if framework_name not in framework_map:
            logger.warning(f"Unknown framework '{framework_name}', skipping")
            return self
        
        framework_class, framework_display_name = framework_map[framework_name]
        
        try:
            # Get framework content for current analysis type
            content = framework_class.get_for_analysis_type(self.analysis_type)
            tokens = framework_class.estimate_tokens(self.analysis_type)
            
            self._framework_content.append(content)
            self._estimated_tokens += tokens
            self.frameworks.append(framework_name)
            
            logger.debug(
                f"Added {framework_display_name} ({tokens} tokens) "
                f"for {self.analysis_type} analysis"
            )
            
        except Exception as e:
            logger.error(f"Failed to load framework '{framework_name}': {e}")
        
        return self
    
    def add_custom_instructions(self, instructions: str) -> 'VisionPromptBuilder':
        """
        Add custom analysis instructions.
        
        Args:
            instructions: Custom guidance for the analysis
            
        Returns:
            Self for method chaining
        """
        self.custom_instructions = instructions
        self._estimated_tokens += len(instructions) // 4  # Rough token estimate
        return self
    
    def estimate_tokens(self) -> int:
        """
        Estimate total token count for this prompt.
        
        Returns:
            Estimated tokens (includes base + frameworks + instructions)
        """
        base_tokens = 200  # Base structure and formatting
        return self._estimated_tokens + base_tokens + (len(self.custom_instructions) // 4)
    
    def build(self) -> str:
        """
        Assemble the final prompt.
        
        Returns:
            Complete prompt text optimized for vision API
        """
        # Base introduction
        intro = self._build_intro()
        
        # Assemble frameworks
        frameworks_section = "\n\n".join(self._framework_content)
        
        # Instructions
        instructions = self._build_instructions()
        
        # Ethical notes
        ethics = self._build_ethics_note()
        
        # Combine all sections
        prompt = f"{intro}\n\n{frameworks_section}\n\n{instructions}\n\n{ethics}"
        
        logger.info(
            f"Built vision prompt with {len(self.frameworks)} frameworks, "
            f"~{self.estimate_tokens()} estimated tokens"
        )
        
        return prompt
    
    def _build_intro(self) -> str:
        """Build introduction based on analysis type."""
        intros = {
            "quick": "Analyze this image briefly with scientific precision.",
            "standard": "Analyze this image with scientific precision using the frameworks below.",
            "full": "Provide a comprehensive analysis of this image with scientific precision, using all available frameworks.",
        }
        
        intro = intros.get(self.analysis_type, intros["standard"])
        
        # Add context about fictional vs. real
        intro += """

**IMPORTANT CONTEXT**: This analysis is for:
- Fictional characters in artistic works (anime, manga, illustrations)
- Real photographs for educational/creative purposes
- Accessibility support for understanding expressions
"""
        
        return intro
    
    def _build_instructions(self) -> str:
        """Build analysis instructions."""
        base_instructions = """
## ANALYSIS INSTRUCTIONS

Analyze the provided image focusing on observable, evidence-based indicators.

### Output Structure:

1. **Subject Identification**: Number of subjects, primary focus, basic description
2. **Primary Analysis**: Apply the frameworks above to identify key patterns
3. **Confidence & Limitations**: State confidence level and note any image quality issues
"""
        
        # Add custom instructions if provided
        if self.custom_instructions:
            base_instructions += f"\n\n**Additional Instructions**:\n{self.custom_instructions}"
        
        # Adjust detail level based on analysis type
        if self.analysis_type == "quick":
            base_instructions += "\n\n**Brevity Requirement**: Keep response under 300 words. Focus on most significant observable indicators only."
        elif self.analysis_type == "full":
            base_instructions += "\n\n**Detail Requirement**: Provide comprehensive analysis with specific evidence for each observation."
        
        return base_instructions
    
    def _build_ethics_note(self) -> str:
        """Build ethical disclaimer."""
        return """
## ETHICAL CONSIDERATIONS

- For real photographs: Observational analysis based on visible cues only
- For artwork/illustrations: Character design and artistic expression analysis
- Avoid definitive claims about character, intentions, or mental health
- Consider cultural context in interpretation
- Educational, accessibility, and creative purposes only
- NOT for hiring, legal, or professional psychological evaluations
"""


# Convenience functions for common use cases

def build_quick_profiler_prompt() -> str:
    """
    Build a quick profiler prompt (~800 tokens).
    
    Use for:
    - Rapid emotion detection
    - Token-constrained scenarios
    - Initial screening
    """
    return (
        VisionPromptBuilder()
        .set_analysis_type("quick")
        .add_framework("ekman")
        .build()
    )


def build_standard_profiler_prompt() -> str:
    """
    Build a standard profiler prompt (~1800 tokens).
    
    Use for:
    - General profiling tasks
    - Balanced detail vs. cost
    - Most common use cases
    """
    return (
        VisionPromptBuilder()
        .set_analysis_type("standard")
        .add_framework("ekman")
        .add_framework("fbi")
        .build()
    )


def build_full_profiler_prompt() -> str:
    """
    Build a comprehensive profiler prompt (~2400 tokens).
    
    Use for:
    - Detailed forensic analysis
    - Academic/research applications
    - When token budget allows
    """
    return (
        VisionPromptBuilder()
        .set_analysis_type("full")
        .add_framework("ekman")
        .add_framework("fbi")
        .build()
    )
