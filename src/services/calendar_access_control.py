"""
Calendar Access Control Service - RBAC and permission validation.

This service enforces strict access control for calendar operations:
- Role-based permissions (owner, member, admin)
- Chat membership validation via LINE API
- Cross-chat isolation enforcement
- Audit-ready permission checks

Security Model:
- Events belong to a chat_id (group/room/DM)
- Only chat members can view/modify events in that chat
- Admins have elevated permissions across all chats
- Event creators can always modify their own events
"""

import logging
from enum import Enum
from typing import Optional, Set
from linebot.v3.messaging import MessagingApi
from linebot.v3.exceptions import InvalidSignatureError

from src.config import settings
from src.services.privilege_service import privilege_service

logger = logging.getLogger(__name__)


class CalendarRole(Enum):
    """Calendar access roles."""
    OWNER = "owner"          # Event creator
    MEMBER = "member"        # Chat member
    ADMIN = "admin"          # Bot admin
    NON_MEMBER = "non_member"  # Not part of chat


class CalendarPermission(Enum):
    """Calendar operation permissions."""
    VIEW_EVENTS = "view_events"
    CREATE_EVENT = "create_event"
    MODIFY_EVENT = "modify_event"
    DELETE_EVENT = "delete_event"


class CalendarAccessControl:
    """
    Access control service for calendar operations.
    
    Enforces:
    - Chat-based isolation (events accessible only within their chat)
    - Membership verification via LINE API
    - Role-based permissions
    - Admin override capabilities
    """

    def __init__(self):
        self._admin_user_ids: Set[str] = set(settings.get_admin_user_ids())
        logger.info(f"✅ CalendarAccessControl initialized ({len(self._admin_user_ids)} admins)")

    async def get_user_role(
        self,
        user_id: str,
        chat_id: str,
        event_owner_id: Optional[str] = None,
        line_bot_api: Optional[MessagingApi] = None
    ) -> CalendarRole:
        """
        Determine user's role in the calendar context.
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID (group_xxx, room_xxx, or user_xxx)
            event_owner_id: ID of event creator (optional, for ownership check)
            line_bot_api: LINE API client for membership verification
            
        Returns:
            CalendarRole enum value
        """
        # Check if user is admin
        if self._is_admin(user_id):
            return CalendarRole.ADMIN

        # Check if user is event owner
        if event_owner_id and user_id == event_owner_id:
            return CalendarRole.OWNER

        # For private DMs (user_xxx), only that user has access
        if chat_id.startswith("user_"):
            chat_user_id = chat_id.replace("user_", "")
            return CalendarRole.MEMBER if user_id == chat_user_id else CalendarRole.NON_MEMBER

        # For groups/rooms, verify membership via LINE API
        if chat_id.startswith("group_") or chat_id.startswith("room_"):
            is_member = await self._verify_chat_membership(
                user_id, chat_id, line_bot_api
            )
            return CalendarRole.MEMBER if is_member else CalendarRole.NON_MEMBER

        # Unknown chat type
        logger.warning(f"⚠️ Unknown chat_id format: {chat_id}")
        return CalendarRole.NON_MEMBER

    async def can_view_events(
        self,
        user_id: str,
        chat_id: str,
        line_bot_api: Optional[MessagingApi] = None
    ) -> bool:
        """
        Check if user can view events in a chat.
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID
            line_bot_api: LINE API client
            
        Returns:
            True if user can view events
        """
        role = await self.get_user_role(user_id, chat_id, line_bot_api=line_bot_api)
        
        # Admins and members can view
        if role in [CalendarRole.ADMIN, CalendarRole.MEMBER]:
            logger.debug(f"✅ Access granted: {user_id} can view events in {chat_id} (role: {role.value})")
            return True
        
        logger.warning(f"❌ Access denied: {user_id} cannot view events in {chat_id} (role: {role.value})")
        return False

    async def can_create_event(
        self,
        user_id: str,
        chat_id: str,
        line_bot_api: Optional[MessagingApi] = None
    ) -> bool:
        """
        Check if user can create events in a chat.
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID
            line_bot_api: LINE API client
            
        Returns:
            True if user can create events
        """
        role = await self.get_user_role(user_id, chat_id, line_bot_api=line_bot_api)
        
        # Admins and members can create
        if role in [CalendarRole.ADMIN, CalendarRole.MEMBER]:
            logger.debug(f"✅ Access granted: {user_id} can create events in {chat_id} (role: {role.value})")
            return True
        
        logger.warning(f"❌ Access denied: {user_id} cannot create events in {chat_id} (role: {role.value})")
        return False

    async def can_modify_event(
        self,
        user_id: str,
        chat_id: str,
        event_owner_id: str,
        line_bot_api: Optional[MessagingApi] = None
    ) -> bool:
        """
        Check if user can modify an event.
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID
            event_owner_id: ID of event creator
            line_bot_api: LINE API client
            
        Returns:
            True if user can modify the event
        """
        role = await self.get_user_role(
            user_id, chat_id, event_owner_id=event_owner_id, line_bot_api=line_bot_api
        )
        
        # Admins and owners can modify
        if role in [CalendarRole.ADMIN, CalendarRole.OWNER]:
            logger.debug(f"✅ Access granted: {user_id} can modify event in {chat_id} (role: {role.value})")
            return True
        
        logger.warning(f"❌ Access denied: {user_id} cannot modify event in {chat_id} (role: {role.value})")
        return False

    async def can_delete_event(
        self,
        user_id: str,
        chat_id: str,
        event_owner_id: str,
        line_bot_api: Optional[MessagingApi] = None
    ) -> bool:
        """
        Check if user can delete an event.
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID
            event_owner_id: ID of event creator
            line_bot_api: LINE API client
            
        Returns:
            True if user can delete the event
        """
        role = await self.get_user_role(
            user_id, chat_id, event_owner_id=event_owner_id, line_bot_api=line_bot_api
        )
        
        # Admins and owners can delete
        if role in [CalendarRole.ADMIN, CalendarRole.OWNER]:
            logger.debug(f"✅ Access granted: {user_id} can delete event in {chat_id} (role: {role.value})")
            return True
        
        logger.warning(f"❌ Access denied: {user_id} cannot delete event in {chat_id} (role: {role.value})")
        return False

    async def _verify_chat_membership(
        self,
        user_id: str,
        chat_id: str,
        line_bot_api: Optional[MessagingApi]
    ) -> bool:
        """
        Verify if user is a member of a group/room chat.
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID
            line_bot_api: LINE API client
            
        Returns:
            True if user is a member
        """
        if not line_bot_api:
            logger.warning("⚠️ LINE API not available, cannot verify membership")
            return False

        try:
            import asyncio
            
            if chat_id.startswith("group_"):
                group_id = chat_id.replace("group_", "")
                # Attempt to get group member profile
                profile = await asyncio.to_thread(
                    line_bot_api.get_group_member_profile,
                    group_id,
                    user_id
                )
                return profile is not None
                
            elif chat_id.startswith("room_"):
                room_id = chat_id.replace("room_", "")
                # Attempt to get room member profile
                profile = await asyncio.to_thread(
                    line_bot_api.get_room_member_profile,
                    room_id,
                    user_id
                )
                return profile is not None
                
        except Exception as e:
            logger.error(f"❌ Failed to verify membership for {user_id} in {chat_id}: {e}")
            # Fail-safe: deny access on verification error
            return False

        return False

    def _is_admin(self, user_id: Optional[str]) -> bool:
        """
        Check if user is a bot admin.
        
        Args:
            user_id: LINE user ID
            
        Returns:
            True if user is admin
        """
        if not user_id:
            return False
        
        # Check runtime-claimed admins
        if privilege_service.is_claimed_admin(user_id):
            return True
        
        # Check env-configured admins
        return user_id in self._admin_user_ids


# Singleton instance
calendar_access_control = CalendarAccessControl()
