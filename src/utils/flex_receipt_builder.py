"""Flex receipt builder — builds LINE Flex Message bubbles for receipt scan results."""

from linebot.v3.messaging import (
    FlexBox,
    FlexBubble,
    FlexButton,
    FlexSeparator,
    FlexText,
    URIAction,
)

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "THB": "฿", "JPY": "¥", "ZAR": "R"}


def build_receipt_bubble(result: dict, app_url: str | None = None) -> FlexBubble:
    """Build a Flex bubble showing receipt scan results with a deep link."""
    fields = result.get("fields", {})
    merchant = fields.get("merchant", {}).get("value", "Unknown")
    total = fields.get("total", {}).get("value", 0)
    category = fields.get("category", {}).get("value", "other")
    currency = fields.get("currency", {}).get("value", "USD")
    confidence = result.get("confidence", {})
    total_conf = confidence.get("total", 0)

    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    source = result.get("source", "LINE")

    return FlexBubble(
        header=FlexBox(
            layout="vertical",
            contents=[
                FlexText(text="🧾 Receipt Scanned", weight="bold", size="lg", color="#1a1a2e"),
                FlexText(text=f"via {source}", size="xs", color="#888"),
            ],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="md",
            contents=[
                FlexBox(
                    layout="horizontal",
                    contents=[
                        FlexText(text="Merchant", size="sm", color="#666", flex=1),
                        FlexText(text=str(merchant), size="sm", weight="bold", flex=2, wrap=True),
                    ],
                ),
                FlexBox(
                    layout="horizontal",
                    contents=[
                        FlexText(text="Total", size="sm", color="#666", flex=1),
                        FlexText(text=f"{symbol}{total:.2f}", size="lg", weight="bold", color="#fbbf24", flex=2),
                    ],
                ),
                FlexBox(
                    layout="horizontal",
                    contents=[
                        FlexText(text="Category", size="sm", color="#666", flex=1),
                        FlexText(text=str(category).capitalize(), size="sm", flex=2),
                    ],
                ),
                FlexSeparator(),
                FlexText(
                    text=f"Confidence: {int(total_conf * 100)}%",
                    size="xs",
                    color="#34d399" if total_conf > 0.7 else "#fbbf24" if total_conf > 0.5 else "#f87171",
                ),
            ],
        ),
        footer=FlexBox(
            layout="vertical",
            spacing="sm",
            contents=[
                FlexButton(
                    action=URIAction(
                        label="Open in Budget Boss",
                        uri=f"{app_url or 'https://budgetboss.app'}/receipts/{result.get('draftId', '')}",
                    ),
                    style="primary",
                    color="#fbbf24",
                ),
            ],
        ),
    )
