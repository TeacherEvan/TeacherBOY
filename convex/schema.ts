import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

const timestampFields = {
  createdAt: v.number(),
  updatedAt: v.number(),
};

export default defineSchema({
  users: defineTable({
    lineUserId: v.string(),
    displayName: v.optional(v.string()),
    role: v.optional(v.string()),
    aliases: v.optional(v.array(v.string())),
    ...timestampFields,
  }).index("by_line_user_id", ["lineUserId"]),

  interactions: defineTable({
    lineUserId: v.optional(v.string()),
    sourceChatId: v.string(),
    messageType: v.string(),
    direction: v.string(),
    textPreview: v.optional(v.string()),
    handledAgent: v.optional(v.string()),
    createdAt: v.number(),
  }).index("by_chat_created", ["sourceChatId", "createdAt"]),

  notes: defineTable({
    ownerLineUserId: v.optional(v.string()),
    sourceChatId: v.string(),
    title: v.string(),
    body: v.string(),
    tags: v.array(v.string()),
    ...timestampFields,
  }),

  assignments: defineTable({
    ownerLineUserId: v.optional(v.string()),
    sourceChatId: v.string(),
    title: v.string(),
    details: v.optional(v.string()),
    dueDate: v.optional(v.string()),
    status: v.string(),
    ...timestampFields,
  }).index("by_owner_status", ["ownerLineUserId", "status"]),

  characterizations: defineTable({
    ownerLineUserId: v.optional(v.string()),
    sourceChatId: v.string(),
    summary: v.string(),
    source: v.string(),
    confidence: v.optional(v.number()),
    ...timestampFields,
  }),

  dailyReports: defineTable({
    ownerLineUserId: v.optional(v.string()),
    sourceChatId: v.string(),
    reportDate: v.string(),
    summary: v.string(),
    ...timestampFields,
  }).index("by_owner_day", ["ownerLineUserId", "reportDate"]),

  staffMemoryItems: defineTable({
    itemId: v.string(),
    title: v.string(),
    summary: v.string(),
    priority: v.string(),
    dueDate: v.optional(v.union(v.string(), v.null())),
    sourceChatId: v.string(),
    createdBy: v.string(),
    ...timestampFields,
  })
    .index("by_item_id", ["itemId"])
    .index("by_due_date", ["dueDate"]),

  calendarEvents: defineTable({
    legacyEventId: v.string(),
    lineUserId: v.string(),
    sourceChatId: v.string(),
    title: v.string(),
    description: v.optional(v.string()),
    eventDate: v.string(),
    reminderDays: v.array(v.number()),
    notificationTargetUserId: v.optional(v.string()),
    notifiedDates: v.array(v.string()),
    ...timestampFields,
  })
    .index("by_scope_legacy_event", ["lineUserId", "sourceChatId", "legacyEventId"])
    .index("by_event_date", ["eventDate"])
    .index("by_user_event_date", ["lineUserId", "eventDate"])
    .index("by_chat_event_date", ["sourceChatId", "eventDate"]),

  appSettings: defineTable({
    key: v.string(),
    value: v.any(),
    updatedBy: v.optional(v.string()),
    updatedAt: v.number(),
  }).index("by_key", ["key"]),

  debriefSessions: defineTable({
    date: v.string(), // YYYY-MM-DD
    chatId: v.string(),
    timePeriod: v.optional(v.string()), // e.g., "9h12 - 10h10, Period 3"
    subject: v.optional(v.string()), // e.g., "English - foreign languages"
    lesson: v.optional(v.string()), // e.g., "Phonics"
    teacher: v.optional(v.string()), // e.g., "Teacher Evan"
    observations: v.string(), // Rich text summary
    imageUrlRef: v.optional(v.string()), // Optional: link to stored image
    validatedByCalendar: v.boolean(), // True if Maton API confirmed details
    ...timestampFields,
  })
    .index("by_date_chat", ["chatId", "date"])
    .index("by_teacher", ["teacher"]),

  // Moderator Mode state per group
  modModeState: defineTable({
    groupId: v.string(),
    mode: v.union(v.literal("all"), v.literal("special")),
    activatedBy: v.string(),
    specialUserId: v.optional(v.string()),
    isActive: v.boolean(),
    ...timestampFields,
  })
    .index("by_group", ["groupId"])
    .index("by_admin", ["activatedBy"]),

  // Ban list per group
  banList: defineTable({
    groupId: v.string(),
    userId: v.string(),
    bannedBy: v.string(),
    reason: v.optional(v.string()),
    bannedAt: v.number(),
  })
    .index("by_group_user", ["groupId", "userId"])
    .index("by_group", ["groupId"]),

  // User warnings per group (3-strike system)
  userWarnings: defineTable({
    groupId: v.string(),
    userId: v.string(),
    count: v.number(),
    lastWarningAt: v.number(),
    lastWarningBy: v.string(),
    lastWarningReason: v.optional(v.string()),
    readByUser: v.boolean(),
    readAt: v.optional(v.number()),
  })
    .index("by_group_user", ["groupId", "userId"])
    .index("by_group", ["groupId"]),
});