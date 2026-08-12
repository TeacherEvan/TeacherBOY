"""FaceLLaVA Framework - Advanced facial attribute and expression understanding.

Based on Face-LLaVA research (WACV 2026) - arxiv:2504.07198
Provides structured facial analysis with intensity metrics and compound emotions.

Token estimates:
- Short version: ~200 tokens (basic attributes)
- Standard version: ~400 tokens (attributes + compound emotions)
- Full version: ~600 tokens (complete framework with intensity metrics)
"""


class FaceLLaVAFramework:
    """Face-LLaVA enhanced facial analysis framework."""

    VERSION = "2.0"
    CATEGORY = "vision"

    # Token estimates for each version
    TOKENS_SHORT = 200
    TOKENS_STANDARD = 400
    TOKENS_FULL = 600

    @staticmethod
    def get_short() -> str:
        """
        Brief version - basic facial attributes.

        Use for:
        - Quick attribute detection
        - Demographic estimation
        - Token-efficient scenarios

        Estimated tokens: ~200
        """
        return """
## FaceLLaVA Facial Attribute Detection

Systematically identify visible facial attributes:
- **Age Range**: Child/Teen/Young Adult/Middle-aged/Senior
- **Gender Presentation**: Masculine/Feminine/Androgynous features
- **Facial Structure**: Round/Oval/Square/Heart-shaped
- **Skin Tone/Complexion**: Light/Medium/Dark with health indicators
- **Hair**: Style, color, grooming level
- **Accessories**: Glasses, jewelry, makeup level
"""

    @staticmethod
    def get_standard() -> str:
        """
        Standard version - attributes + compound emotions.

        Use for:
        - Professional analysis
        - Balanced token/quality
        - Standard profiling depth

        Estimated tokens: ~400
        """
        return """
## FaceLLaVA-Enhanced Facial Analysis

**Based on Face-LLaVA research (WACV 2026) - State-of-the-art facial understanding**

### FACIAL ATTRIBUTE DETECTION
Systematically identify visible attributes:
- **Age Range**: Estimate bracket (child/teen/young adult/middle-aged/senior)
- **Gender Presentation**: Masculine/Feminine/Androgynous features
- **Skin Tone/Complexion**: Light/Medium/Dark, health indicators
- **Hair**: Style, color, grooming level
- **Facial Hair**: Presence, style, grooming
- **Accessories**: Glasses, jewelry, makeup level
- **Facial Structure**: Round/Oval/Square/Heart-shaped

### COMPOUND EMOTION DETECTION
Identify complex emotional states beyond basic emotions:
- **Happily Surprised**: Joy + Surprise blend (positive excitement)
- **Sadly Angry**: Sadness + Anger blend (grief-driven anger)
- **Fearfully Surprised**: Fear + Surprise blend (shock)
- **Disgusted Anger**: Disgust + Anger blend (moral outrage)
- **Awe**: Surprise + Fear in positive context (wonder)
- **Contemptuous Amusement**: Contempt + mild happiness (smirking at someone)
"""

    @staticmethod
    def get_full() -> str:
        """
        Full version - complete framework with intensity metrics.

        Use for:
        - Research-grade analysis
        - Maximum detail requirements
        - Professional forensic work

        Estimated tokens: ~600
        """
        return """
## FaceLLaVA-Enhanced Facial Analysis (Complete Framework)

**Based on Face-LLaVA research (WACV 2026, arxiv:2504.07198)**
**State-of-the-art facial attribute and expression understanding**

### FACIAL ATTRIBUTE DETECTION
Systematically identify visible facial attributes:
- **Age Range**: Estimate age bracket (child/teen/young adult/middle-aged/senior)
- **Gender Presentation**: Masculine/Feminine/Androgynous features
- **Skin Tone/Complexion**: Light/Medium/Dark, health indicators, texture
- **Hair**: Style, color, length, grooming level, cultural markers
- **Facial Hair**: Presence, style (beard/mustache/stubble), grooming
- **Accessories**: Glasses, jewelry, piercings, makeup level
- **Facial Structure**: Round/Oval/Square/Heart-shaped, bone structure prominence

### EXPRESSION INTENSITY METRICS
Rate each detected expression on a 0-100 scale:
- **Intensity Score**: How strongly the emotion presents (subtle/moderate/intense)
  * 0-30: Subtle, barely perceptible
  * 31-65: Moderate, clearly visible
  * 66-100: Intense, strongly expressed

- **Authenticity Score**: Genuine vs. posed/performed
  * Look for micro-expression congruence
  * Check for eye involvement (genuine emotions engage eyes)
  * Assess timing (genuine emotions appear simultaneously with context)

- **Duration Indicators**: Sustained vs. fleeting expression
  * Sustained (>2 sec): Genuine emotional state
  * Fleeting (<500ms): Microexpression or suppressed emotion

- **Symmetry Score**: Bilateral symmetry of expression
  * Symmetric: More likely genuine
  * Asymmetric: Possible posed/controlled emotion

### COMPOUND EMOTION DETECTION
Identify complex emotional states beyond basic emotions:
- **Happily Surprised**: Joy + Surprise blend
  * Indicators: Wide eyes + genuine smile + raised brows
  * Context: Positive unexpected events

- **Sadly Angry**: Sadness + Anger blend
  * Indicators: Downturned mouth + furrowed brow + tense jaw
  * Context: Grief-driven anger, sense of injustice

- **Fearfully Surprised**: Fear + Surprise blend
  * Indicators: Wide eyes + open mouth + tense body
  * Context: Shock, sudden threat

- **Disgusted Anger**: Disgust + Anger blend
  * Indicators: Nose wrinkle + lowered brows + tight lips
  * Context: Moral outrage, violated values

- **Awe**: Surprise + Fear (positive context)
  * Indicators: Wide eyes + slight mouth opening + relaxed brow
  * Context: Wonder, spiritual/aesthetic experience

- **Contemptuous Amusement**: Contempt + mild happiness
  * Indicators: Unilateral lip raise + slight smile
  * Context: Smirking at someone, superiority display

### ANALYSIS GUIDELINES
1. **Avoid single-indicator reliance**: Use multiple cues for accuracy
2. **Consider cultural context**: Some expressions vary by culture
3. **Assess temporal dynamics**: When does the expression appear?
4. **Look for incongruence**: Do facial expression and context match?
"""


# Export for easy access
FACELLAVA_FRAMEWORK_SHORT = FaceLLaVAFramework.get_short()
FACELLAVA_FRAMEWORK_STANDARD = FaceLLaVAFramework.get_standard()
FACELLAVA_FRAMEWORK_FULL = FaceLLaVAFramework.get_full()
