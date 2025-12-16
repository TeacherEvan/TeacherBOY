"""Text preprocessing utilities for translation."""

import re
from typing import List, Tuple


def extract_parenthesized_text(text: str) -> Tuple[str, List[str]]:
    """
    Extract text within parentheses and replace with placeholders.
    
    This allows translation services to skip translating content in parentheses,
    which is useful for preserving proper nouns, technical terms, or notes.
    
    The regex pattern `\\([^()]*\\)` matches simple (non-nested) parentheses.
    It will only match parentheses that don't contain other parentheses inside them.
    For example, in "(outer (inner))", only "(inner)" will be matched.
    
    Args:
        text: Original text that may contain parenthesized content
        
    Returns:
        Tuple of (processed_text, extracted_items)
        - processed_text: Text with parentheses replaced by placeholders
        - extracted_items: List of extracted parenthesized strings (including parentheses)
        
    Example:
        >>> extract_parenthesized_text("(Pim) had the day off.")
        ("__PAREN_0__ had the day off.", ["(Pim)"])
    """
    # Find all text within parentheses (including the parentheses themselves)
    # Pattern explanation: \\( matches opening paren, [^()]* matches any non-paren chars, \\) matches closing paren
    pattern = r'\([^()]*\)'
    
    extracted_items = []
    
    def replace_with_placeholder(match):
        """Replace function that assigns sequential placeholders."""
        item = match.group(0)
        extracted_items.append(item)
        return f"__PAREN_{len(extracted_items) - 1}__"
    
    # Use re.sub with a function to replace and track items
    processed_text = re.sub(pattern, replace_with_placeholder, text)
    
    return processed_text, extracted_items


def is_only_parenthesized_content(text: str, extracted_items: List[str]) -> bool:
    """
    Check if the text contains only parenthesized content (no translatable text).
    
    Args:
        text: Processed text with placeholders
        extracted_items: List of extracted parenthesized strings
        
    Returns:
        True if text is empty or contains only placeholders
        
    Example:
        >>> is_only_parenthesized_content("__PAREN_0__", ["(Name)"])
        True
        >>> is_only_parenthesized_content("__PAREN_0__ text", ["(Name)"])
        False
    """
    if not text.strip():
        return True
    
    # Check if text is only placeholders by removing all placeholders and checking what's left
    remaining = text
    for i in range(len(extracted_items)):
        placeholder = f"__PAREN_{i}__"
        remaining = remaining.replace(placeholder, "")
    
    # If only whitespace remains, it's only parenthesized content
    return not remaining.strip()


def restore_parenthesized_text(text: str, extracted_items: List[str]) -> str:
    """
    Restore parenthesized text back into the translated string.
    
    Args:
        text: Translated text containing placeholders
        extracted_items: List of original parenthesized strings
        
    Returns:
        Text with placeholders replaced by original parenthesized content
        
    Example:
        >>> restore_parenthesized_text("__PAREN_0__ มีวันหยุด", ["(Pim)"])
        "(Pim) มีวันหยุด"
    """
    restored_text = text
    for i, item in enumerate(extracted_items):
        placeholder = f"__PAREN_{i}__"
        restored_text = restored_text.replace(placeholder, item)
    
    return restored_text
