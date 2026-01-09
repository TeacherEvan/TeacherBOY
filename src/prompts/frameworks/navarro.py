"""Navarro Body Language Framework - FBI nonverbal communication principles.

Based on Joe Navarro's 25+ years of FBI experience analyzing body language
for investigative purposes.

Token estimates:
- Short version: ~250 tokens (key indicators only)
- Standard version: ~500 tokens (comprehensive body language analysis)
- Full version: ~800 tokens (complete framework with all details)
"""


class NavarroBodyLanguageFramework:
    """Joe Navarro's FBI body language analysis framework."""
    
    VERSION = "2.0"
    CATEGORY = "vision"
    
    # Token estimates for each version
    TOKENS_SHORT = 250
    TOKENS_STANDARD = 500
    TOKENS_FULL = 800
    
    @staticmethod
    def get_short() -> str:
        """
        Brief version - key body language indicators.
        
        Use for:
        - Quick posture assessment
        - General comfort/discomfort detection
        - Token-constrained scenarios
        
        Estimated tokens: ~250
        """
        return """
## Navarro's Key Body Language Indicators

**Most Reliable**: Limbic responses (freeze/flight/fight) reveal true emotional state

1. **Feet & Legs** (most honest body part):
   - Foot direction = interest/disinterest
   - Happy feet (bouncing) = positive emotion
   - Locked ankles = restraining negative emotions

2. **Torso**: 
   - Facing toward = engagement
   - Turning away = discomfort
   - Arms crossed = barrier/self-soothing

3. **Hands**:
   - Steepling = confidence
   - Self-touching (neck, face) = anxiety
   - Hidden hands = potential concealment

4. **Neck & Shoulders**:
   - Neck touching = insecurity
   - Exposed neck = comfort/confidence
"""
    
    @staticmethod
    def get_standard() -> str:
        """
        Standard version - comprehensive body language analysis.
        
        Use for:
        - Professional profiling
        - Standard analysis depth
        - Balanced token usage
        
        Estimated tokens: ~500
        """
        return """
## Joe Navarro's FBI Body Language Analysis

**Apply evidence-based nonverbal communication principles:**

### 1. LIMBIC SYSTEM RESPONSES (Most Reliable)
- **Freeze**: Stillness, minimal movement, reduced blinking
- **Flight**: Distancing, turning away, barrier behaviors
- **Fight**: Puffing up, aggressive posture, forward lean

### 2. FEET AND LEGS (Most Honest Body Part)
- Foot direction indicates interest/disinterest
- Happy feet (bouncing, wiggling) = positive emotion
- Locked ankles = restraining negative emotions
- Crossed legs = comfort indicator in safe environments
- Weight distribution reveals confidence/uncertainty

### 3. TORSO DISPLAYS
- **Ventral fronting**: Facing toward = engagement
- **Ventral denial**: Turning away = discomfort
- **Torso shield**: Barriers (arms, objects) = protection
- **Puffing up chest** = confidence/dominance display

### 4. ARM AND HAND BEHAVIORS
- Arm crossing: self-soothing or barrier (context-dependent)
- Hand steepling: confidence indicator
- Palm-up gestures: openness and honesty
- Self-touching: pacifying behaviors (neck, face, arm)
- Hidden hands: potentially concealing information
- Thumbs up/out = confidence; thumbs hidden = low confidence

### 5. NECK AND SHOULDER TELLS
- Neck touching: insecurity, doubt, discomfort
- Shoulder shrug (partial): lack of commitment
- Turtle effect (head sinking): stress response
- Exposed neck: comfort and confidence

### 6. FACIAL TELLS
- Lip compression: stress or negative emotion
- Lip licking: nervousness or stress-induced dry mouth
- Nose touching: anxiety indicator
- Eye blocking: hand to eyes = disbelief or stress
"""
    
    @staticmethod
    def get_full() -> str:
        """
        Full version - complete framework with all details.
        
        Use for:
        - Deep psychological analysis
        - Professional forensic profiling
        - Maximum accuracy requirements
        
        Estimated tokens: ~800
        """
        return """
## Joe Navarro's FBI Body Language Analysis (Complete Framework)

**Apply these evidence-based nonverbal communication principles from 25+ years FBI experience:**

### 1. LIMBIC SYSTEM RESPONSES (Most Reliable - Honest Reactions)
The limbic brain responds before conscious thought, revealing true emotions:
- **Freeze response**: Stillness, minimal movement, reduced blinking, breath-holding
- **Flight response**: Distancing, turning away, barrier behaviors, leaning back
- **Fight response**: Puffing up, aggressive posture, forward lean, territorial expansion

### 2. FEET AND LEGS (Most Honest Body Part - Least Controlled)
Lower body reveals true intentions because it's farthest from conscious control:
- **Foot direction** indicates genuine interest/disinterest (point toward what we like)
- **Happy feet**: Bouncing, wiggling, jiggling = positive emotion, excitement
- **Locked ankles**: Restraining negative emotions, holding back
- **Crossed legs**: Comfort indicator in safe environments (NOT always defensive)
- **Standing**: Weight distribution and balance reveal confidence/uncertainty
- **Knee clasp**: Holding knees when seated = need for psychological support

### 3. TORSO DISPLAYS (Core Emotional Indicators)
The torso protects vital organs, so positioning reveals comfort/threat assessment:
- **Ventral fronting**: Facing toward someone/something = engagement, interest
- **Ventral denial**: Turning torso away = discomfort, disinterest
- **Torso shield**: Using arms, objects, or barriers = self-protection
- **Puffing up chest** = confidence, dominance display, territorial claim
- **Caving in chest** = low confidence, submission, defeat

### 4. ARM AND HAND BEHAVIORS (Emotional Regulation & Honesty)
Arms and hands are highly expressive but also consciously controlled:
- **Arm crossing**: Context-dependent - can be self-soothing OR barrier
- **Hand steepling**: High confidence indicator, authority
- **Palm-up gestures**: Openness, honesty, supplication
- **Self-touching**: Pacifying behaviors - neck, face, arm rubs indicate stress
- **Hidden hands**: Potentially concealing information or nervous
- **Thumbs**: Thumbs up/out = confidence; thumbs hidden = low confidence
- **Interlaced fingers with thumbs up** = very high confidence
- **Touching face** = self-soothing when stressed

### 5. NECK AND SHOULDER TELLS (Vulnerability Indicators)
Neck is vulnerable area - how we protect it reveals emotional state:
- **Neck touching/covering**: Insecurity, doubt, discomfort, vulnerability
- **Shoulder shrug** (partial): Lack of commitment to statement
- **Turtle effect** (head sinking into shoulders): Stress response, withdrawal
- **Exposed neck**: Comfort, confidence, trust in environment
- **Shoulder tension**: Holding shoulders high = stress, anxiety

### 6. FACIAL TELLS (Secondary to Body Language)
Face is most consciously controlled but still reveals:
- **Lip compression**: Stress, disagreement, negative emotion
- **Lip licking**: Nervousness or dry mouth from stress
- **Nose touching**: Anxiety indicator (nerve endings respond to stress)
- **Eye blocking**: Hand to eyes = disbelief, stress, "I don't want to see this"
- **Genuine vs. fake smile**: Real smiles engage eyes (Duchenne smile)

### KEY PRINCIPLE
**Context is everything**. A single gesture means little; clusters of behaviors reveal truth.
**Baseline first**: Establish normal behavior before identifying deviations.
"""


# Export for easy access
NAVARRO_FRAMEWORK_SHORT = NavarroBodyLanguageFramework.get_short()
NAVARRO_FRAMEWORK_STANDARD = NavarroBodyLanguageFramework.get_standard()
NAVARRO_FRAMEWORK_FULL = NavarroBodyLanguageFramework.get_full()
