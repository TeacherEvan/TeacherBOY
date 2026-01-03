"""
Psychological Profiler Service - Advanced behavioral analysis from photos.

This service implements comprehensive psychological profiling using established
frameworks from behavioral science and forensic psychology:

- Paul Ekman's Facial Action Coding System (FACS) & 7 Universal Emotions
- Joe Navarro's FBI body language principles
- FBI Behavioral Analysis Unit (BAU) methodology
- Color psychology and environmental profiling

DISCLAIMER: This is an AI-assisted analysis tool for educational and entertainment
purposes only. It should NOT be used for making actual psychological assessments,
hiring decisions, legal judgments, or any professional evaluations.
"""

import logging
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProfileAnalysis:
    """Structured psychological profile analysis result."""
    
    # Subject identification
    subject_count: int = 0
    primary_subject_description: str = ""
    
    # Facial analysis (Ekman Framework)
    primary_emotion: str = ""  # One of 7 universal emotions
    emotion_intensity: str = ""  # low/medium/high
    secondary_emotions: List[str] = field(default_factory=list)
    facial_symmetry: str = ""  # balanced/asymmetric
    microexpression_indicators: List[str] = field(default_factory=list)
    
    # Eye analysis
    gaze_direction: str = ""
    eye_contact_quality: str = ""
    pupil_indicators: str = ""
    
    # Body language (Navarro Principles)
    posture_type: str = ""  # open/closed/neutral
    confidence_indicators: List[str] = field(default_factory=list)
    stress_indicators: List[str] = field(default_factory=list)
    comfort_level: str = ""  # comfortable/uncomfortable/mixed
    hand_position: str = ""
    barrier_behaviors: List[str] = field(default_factory=list)
    
    # Clothing analysis
    clothing_style: str = ""
    formality_level: str = ""
    color_psychology: str = ""
    condition_indicators: str = ""
    
    # Environmental context
    setting_type: str = ""
    environment_mood: str = ""
    social_context: str = ""
    
    # Action/Activity
    current_action: str = ""
    energy_level: str = ""
    
    # Overall assessment
    behavioral_summary: str = ""
    personality_indicators: List[str] = field(default_factory=list)
    deception_indicators: List[str] = field(default_factory=list)
    authenticity_assessment: str = ""
    
    # Raw analysis
    full_analysis: str = ""
    confidence_score: str = ""  # low/medium/high
    
    # Metadata
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# FBI Behavioral Analysis Framework
# ============================================================================

FBI_BAU_FRAMEWORK = """
## FBI Behavioral Analysis Unit (BAU) Assessment Framework

Apply the following investigative profiling methodology:

### 1. VICTIMOLOGY/SUBJECT ASSESSMENT
- Age estimation and demographic indicators
- Social-economic status markers
- Lifestyle indicators visible in appearance
- Health and wellness indicators

### 2. BEHAVIORAL INDICATORS
- Baseline vs. stressed behavior patterns
- Fight/flight/freeze response indicators
- Territorial and personal space dynamics
- Grooming and self-presentation priorities

### 3. COGNITIVE LOAD INDICATORS
- Signs of mental effort or strain
- Decision-making posture
- Information processing indicators
- Attention and focus patterns

### 4. SOCIAL DYNAMICS
- Dominance vs. submission signals
- Affiliation and rapport indicators
- Status and hierarchy markers
- Group dynamics (if multiple subjects)
"""

# ============================================================================
# Paul Ekman's Facial Analysis Framework
# ============================================================================

EKMAN_EMOTIONS_FRAMEWORK = """
## Paul Ekman's Facial Action Coding System (FACS) Analysis

Analyze for the 7 Universal Emotions with specific action unit (AU) indicators:

### 1. HAPPINESS
- AU6: Cheek raiser (crow's feet)
- AU12: Lip corner puller
- Genuine (Duchenne) vs. social smile indicators
- Eye crinkles and spontaneous muscle engagement

### 2. SADNESS
- AU1: Inner brow raiser
- AU4: Brow lowerer
- AU15: Lip corner depressor
- Drooping eyelids and downcast gaze

### 3. FEAR
- AU1+2: Brow raiser (inner + outer)
- AU4: Brow lowerer
- AU5: Upper lid raiser
- AU20: Lip stretcher
- Wide eyes, raised eyebrows, tense mouth

### 4. ANGER
- AU4: Brow lowerer
- AU5: Upper lid raiser
- AU7: Lid tightener
- AU23/24: Lip tightener/presser
- Narrowed eyes, tense jaw, flared nostrils

### 5. SURPRISE
- AU1+2: Brow raiser
- AU5: Upper lid raiser
- AU26: Jaw drop
- Raised eyebrows, wide eyes, open mouth

### 6. DISGUST
- AU9: Nose wrinkler
- AU10: Upper lip raiser
- Wrinkled nose, raised upper lip, asymmetric expression

### 7. CONTEMPT
- AU14: Dimpler (one-sided)
- Unilateral lip corner raise
- Asymmetric expression indicating superiority

### MICROEXPRESSION INDICATORS
- Duration: less than 1/2 second = potential concealed emotion
- Inconsistency between verbal/nonverbal = emotional leakage
- Partial expressions = suppression attempts
"""

# ============================================================================
# Joe Navarro's Body Language Framework
# ============================================================================

NAVARRO_BODY_LANGUAGE = """
## Joe Navarro's FBI Body Language Analysis

Apply these evidence-based nonverbal communication principles:

### 1. LIMBIC SYSTEM RESPONSES (Most Reliable)
- Freeze response: stillness, minimal movement
- Flight response: distancing, turning away, barrier behaviors
- Fight response: puffing up, aggressive posture, forward lean

### 2. FEET AND LEGS (Most Honest Body Part)
- Foot direction indicates interest/disinterest
- Happy feet: bouncing, wiggling = positive emotion
- Locked ankles: restraining negative emotions
- Crossed legs: comfort indicator in safe environments
- Standing: weight distribution and balance

### 3. TORSO DISPLAYS
- Ventral fronting: facing toward = engagement
- Ventral denial: turning away = discomfort
- Torso shield: barriers (arms, objects) = protection
- Puffing up chest = confidence/dominance display

### 4. ARM AND HAND BEHAVIORS
- Arm crossing: self-soothing or barrier (context-dependent)
- Hand steepling: confidence indicator
- Palm-up gestures: openness and honesty
- Self-touching: pacifying behaviors (neck, face, arm)
- Hidden hands: potentially concealing information
- Thumbs up/out: confidence; thumbs hidden = low confidence

### 5. NECK AND SHOULDER TELLS
- Neck touching: insecurity, doubt, discomfort
- Shoulder shrug (partial): lack of commitment
- Turtle effect (head sinking): stress response
- Exposed neck: comfort and confidence

### 6. FACIAL TELLS
- Lip compression: stress or negative emotion
- Lip licking: nervousness or dry mouth from stress
- Nose touching: anxiety indicator
- Eye blocking: hand to eyes = disbelief or stress
- Genuine vs. fake smile detection
"""

# ============================================================================
# Color Psychology Framework
# ============================================================================

COLOR_PSYCHOLOGY_FRAMEWORK = """
## Color Psychology Analysis

Analyze clothing and environmental colors for psychological significance:

### PRIMARY COLOR INDICATORS
- **Red**: Power, passion, aggression, energy, attention-seeking
- **Blue**: Trust, calm, authority, stability, professionalism
- **Green**: Balance, growth, harmony, nature connection
- **Yellow**: Optimism, creativity, caution, intellectual stimulation
- **Orange**: Enthusiasm, warmth, sociability, adventure
- **Purple**: Luxury, creativity, spirituality, uniqueness
- **Black**: Power, elegance, mystery, sophistication, authority
- **White**: Purity, simplicity, cleanliness, new beginnings
- **Gray**: Neutrality, balance, sophistication, detachment
- **Brown**: Reliability, earthiness, warmth, stability
- **Pink**: Nurturing, romantic, youthful, compassionate

### CLOTHING COLOR COMBINATIONS
- Monochromatic: focused, deliberate, confident
- Contrasting: bold, attention-seeking, creative
- Neutral palette: professional, understated, practical
- Bright colors: extroverted, energetic, optimistic
- Dark colors: formal, authoritative, reserved
"""

# ============================================================================
# Master Profiling Prompt
# ============================================================================

MASTER_PROFILING_PROMPT = f"""You are an expert behavioral analyst trained in forensic psychology and nonverbal communication analysis. Your expertise combines:

1. FBI Behavioral Analysis Unit (BAU) profiling methodology
2. Paul Ekman's Facial Action Coding System (FACS) and micro-expression analysis
3. Joe Navarro's body language interpretation (25+ years FBI experience)
4. Environmental psychology and color analysis

{FBI_BAU_FRAMEWORK}

{EKMAN_EMOTIONS_FRAMEWORK}

{NAVARRO_BODY_LANGUAGE}

{COLOR_PSYCHOLOGY_FRAMEWORK}

---

## ANALYSIS INSTRUCTIONS

Analyze the provided image with scientific precision while maintaining ethical boundaries. 

### STRUCTURE YOUR ANALYSIS AS FOLLOWS:

## 🎯 SUBJECT IDENTIFICATION
- Number of subjects and primary focus
- Brief physical description (age range, presentation)

## 😊 FACIAL EXPRESSION ANALYSIS (Ekman Framework)
- **Primary Emotion**: [Identify dominant emotion from 7 universal]
- **Intensity**: [Low/Medium/High]
- **Secondary Emotions**: [Any blended or background emotions]
- **Authenticity**: [Genuine vs. performed expression]
- **Microexpression Indicators**: [Any brief emotional leakage detected]

## 👁️ EYE ANALYSIS
- **Gaze Direction**: Where are they looking?
- **Eye Contact Quality**: Engaged, avoiding, seeking
- **Pupil/Tension Indicators**: What the eyes reveal

## 🧍 BODY LANGUAGE ANALYSIS (Navarro Framework)
- **Posture**: Open/Closed/Neutral - what it reveals
- **Confidence Markers**: High/Medium/Low with specific indicators
- **Stress Indicators**: Pacifying behaviors, tension points
- **Comfort Level**: Overall assessment
- **Hand Position**: What hands reveal about mental state
- **Barrier Behaviors**: Protective gestures or positioning

## 👔 CLOTHING & PRESENTATION ANALYSIS
- **Style Assessment**: What their choices suggest
- **Formality Level**: How dressed vs. context
- **Color Psychology**: Psychological significance of colors worn
- **Condition/Care**: Attention to grooming and presentation

## 🏠 ENVIRONMENTAL CONTEXT
- **Setting Type**: Professional/Casual/Public/Private
- **Environment Mood**: What surroundings suggest
- **Social Context**: Situation implications

## 🎬 ACTION & ENERGY ANALYSIS
- **Current Activity**: What they appear to be doing
- **Energy Level**: High/Moderate/Low
- **Engagement Level**: How present they appear

## 🔍 BEHAVIORAL PROFILE SUMMARY
- **Personality Indicators**: Key traits suggested by analysis
- **Emotional State Assessment**: Overall emotional picture
- **Authenticity Score**: How genuine the presentation appears
- **Key Observations**: Most significant behavioral tells
- **Areas of Note**: Any patterns warranting attention

## ⚠️ CONFIDENCE & LIMITATIONS
- State confidence level in your analysis
- Note any image quality or visibility limitations

---

**IMPORTANT ETHICAL NOTES:**
- This is an observational analysis based on visible cues only
- Avoid making definitive claims about character, intentions, or mental health diagnoses
- Cultural context may affect interpretation of certain behaviors
- This analysis is for educational/entertainment purposes only
- Do NOT use for hiring, legal, or professional psychological evaluations

Provide your analysis in a clear, organized format using the structure above. Be thorough but concise. Focus on observable, evidence-based indicators rather than speculation.
"""


class ProfilerService:
    """
    Service for psychological profiling of images.
    
    Integrates multiple behavioral analysis frameworks to provide
    comprehensive psychological assessment from photos.
    """

    def __init__(self):
        """Initialize the profiler service."""
        self._analysis_count = 0
        logger.info("🔬 ProfilerService initialized with FBI/Ekman/Navarro frameworks")

    def get_profiling_prompt(self) -> str:
        """Get the master profiling prompt."""
        return MASTER_PROFILING_PROMPT

    def get_quick_analysis_prompt(self) -> str:
        """Get a condensed prompt for quick analysis."""
        return """Analyze this image briefly, focusing on:

1. **Primary Emotion**: What emotion is displayed?
2. **Confidence Level**: Does body language show confidence?
3. **Authenticity**: Does the expression appear genuine?
4. **Key Observations**: 2-3 most notable behavioral indicators
5. **Overall Impression**: Brief summary

Keep response under 300 words. Focus on most significant observable indicators.
"""

    def encode_image_to_base64(self, image_bytes: bytes) -> str:
        """
        Encode image bytes to base64 string for API transmission.
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_bytes).decode('utf-8')

    def get_image_data_url(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """
        Create a data URL for the image.
        
        Args:
            image_bytes: Raw image bytes
            mime_type: MIME type of the image
            
        Returns:
            Data URL string for use in vision API
        """
        base64_data = self.encode_image_to_base64(image_bytes)
        return f"data:{mime_type};base64,{base64_data}"

    def build_vision_message(
        self,
        image_data_url: str,
        analysis_type: str = "full"
    ) -> List[Dict[str, Any]]:
        """
        Build the message structure for vision API call.
        
        Args:
            image_data_url: Base64 data URL of the image
            analysis_type: "full" for comprehensive, "quick" for brief
            
        Returns:
            List of message dicts for API
        """
        if analysis_type == "quick":
            prompt = self.get_quick_analysis_prompt()
        else:
            prompt = self.get_profiling_prompt()

        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    }
                ]
            }
        ]

    def format_response_for_line(self, analysis: str, truncate: bool = True) -> str:
        """
        Format the analysis response for LINE message constraints.
        
        LINE has a 5000 character limit for text messages.
        
        Args:
            analysis: Raw analysis text
            truncate: Whether to truncate for LINE limits
            
        Returns:
            Formatted response string
        """
        # Add Zeus branding
        header = "⚡ ZEUS PSYCHOLOGICAL PROFILER ⚡\n"
        header += "━" * 28 + "\n\n"
        
        footer = "\n\n" + "━" * 28
        footer += "\n⚠️ For entertainment only. Not professional advice."
        
        available_chars = 5000 - len(header) - len(footer) - 50  # Buffer
        
        if truncate and len(analysis) > available_chars:
            analysis = analysis[:available_chars] + "\n\n[Analysis truncated]"
        
        return header + analysis + footer

    def extract_primary_emotion(self, analysis: str) -> str:
        """Extract the primary emotion from analysis text."""
        emotions = ["Happiness", "Sadness", "Fear", "Anger", "Surprise", "Disgust", "Contempt", "Neutral"]
        analysis_lower = analysis.lower()
        
        for emotion in emotions:
            if emotion.lower() in analysis_lower:
                return emotion
        return "Undetermined"

    def increment_analysis_count(self) -> int:
        """Increment and return the analysis counter."""
        self._analysis_count += 1
        return self._analysis_count

    def get_analysis_count(self) -> int:
        """Get current analysis count."""
        return self._analysis_count


# Singleton instance
profiler_service = ProfilerService()
