"""Color Psychology Framework - Analysis of clothing and environmental colors.

Provides psychological significance of color choices in appearance and surroundings.

Token estimates:
- Short version: ~150 tokens (primary colors only)
- Standard version: ~300 tokens (comprehensive color meanings)
- Full version: ~400 tokens (colors + combinations)
"""


class ColorPsychologyFramework:
    """Color psychology analysis framework."""

    VERSION = "2.0"
    CATEGORY = "vision"

    # Token estimates for each version
    TOKENS_SHORT = 150
    TOKENS_STANDARD = 300
    TOKENS_FULL = 400

    @staticmethod
    def get_short() -> str:
        """
        Brief version - primary colors only.

        Use for:
        - Quick color assessment
        - Token-constrained scenarios
        - Basic profiling

        Estimated tokens: ~150
        """
        return """
## Color Psychology (Primary Colors)

Analyze clothing/environmental colors:
- **Red**: Power, passion, energy, aggression
- **Blue**: Trust, calm, authority, professionalism
- **Green**: Balance, growth, harmony, nature
- **Yellow**: Optimism, creativity, caution
- **Black**: Power, elegance, authority
- **White**: Purity, simplicity, cleanliness
- **Gray**: Neutrality, sophistication
"""

    @staticmethod
    def get_standard() -> str:
        """
        Standard version - comprehensive color meanings.

        Use for:
        - Professional analysis
        - Standard profiling depth
        - Balanced detail

        Estimated tokens: ~300
        """
        return """
## Color Psychology Analysis

**Analyze clothing and environmental colors for psychological significance:**

### PRIMARY COLOR INDICATORS
- **Red**: Power, passion, aggression, energy, attention-seeking
- **Blue**: Trust, calm, authority, stability, professionalism
- **Green**: Balance, growth, harmony, nature connection, renewal
- **Yellow**: Optimism, creativity, caution, intellectual stimulation
- **Orange**: Enthusiasm, warmth, sociability, adventure
- **Purple**: Luxury, creativity, spirituality, uniqueness
- **Black**: Power, elegance, mystery, sophistication, authority
- **White**: Purity, simplicity, cleanliness, new beginnings
- **Gray**: Neutrality, balance, sophistication, detachment
- **Brown**: Reliability, earthiness, warmth, stability
- **Pink**: Nurturing, romantic, youthful, compassionate
"""

    @staticmethod
    def get_full() -> str:
        """
        Full version - colors + combinations.

        Use for:
        - Deep psychological analysis
        - Professional profiling
        - Maximum insight

        Estimated tokens: ~400
        """
        return """
## Color Psychology Analysis (Complete Framework)

**Analyze clothing and environmental colors for psychological significance:**

### PRIMARY COLOR INDICATORS
- **Red**: Power, passion, aggression, energy, attention-seeking, danger
  * Dark red: Sophistication, maturity
  * Bright red: Boldness, confidence, sometimes aggression

- **Blue**: Trust, calm, authority, stability, professionalism
  * Navy: Authority, conservatism, traditional
  * Light blue: Peace, serenity, approachability

- **Green**: Balance, growth, harmony, nature connection, renewal
  * Dark green: Wealth, prestige, traditionalism
  * Bright green: Vitality, freshness, environmental awareness

- **Yellow**: Optimism, creativity, caution, intellectual stimulation
  * Can indicate anxiety or nervousness if too bright
  * Gold/golden: Success, prestige, quality

- **Orange**: Enthusiasm, warmth, sociability, adventure, spontaneity
  * Can be attention-seeking or energetic

- **Purple**: Luxury, creativity, spirituality, uniqueness, mystery
  * Deep purple: Royalty, wisdom, dignity
  * Light purple: Romance, nostalgia

- **Black**: Power, elegance, mystery, sophistication, authority
  * Can indicate mourning or rebellion depending on context
  * Professional standard in many contexts

- **White**: Purity, simplicity, cleanliness, new beginnings
  * Sterility or coldness in excess

- **Gray**: Neutrality, balance, sophistication, detachment
  * Can indicate indecision or lack of emotion

- **Brown**: Reliability, earthiness, warmth, stability, approachability
  * Natural, unpretentious

- **Pink**: Nurturing, romantic, youthful, compassionate
  * Bright pink: Playful, energetic
  * Pale pink: Gentle, calming

### CLOTHING COLOR COMBINATIONS
- **Monochromatic**: Focused, deliberate, confident, minimalist
- **Contrasting**: Bold, attention-seeking, creative, confident
- **Neutral palette**: Professional, understated, practical, conservative
- **Bright colors**: Extroverted, energetic, optimistic, youthful
- **Dark colors**: Formal, authoritative, reserved, serious
- **Pastel colors**: Gentle, approachable, soft, non-threatening

### ENVIRONMENTAL COLOR CONTEXT
- **Warm-toned environment**: Energizing, stimulating, social
- **Cool-toned environment**: Calming, professional, focused
- **Cluttered/many colors**: Chaotic, creative, informal
- **Minimal/neutral**: Organized, professional, controlled
"""


# Export for easy access
COLOR_FRAMEWORK_SHORT = ColorPsychologyFramework.get_short()
COLOR_FRAMEWORK_STANDARD = ColorPsychologyFramework.get_standard()
COLOR_FRAMEWORK_FULL = ColorPsychologyFramework.get_full()
