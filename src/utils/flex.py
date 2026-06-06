"""Flex Message templates for Ms. Green."""


def create_translation_flex(original_text: str, translated_text: str, source_lang: str, target_lang: str) -> dict:
    """
    Create a Flex Message bubble for translation result.

    Args:
        original_text: The original message text
        translated_text: The translated text
        source_lang: Source language code ('th' or 'en')
        target_lang: Target language code ('th' or 'en')

    Returns:
        Flex Message Bubble dictionary
    """
    # Determine colors and labels
    primary_color = "#0D8186"  # Teal
    secondary_color = "#aaaaaa"

    source_label = "Thai" if source_lang == "th" else "English"
    target_label = "English" if source_lang == "th" else "Thai"

    source_flag = "🇹🇭" if source_lang == "th" else "🇬🇧"
    target_flag = "🇬🇧" if source_lang == "th" else "🇹🇭"

    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "Ms. Green",
                            "weight": "bold",
                            "color": primary_color,
                            "size": "sm",
                        },
                        {
                            "type": "text",
                            "text": "TRANSLATOR",
                            "weight": "bold",
                            "color": secondary_color,
                            "size": "xxs",
                            "align": "end",
                            "gravity": "center",
                        },
                    ],
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                # Source Language Section
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": source_flag, "size": "lg", "flex": 0},
                        {
                            "type": "text",
                            "text": source_label,
                            "weight": "bold",
                            "size": "sm",
                            "margin": "sm",
                            "gravity": "center",
                        },
                    ],
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": original_text,
                    "wrap": True,
                    "color": "#555555",
                    "size": "sm",
                    "margin": "sm",
                },
                # Divider
                {"type": "separator", "margin": "xl", "color": "#eeeeee"},
                # Target Language Section
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": target_flag, "size": "lg", "flex": 0},
                        {
                            "type": "text",
                            "text": target_label,
                            "weight": "bold",
                            "size": "sm",
                            "margin": "sm",
                            "gravity": "center",
                            "color": primary_color,
                        },
                    ],
                    "margin": "xl",
                },
                {
                    "type": "text",
                    "text": translated_text,
                    "wrap": True,
                    "weight": "regular",
                    "size": "md",
                    "margin": "sm",
                    "color": "#000000",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Powered by AI translation",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center",
                }
            ],
        },
    }
