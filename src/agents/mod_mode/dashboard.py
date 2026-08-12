"""LINE Flex Message dashboard for Moderator Mode."""

from typing import Any


class ModDashboardBuilder:
    """Build Flex Message dashboards for mod mode admin control."""

    PRIMARY_COLOR = "#0D8186"
    DANGER_COLOR = "#E74C3C"
    WARNING_COLOR = "#F39C12"
    SECONDARY_COLOR = "#95A5A6"

    def build_main_dashboard(
        self,
        group_name: str,
        group_id: str,
        mode_info: dict,
    ) -> dict[str, Any]:
        """Build main moderator dashboard."""
        mode = mode_info.get("mode", "unknown")
        is_active = mode_info.get("is_active", False)
        status_text = "🟢 ACTIVE" if is_active else "🔴 INACTIVE"
        mode_display = "ALL USERS" if mode == "all" else f"SPECIAL @{mode_info.get('special_user_id', '?')}"

        return {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🛡️ MODERATOR MODE",
                        "weight": "bold",
                        "color": "#FFFFFF",
                        "size": "lg",
                    },
                    {
                        "type": "text",
                        "text": f"{group_name} ({status_text})",
                        "color": "#FFFFFF",
                        "size": "sm",
                        "margin": "sm",
                    },
                ],
                "backgroundColor": self.PRIMARY_COLOR,
                "paddingAll": "md",
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "Mode:",
                                "weight": "bold",
                                "size": "sm",
                                "color": self.SECONDARY_COLOR,
                                "flex": 1,
                            },
                            {
                                "type": "text",
                                "text": mode_display,
                                "size": "sm",
                                "color": "#000000",
                                "flex": 2,
                                "align": "end",
                            },
                        ],
                    },
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "contents": [
                            self._action_button("👢 Kick User", "mod_kick", self.PRIMARY_COLOR),
                            self._action_button("⚠️ Warn User", "mod_warn", self.WARNING_COLOR),
                            self._action_button("🔨 Ban User", "mod_ban", self.DANGER_COLOR),
                            self._action_button("📋 Ban List", "mod_banlist", self.SECONDARY_COLOR),
                            self._action_button("👥 Warning List", "mod_warnlist", self.SECONDARY_COLOR),
                            self._action_button("⚙️ Settings", "mod_settings", self.PRIMARY_COLOR),
                            self._action_button("❌ Deactivate Mod Mode", "mod_deactivate", self.DANGER_COLOR),
                        ],
                    },
                ],
            },
        }

    def _action_button(self, label: str, action: str, color: str) -> dict:
        return {
            "type": "button",
            "action": {
                "type": "postback",
                "label": label,
                "data": f"action={action}",
                "displayText": label,
            },
            "style": "primary",
            "color": color,
            "margin": "sm",
        }

    def build_ban_list_dashboard(self, group_id: str, bans: list[dict]) -> dict[str, Any]:
        """Build ban list view."""
        contents = [
            {
                "type": "text",
                "text": "🔨 BANNED USERS",
                "weight": "bold",
                "size": "lg",
                "color": self.PRIMARY_COLOR,
            },
            {"type": "separator", "margin": "md"},
        ]
        if not bans:
            contents.append({"type": "text", "text": "No banned users.", "color": self.SECONDARY_COLOR})
        else:
            for ban in bans[:20]:  # Limit for Flex size
                contents.append(
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [  # type: ignore[dict-item]
                            {"type": "text", "text": ban.get("userId", "?"), "size": "sm", "flex": 2},
                            {
                                "type": "text",
                                "text": ban.get("reason", "No reason"),
                                "size": "sm",
                                "color": self.SECONDARY_COLOR,
                                "flex": 3,
                                "wrap": True,
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "Unban",
                                    "data": f"action=mod_unban&user={ban.get('userId')}",
                                },
                                "style": "secondary",
                                "color": self.PRIMARY_COLOR,
                                "flex": 1,
                            },
                        ],
                        "margin": "sm",
                    }
                )
        return {"type": "bubble", "size": "giga", "body": {"type": "box", "layout": "vertical", "contents": contents}}

    def build_kick_confirm(self, group_id: str, user_id: str, display_name: str) -> dict[str, Any]:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "👢 CONFIRM KICK", "weight": "bold", "size": "lg", "color": self.DANGER_COLOR},
                    {"type": "text", "text": f"Kick {display_name} ({user_id})?", "margin": "md", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "button",
                                "action": {"type": "postback", "label": "Cancel", "data": "action=mod_cancel"},
                                "style": "secondary",
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "Confirm Kick",
                                    "data": f"action=mod_kick_confirm&user={user_id}",
                                },
                                "style": "primary",
                                "color": self.DANGER_COLOR,
                            },
                        ],
                    },
                ],
            },
        }

    def build_warn_confirm(self, group_id: str, user_id: str, display_name: str) -> dict[str, Any]:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "⚠️ CONFIRM WARN", "weight": "bold", "size": "lg", "color": self.WARNING_COLOR},
                    {"type": "text", "text": f"Warn {display_name} ({user_id})?", "margin": "md", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "button",
                                "action": {"type": "postback", "label": "Cancel", "data": "action=mod_cancel"},
                                "style": "secondary",
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "Confirm Warn",
                                    "data": f"action=mod_warn_confirm&user={user_id}",
                                },
                                "style": "primary",
                                "color": self.WARNING_COLOR,
                            },
                        ],
                    },
                ],
            },
        }

    def build_settings_dashboard(self, group_id: str, mode_info: dict) -> dict[str, Any]:
        mode = mode_info.get("mode", "all")
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "⚙️ MOD MODE SETTINGS",
                        "weight": "bold",
                        "size": "lg",
                        "color": self.PRIMARY_COLOR,
                    },
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": f"Current Mode: {mode.upper()}", "margin": "md"},
                    {
                        "type": "button",
                        "action": {"type": "postback", "label": "Switch to ALL", "data": "action=mod_set_all"},
                        "style": "primary" if mode != "all" else "secondary",
                        "color": self.PRIMARY_COLOR,
                        "margin": "md",
                    },
                    {
                        "type": "button",
                        "action": {"type": "postback", "label": "Switch to SPECIAL", "data": "action=mod_set_special"},
                        "style": "primary" if mode != "special" else "secondary",
                        "color": self.PRIMARY_COLOR,
                        "margin": "sm",
                    },
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "button",
                        "action": {"type": "postback", "label": "← Back to Dashboard", "data": "action=mod_dashboard"},
                        "style": "link",
                    },
                ],
            },
        }

    def build_warn_list_dashboard(self, group_id: str, warnings: list[dict]) -> dict[str, Any]:
        """Build warning list view."""
        contents = [
            {
                "type": "text",
                "text": "⚠️ WARNING LIST",
                "weight": "bold",
                "size": "lg",
                "color": self.PRIMARY_COLOR,
            },
            {"type": "separator", "margin": "md"},
        ]
        if not warnings:
            contents.append({"type": "text", "text": "No warnings.", "color": self.SECONDARY_COLOR})
        else:
            for warn in warnings[:20]:  # Limit for Flex size
                contents.append(
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [  # type: ignore[dict-item]
                            {"type": "text", "text": warn.get("userId", "?"), "size": "sm", "flex": 2},
                            {
                                "type": "text",
                                "text": f"Count: {warn.get('count', 0)}/3 | {warn.get('lastWarningReason', 'No reason')}",
                                "size": "sm",
                                "color": self.SECONDARY_COLOR,
                                "flex": 3,
                                "wrap": True,
                            },
                        ],
                        "margin": "sm",
                    }
                )
        return {"type": "bubble", "size": "giga", "body": {"type": "box", "layout": "vertical", "contents": contents}}
