from src.agents.help_agent import HelpAgent


def test_command_categories_use_ms_green_examples():
    agent = HelpAgent()

    categories = agent._get_command_categories(
        is_admin=False,
        chat_type="private chat",
        zeus_available=True,
        search_available=True,
    )

    joined = " ".join(
        f"{command['command']} {' '.join(command['examples'])} {command['description']}"
        for commands in categories.values()
        for command in commands
        if command["available"]
    )

    assert "Ms. Green" in joined
    assert "Zeus" not in joined


def test_adaptive_tips_use_ai_translation_and_ms_green():
    agent = HelpAgent()

    tips = agent._get_adaptive_tips(is_admin=False, chat_type="private chat")
    joined = " ".join(tips)

    assert "Ms. Green" in joined
    assert "Google Translate" not in joined
    assert "LibreTranslate" not in joined
    assert "Zeus" not in joined