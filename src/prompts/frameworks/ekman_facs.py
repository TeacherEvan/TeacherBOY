"""Ekman FACS Framework - Modular facial expression analysis.

This module provides Paul Ekman's Facial Action Coding System in multiple
granularities for token-efficient prompt composition.

Token estimates:
- Short version: ~300 tokens (7 universal emotions only)
- Standard version: ~700 tokens (AU codes + emotions)
- Full version: ~1200 tokens (complete FACS with all AU codes)
"""


class EkmanFACSFramework:
    """Paul Ekman's Facial Action Coding System - modular versions."""
    
    VERSION = "2.0"
    CATEGORY = "vision"
    
    # Token estimates for each version
    TOKENS_SHORT = 300
    TOKENS_STANDARD = 700
    TOKENS_FULL = 1200
    
    @staticmethod
    def get_short() -> str:
        """
        Brief version - 7 universal emotions only.
        
        Use for:
        - Quick emotion detection
        - Token-constrained scenarios
        - Mobile/low-latency applications
        
        Estimated tokens: ~300
        """
        return """
## Ekman's 7 Universal Emotions (Brief)

Identify emotions using these core patterns:

1. **Happiness**: AU6 (crow's feet) + AU12 (smile) - Genuine smile shows eye wrinkles
2. **Sadness**: AU1 (inner brow raise) + AU4 (brow lowerer) + AU15 (lip corner depression)
3. **Fear**: AU1+AU2 (raised brows) + AU4 (lowered brows) + AU5 (wide eyes) + AU20 (stretched lips)
4. **Anger**: AU4 (lowered brows) + AU5 (upper lid raise) + AU7 (tightened lids) + AU23/24 (compressed lips)
5. **Surprise**: AU1+AU2 (raised brows) + AU5 (wide eyes) + AU26 (jaw drop) - Brief duration
6. **Disgust**: AU9 (nose wrinkle) + AU10 (raised upper lip) + AU17 (chin raise)
7. **Contempt**: AU14 (unilateral lip corner raise) - One-sided smirk indicating superiority

**Authenticity Check**: Genuine emotions show symmetry and involve eyes. Fake smiles lack AU6.
"""
    
    @staticmethod
    def get_standard() -> str:
        """
        Standard version - AU codes with practical guidance.
        
        Use for:
        - General profiling tasks
        - Balanced token usage vs. detail
        - Most common use cases
        
        Estimated tokens: ~700
        """
        return """
## Paul Ekman's FACS - Facial Action Units

### Key Action Units (AUs)

**Upper Face:**
- AU1: Inner Brow Raiser (frontalis medialis) - Surprise, fear
- AU2: Outer Brow Raiser (frontalis lateralis) - Surprise, fear
- AU4: Brow Lowerer (corrugator) - Anger, concentration
- AU5: Upper Lid Raiser (levator palpebrae) - Surprise, fear
- AU6: Cheek Raiser (orbicularis oculi) - Genuine happiness
- AU7: Lid Tightener (orbicularis oculi pars palpebralis) - Anger, squinting

**Lower Face:**
- AU9: Nose Wrinkler (levator labii superioris alaquae nasi) - Disgust
- AU10: Upper Lip Raiser (levator labii superioris) - Disgust
- AU12: Lip Corner Puller (zygomaticus major) - Smile (fake if without AU6)
- AU14: Dimpler (buccinator) - Contempt (unilateral)
- AU15: Lip Corner Depressor (depressor anguli oris) - Sadness
- AU17: Chin Raiser (mentalis) - Disgust, sadness
- AU20: Lip Stretcher (risorius) - Fear
- AU23: Lip Tightener (orbicularis oris) - Anger
- AU24: Lip Presser (orbicularis oris) - Anger, tension
- AU25: Lips Part (relaxation) - Surprise, concentration
- AU26: Jaw Drop (masseter relaxation) - Surprise
- AU27: Mouth Stretch (pterygoids) - Pain, effort

### The 7 Universal Emotions with AU Signatures

**Happiness**: AU6 + AU12 (Duchenne smile)  
**Sadness**: AU1 + AU4 + AU15  
**Fear**: AU1 + AU2 + AU4 + AU5 + AU20 + AU25/26  
**Anger**: AU4 + AU5 + AU7 + AU23/24  
**Surprise**: AU1 + AU2 + AU5 + AU26  
**Disgust**: AU9 + AU10 + AU17  
**Contempt**: AU14 (unilateral - key marker)  

### Microexpression Detection
- **Duration**: < 500ms indicates concealed emotion
- **Intensity**: Partial expressions suggest suppression
- **Timing**: Genuine emotions appear simultaneously with speech
- **Symmetry**: Asymmetry may indicate deception
"""
    
    @staticmethod
    def get_full() -> str:
        """
        Complete version - comprehensive FACS reference.
        
        Use for:
        - Detailed forensic analysis
        - Academic/research applications
        - When token budget allows
        
        Estimated tokens: ~1200
        """
        return f"""{EkmanFACSFramework.get_standard()}

### Complete AU Reference

**Additional Upper Face AUs:**
- AU41: Lid Drop (relaxation) - Fatigue, drowsiness
- AU42: Slit (orbicularis oculi) - Squint, concentration
- AU43: Eyes Closed (orbicularis oculi) - Blink, rest
- AU44: Squint (orbicularis oculi) - Bright light, concentration
- AU45: Blink (orbicularis oculi) - Normal rate: 15-20/min
- AU46: Wink (orbicularis oculi) - Social signal

**Additional Lower Face AUs:**
- AU16: Lower Lip Depressor (depressor labii inferioris) - Sadness, disgust
- AU18: Lip Puckerer (incisivus labii superioris) - Kiss, doubt
- AU22: Lip Funneler (orbicularis oris) - Concentration
- AU28: Lip Suck (orbicularis oris) - Anxiety, nervousness

**Head Movement Codes:**
- M51: Head turn left
- M52: Head turn right
- M53: Head up
- M54: Head down
- M55: Head tilt left
- M56: Head tilt right
- M57: Head forward
- M58: Head back

### Emotion Blends and Complex States

**Compound Emotions:**
- **Happily Surprised**: AU1+AU2+AU6+AU12 (joy + surprise)
- **Sadly Angry**: AU1+AU4+AU7+AU15 (sadness + anger blend)
- **Fearfully Surprised**: AU1+AU2+AU5+AU20 with high intensity
- **Disgusted Anger**: AU9+AU10+AU4+AU7 (disgust + anger)
- **Contemptuous Amusement**: AU14 + mild AU12

### Deception Indicators

**Micro-leakage Signs:**
1. Brief contradictory expressions (< 500ms)
2. Asymmetric facial displays (unilateral AUs outside AU14)
3. Delayed onset relative to speech
4. Incongruent eye vs. mouth expressions
5. Excessive blinking or eye blocking (AU43)
6. Lip compression (AU23/24) - concealing information
7. Nose touching or face covering gestures

### Cultural Considerations

While the 7 universal emotions are cross-cultural, display rules vary:
- **Western**: More facial expressiveness encouraged
- **East Asian**: Emotional restraint valued, subtle expressions
- **Mediterranean**: Expressive, animated facial movements
- **Nordic**: Reserved, controlled expressions

Note: Always consider context and individual baselines.
"""
    
    @staticmethod
    def get_for_analysis_type(analysis_type: str) -> str:
        """
        Get appropriate version based on analysis depth.
        
        Args:
            analysis_type: "quick", "standard", or "full"
            
        Returns:
            Framework text optimized for analysis type
        """
        mapping = {
            "quick": EkmanFACSFramework.get_short,
            "standard": EkmanFACSFramework.get_standard,
            "full": EkmanFACSFramework.get_full,
        }
        
        getter = mapping.get(analysis_type, EkmanFACSFramework.get_standard)
        return getter()
    
    @staticmethod
    def estimate_tokens(analysis_type: str) -> int:
        """
        Estimate token usage for analysis type.
        
        Args:
            analysis_type: "quick", "standard", or "full"
            
        Returns:
            Estimated token count
        """
        mapping = {
            "quick": EkmanFACSFramework.TOKENS_SHORT,
            "standard": EkmanFACSFramework.TOKENS_STANDARD,
            "full": EkmanFACSFramework.TOKENS_FULL,
        }
        
        return mapping.get(analysis_type, EkmanFACSFramework.TOKENS_STANDARD)
