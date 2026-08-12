"""FBI BAU Framework - Behavioral Analysis Unit methodology.

This module provides FBI profiling frameworks for behavioral analysis
from visual cues and environmental context.

Token estimates:
- Short version: ~200 tokens (key indicators only)
- Standard version: ~400 tokens (core methodology)
- Full version: ~600 tokens (complete BAU framework)
"""


class FBIBAUFramework:
    """FBI Behavioral Analysis Unit profiling methodology."""

    VERSION = "2.0"
    CATEGORY = "vision"

    TOKENS_SHORT = 200
    TOKENS_STANDARD = 400
    TOKENS_FULL = 600

    @staticmethod
    def get_short() -> str:
        """
        Brief version - key behavioral indicators.

        Estimated tokens: ~200
        """
        return """
## FBI Behavioral Analysis (Brief)

**Key Assessment Areas:**

1. **Victimology/Subject Assessment**
   - Age and demographic markers
   - Socioeconomic status indicators
   - Health and wellness signs

2. **Behavioral Patterns**
   - Baseline vs. stressed behavior
   - Fight/flight/freeze responses
   - Personal space dynamics

3. **Cognitive Load**
   - Signs of mental effort
   - Decision-making posture
   - Attention patterns

4. **Social Dynamics**
   - Dominance vs. submission
   - Affiliation indicators
   - Status markers
"""

    @staticmethod
    def get_standard() -> str:
        """
        Standard version - core BAU methodology.

        Estimated tokens: ~400
        """
        return """
## FBI Behavioral Analysis Unit (BAU) Framework

### 1. Victimology/Subject Assessment

**Demographic Indicators:**
- Age estimation from physical markers (skin, posture, fashion)
- Gender presentation and conformity to norms
- Ethnic/cultural markers in appearance and behavior

**Socioeconomic Status:**
- Clothing quality and brand markers
- Grooming standards (professional vs. casual)
- Accessories and status symbols
- Condition of personal items

**Lifestyle Indicators:**
- Activity level (athletic build, sedentary markers)
- Occupational markers (calluses, posture, sun exposure)
- Health and wellness (nutrition, sleep, stress markers)
- Substance use indicators (if visible)

### 2. Behavioral Indicators

**Baseline vs. Stressed Behavior:**
- Identify "normal" behavior for subject's demographics
- Note deviations suggesting stress or deception
- Look for incongruence between verbal and nonverbal

**Limbic System Responses:**
- **Freeze**: Stillness, reduced blinking, minimal movement
- **Flight**: Distancing, turning away, creating barriers
- **Fight**: Puffing up, aggressive posture, forward lean

**Territorial Dynamics:**
- Personal space preferences (culture-dependent)
- Comfort with proximity to others
- Defensive positioning or barrier creation

### 3. Cognitive Load Assessment

**Mental Effort Indicators:**
- Furrowed brow (concentration)
- Lip compression (processing information)
- Gaze direction (constructive vs. recall)
- Processing delays (slower responses)

**Decision-Making Posture:**
- Leaning back: Evaluating, skeptical
- Leaning forward: Engaged, interested
- Neutral: Balanced consideration

**Attention Patterns:**
- Focused gaze: High engagement
- Wandering eyes: Distraction, boredom
- Avoiding gaze: Discomfort, deception

### 4. Social Dynamics

**Power and Status:**
- **Dominance**: Expansive posture, direct gaze, taking space
- **Submission**: Contracted posture, averted gaze, minimal space
- **Neutral**: Balanced, non-threatening stance

**Affiliation Signals:**
- Mirroring: Rapport and connection
- Open posture: Receptiveness
- Closed posture: Defensiveness or discomfort

**Group Dynamics** (if multiple subjects):
- Leader identification: Central position, others orient toward
- Follower patterns: Deferential body language
- Outlier identification: Physical distance, different orientation
"""

    @staticmethod
    def get_full() -> str:
        """
        Complete version - comprehensive BAU profiling.

        Estimated tokens: ~600
        """
        return f"""{FBIBAUFramework.get_standard()}

### 5. Advanced Behavioral Profiling

**Emotional State Reconstruction:**
- Identify primary emotion from facial cues
- Note secondary/suppressed emotions
- Assess emotional congruence with context
- Detect emotional leakage or masking

**Stress and Anxiety Markers:**
- Physiological: Pupil dilation, flushed skin, sweating
- Behavioral: Pacifying behaviors, grooming gestures
- Postural: Tension, rigid stance, protective positioning
- Facial: Microexpressions, eye blocking, lip compression

**Deception Indicators** (cluster required, not individual signs):
- Incongruent expressions (emotion doesn't match context)
- Asymmetric facial displays
- Timing delays between speech and expression
- Excessive baseline variations
- Cognitive load markers (thinking hard about response)
- Self-soothing behaviors (pacifying gestures)

**Personality Trait Indicators:**
- **Conscientiousness**: Neat appearance, organized posture
- **Extraversion**: Animated expressions, open body language
- **Neuroticism**: Tension markers, anxious behaviors
- **Agreeableness**: Warm expressions, affiliative gestures
- **Openness**: Creative presentation, unconventional styling

### 6. Environmental Context Integration

**Setting Analysis:**
- Professional: Formal dress, composed demeanor expected
- Casual: Relaxed posture, informal presentation
- Public: Guarded behavior, social performance
- Private: Authentic behavior, less filtering

**Situational Appropriateness:**
- Dress matches context: Indicates planning, awareness
- Dress mismatches: May suggest transition, stress, or values
- Behavior matches setting: Social competence
- Behavior conflicts: Stress, distraction, or defiance

**Cultural Context Considerations:**
- Collectivist cultures: Group harmony, restrained expression
- Individualist cultures: Self-expression, direct communication
- High-context: Subtle cues, implicit communication
- Low-context: Explicit communication, direct expression

### Profiling Best Practices

1. **Cluster Analysis**: Never rely on single indicator
2. **Baseline Comparison**: Establish normal, note deviations
3. **Context Integration**: Behavior must fit situation
4. **Cultural Sensitivity**: Adjust interpretations accordingly
5. **Probabilistic**: Use terms like "suggests" not "proves"
6. **Ethics**: Avoid diagnosis, focus on observations
"""

    @staticmethod
    def get_for_analysis_type(analysis_type: str) -> str:
        """Get appropriate version based on analysis depth."""
        mapping = {
            "quick": FBIBAUFramework.get_short,
            "standard": FBIBAUFramework.get_standard,
            "full": FBIBAUFramework.get_full,
        }

        getter = mapping.get(analysis_type, FBIBAUFramework.get_standard)
        return getter()

    @staticmethod
    def estimate_tokens(analysis_type: str) -> int:
        """Estimate token usage for analysis type."""
        mapping = {
            "quick": FBIBAUFramework.TOKENS_SHORT,
            "standard": FBIBAUFramework.TOKENS_STANDARD,
            "full": FBIBAUFramework.TOKENS_FULL,
        }

        return mapping.get(analysis_type, FBIBAUFramework.TOKENS_STANDARD)
