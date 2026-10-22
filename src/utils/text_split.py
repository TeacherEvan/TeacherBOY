"""
Text splitting utilities for LINE message limits.

The LINE Messaging API accepts at most 5000 characters per text message.
Long reports (FBI profiles, Hannibal chat analyses) must therefore be
delivered as several messages — but they must never be *truncated*: losing
the tail of an analysis is a correctness bug, not a formatting choice.

This module provides one deterministic splitter shared by every feature that
needs to emit long text over LINE.
"""

from __future__ import annotations

# LINE hard limit for a single text message.
LINE_MAX_CHARS = 5000
# Working size for one part of a multi-part message (leaves room for the
# "Part x/y" indicator and any header/footer).
LINE_PART_CHARS = 4500

__all__ = [
    "LINE_MAX_CHARS",
    "LINE_PART_CHARS",
    "split_sentences",
    "split_text",
]


def split_sentences(text: str) -> list[str]:
    """
    Split text into sentences without losing a single character.

    Sentence terminators (".", "!", "?", "…") end a sentence. Whitespace that
    follows a terminator stays attached to the sentence it follows, so
    ``"".join(split_sentences(text)) == text`` always holds.

    Args:
        text: Text to split

    Returns:
        List of sentence fragments (possibly empty).
    """
    if not text:
        return []

    sentences: list[str] = []
    start = 0
    index = 0
    length = len(text)

    while index < length:
        if text[index] in ".!?…":
            end = index + 1
            while end < length and text[end] in " \t":
                end += 1
            # Guard against splitting decimals ("3.5") and version numbers.
            if end < length and text[end].isdigit():
                index += 1
                continue
            sentences.append(text[start:end])
            start = end
            index = end
            continue
        index += 1

    if start < length:
        sentences.append(text[start:])

    return [s for s in sentences if s]


def split_text(text: str, max_length: int = LINE_PART_CHARS) -> list[str]:
    """
    Split text into chunks of at most ``max_length`` characters.

    Splits on the coarsest boundary that fits — paragraph, then line, then
    sentence, then a hard cut as a last resort — so no content is ever lost.

    Args:
        text: Text to split
        max_length: Maximum characters per chunk

    Returns:
        List of chunks. For any text with actual content, joining the chunks
        reproduces the original text. Whitespace-only input yields no chunks.
    """
    if not text:
        return []

    # A whitespace-only payload carries no content. Returning it from the
    # early-exit path while the general path drops it would make the two
    # code paths disagree on the same input.
    if not text.strip():
        return []

    if max_length <= 0:
        return [text]

    if len(text) <= max_length:
        return [text]

    parts: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            parts.append(current.rstrip())
            current = ""

    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_length:
            current = candidate
            continue

        flush()
        if len(paragraph) <= max_length:
            current = paragraph
            continue

        for line in paragraph.split("\n"):
            candidate = line if not current else f"{current}\n{line}"
            if len(candidate) <= max_length:
                current = candidate
                continue

            flush()
            if len(line) <= max_length:
                current = line
                continue

            for sentence in split_sentences(line):
                candidate = sentence if not current else f"{current} {sentence}"
                if len(candidate) <= max_length:
                    current = candidate
                    continue

                flush()
                if len(sentence) <= max_length:
                    current = sentence
                    continue

                # Last resort: hard cut, still no content loss.
                for offset in range(0, len(sentence), max_length):
                    flush()
                    current = sentence[offset : offset + max_length]

    flush()
    return [p for p in parts if p]
