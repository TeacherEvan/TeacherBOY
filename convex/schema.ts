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
});