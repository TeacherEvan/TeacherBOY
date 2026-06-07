"""Flex message builders for the DM-first admin dashboard."""

from __future__ import annotations

from linebot.v3.messaging import FlexContainer, FlexMessage


def _message_button(label: str, text: str, *, style: str = "secondary") -> dict:
    return {
        "type": "button",
        "style": style,
        "height": "sm",
        "action": {
            "type": "message",
            "label": label,
            "text": text,
        },
    }


def _button_row(*buttons: dict) -> dict:
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "margin": "md",
        "contents": list(buttons),
    }


def build_admin_dashboard(
    *,
    target_chat_id: str,
    persistence_backend: str,
    is_sleeping: bool,
    pending_confirmations: int,
) -> FlexMessage:
    toggle_text = f"/admin wake {target_chat_id}" if is_sleeping else f"/admin sleep {target_chat_id} 24"

    risky_rows = [
        _button_row(
            _message_button(
                "Preview reset",
                f"/admin reset {target_chat_id}",
                style="primary",
            ),
            _message_button(
                "Preview purge",
                f"/admin purge {target_chat_id}",
                style="primary",
            ),
        )
    ]

    if target_chat_id.startswith(("group_", "room_")):
        risky_rows.append(
            _button_row(
                _message_button(
                    "Preview leave",
                    f"/admin leave {target_chat_id}",
                    style="primary",
                )
            )
        )

    flex_dict = {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1F2937",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "Admin Dashboard",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#FFFFFF",
                },
                {
                    "type": "text",
                    "text": "DM-first controls for the selected chat",
                    "size": "sm",
                    "color": "#D1D5DB",
                    "margin": "sm",
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F3F4F6",
                    "cornerRadius": "12px",
                    "paddingAll": "16px",
                    "contents": [
                        {
                            "type": "text",
                            "text": "Context",
                            "weight": "bold",
                            "size": "md",
                            "color": "#111827",
                        },
                        {
                            "type": "text",
                            "text": f"Target chat: {target_chat_id}",
                            "size": "sm",
                            "color": "#374151",
                            "margin": "md",
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": f"Persistence backend: {persistence_backend}",
                            "size": "sm",
                            "color": "#374151",
                            "margin": "sm",
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": f"Pending confirmations: {pending_confirmations}",
                            "size": "sm",
                            "color": "#374151",
                            "margin": "sm",
                        },
                    ],
                },
                {
                    "type": "text",
                    "text": "Safe actions",
                    "weight": "bold",
                    "size": "md",
                    "color": "#111827",
                },
                _button_row(
                    _message_button("View status", f"/admin status {target_chat_id}"),
                    _message_button("Toggle sleep/wake", toggle_text),
                ),
                _button_row(
                    _message_button("Open confirmations", "/admin confirmations"),
                    _message_button("View sessions", "/admin sessions"),
                ),
                _button_row(
                    _message_button("View groups", "/admin groups"),
                ),
                {
                    "type": "separator",
                    "margin": "lg",
                },
                {
                    "type": "text",
                    "text": "Risky actions",
                    "weight": "bold",
                    "size": "md",
                    "color": "#111827",
                },
                {
                    "type": "text",
                    "text": "These buttons only open the existing private preview flow.",
                    "size": "xs",
                    "color": "#6B7280",
                    "wrap": True,
                },
                *risky_rows,
            ],
            "paddingAll": "20px",
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "12px",
            "backgroundColor": "#F9FAFB",
            "contents": [
                {
                    "type": "text",
                    "text": "Backend mode is shown for visibility only. No live switching is available here.",
                    "size": "xs",
                    "color": "#6B7280",
                    "wrap": True,
                }
            ],
        },
    }

    return FlexMessage(
        altText=f"Admin dashboard for {target_chat_id}",
        contents=FlexContainer.from_dict(flex_dict),
        quickReply=None,
    )


def build_dashboard_handoff_message() -> str:
    return "I sent your admin panel privately."


def build_dashboard_delivery_failure_message() -> str:
    return "⚠️ The private dashboard could not be delivered. Start a private chat with the bot and try again."
