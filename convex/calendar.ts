import { mutationGeneric, queryGeneric } from "convex/server";
import { v } from "convex/values";

import {
  clientError,
} from "./client_errors";
import {
  diffInDays,
  hasMatchingOwnershipScope,
  requireIsoDate,
  resolveUpsertExistingEvent,
  validateReminderNotification,
} from "./calendar_helpers";

const nullableString = v.optional(v.union(v.string(), v.null()));
const CALENDAR_TIME_ZONE = "Asia/Bangkok";

function todayIso(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: CALENDAR_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());

  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );

  return `${values.year}-${values.month}-${values.day}`;
}

function normalizeReminderDays(reminderDays: number[] | undefined): number[] {
  const base = reminderDays && reminderDays.length > 0 ? reminderDays : [0];
  const values = Array.from(
    new Set(base.map((value) => Math.max(0, Math.floor(value)))),
  ).sort((left, right) => right - left);

  if (!values.includes(0)) {
    values.push(0);
  }

  return values.sort((left, right) => right - left);
}

function mapCalendarEvent(
  document: Record<string, any>,
  extras?: Record<string, unknown>,
) {
  return {
    eventId: document._id,
    legacyEventId: document.legacyEventId,
    lineUserId: document.lineUserId,
    sourceChatId: document.sourceChatId,
    title: document.title,
    description: document.description ?? "",
    eventDate: document.eventDate,
    reminderDays: document.reminderDays,
    notificationTargetUserId: document.notificationTargetUserId,
    notifiedDates: document.notifiedDates,
    createdAt: document.createdAt,
    updatedAt: document.updatedAt,
    ...extras,
  };
}

export function requireReminderQueryScope(args: {
  lineUserId?: string | null;
  sourceChatId?: string | null;
}):
  | { scope: "global" }
  | { scope: "user"; value: string }
  | { scope: "chat"; value: string } {
  if (args.lineUserId && args.sourceChatId) {
    throw clientError(
      "mixed_query_scope",
      "getDueReminders accepts either lineUserId or sourceChatId, not both",
    );
  }

  if (args.lineUserId) {
    return { scope: "user", value: args.lineUserId };
  }

  if (args.sourceChatId) {
    return { scope: "chat", value: args.sourceChatId };
  }

  return { scope: "global" };
}

export const upsertEvent = mutationGeneric({
  args: {
    eventId: nullableString,
    legacyEventId: v.string(),
    lineUserId: v.string(),
    sourceChatId: v.string(),
    title: v.string(),
    description: nullableString,
    eventDate: v.string(),
    reminderDays: v.optional(v.array(v.number())),
    notificationTargetUserId: nullableString,
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const eventDate = requireIsoDate(args.eventDate, "eventDate");
    const reminderDays = normalizeReminderDays(args.reminderDays);

    const matchingLegacyEvents = await ctx.db
      .query("calendarEvents")
      .withIndex("by_scope_legacy_event", (query) =>
        (query as any)
          .eq("lineUserId", args.lineUserId)
          .eq("sourceChatId", args.sourceChatId)
          .eq("legacyEventId", args.legacyEventId),
      )
      .collect();

    let explicitEvent = null;

    if (!matchingLegacyEvents.length && args.eventId) {
      const normalizedId = ctx.db.normalizeId("calendarEvents", args.eventId);
      if (normalizedId) {
        const candidate = await ctx.db.get(normalizedId);
        if (candidate && hasMatchingOwnershipScope(candidate, args)) {
          explicitEvent = candidate;
        }
      }
    }

    const existing = resolveUpsertExistingEvent({
      scopedLegacyMatches: matchingLegacyEvents,
      explicitEvent,
      legacyEventId: args.legacyEventId,
      sourceChatId: args.sourceChatId,
    });

    const patch = {
      legacyEventId: args.legacyEventId,
      lineUserId: args.lineUserId,
      sourceChatId: args.sourceChatId,
      title: args.title,
      description: args.description ?? undefined,
      eventDate,
      reminderDays,
      notificationTargetUserId: args.notificationTargetUserId ?? undefined,
      updatedAt: now,
    };

    if (existing) {
      await ctx.db.patch(existing._id, patch);
      const updated = await ctx.db.get(existing._id);
      return updated ? mapCalendarEvent(updated) : null;
    }

    const eventId = await ctx.db.insert("calendarEvents", {
      ...patch,
      notifiedDates: [],
      createdAt: now,
    });

    const inserted = await ctx.db.get(eventId);
    return inserted ? mapCalendarEvent(inserted) : null;
  },
});

export const listUserEvents = queryGeneric({
  args: {
    lineUserId: v.string(),
    includePast: v.optional(v.boolean()),
  },
  handler: async (ctx, args) => {
    const floorDate = todayIso();
    const records = args.includePast
      ? await ctx.db
          .query("calendarEvents")
          .withIndex("by_user_event_date", (query) =>
            query.eq("lineUserId", args.lineUserId),
          )
          .collect()
      : await ctx.db
          .query("calendarEvents")
          .withIndex("by_user_event_date", (query) =>
            (query as any).eq("lineUserId", args.lineUserId).gte("eventDate", floorDate),
          )
          .collect();

    return records.map((record) => mapCalendarEvent(record));
  },
});

export const listChatEvents = queryGeneric({
  args: {
    sourceChatId: v.string(),
    includePast: v.optional(v.boolean()),
  },
  handler: async (ctx, args) => {
    const floorDate = todayIso();
    const records = args.includePast
      ? await ctx.db
          .query("calendarEvents")
          .withIndex("by_chat_event_date", (query) =>
            query.eq("sourceChatId", args.sourceChatId),
          )
          .collect()
      : await ctx.db
          .query("calendarEvents")
          .withIndex("by_chat_event_date", (query) =>
            (query as any).eq("sourceChatId", args.sourceChatId).gte("eventDate", floorDate),
          )
          .collect();

    return records.map((record) => mapCalendarEvent(record));
  },
});

export const getDueReminders = queryGeneric({
  args: {
    today: v.string(),
    lineUserId: nullableString,
    sourceChatId: nullableString,
  },
  handler: async (ctx, args) => {
    const today = requireIsoDate(args.today, "today");
    const reminderScope = requireReminderQueryScope(args);

    let records;
    if (reminderScope.scope === "user") {
      records = await ctx.db
        .query("calendarEvents")
        .withIndex("by_user_event_date", (query) =>
          (query as any).eq("lineUserId", reminderScope.value).gte("eventDate", today),
        )
        .collect();
    } else if (reminderScope.scope === "chat") {
      records = await ctx.db
        .query("calendarEvents")
        .withIndex("by_chat_event_date", (query) =>
          (query as any).eq("sourceChatId", reminderScope.value).gte("eventDate", today),
        )
        .collect();
    } else {
      records = await ctx.db
        .query("calendarEvents")
        .withIndex("by_event_date", (query) => query.gte("eventDate", today))
        .collect();
    }

    return records
      .map((record) => ({
        record,
        daysUntil: diffInDays(record.eventDate, today),
      }))
      .filter(({ record, daysUntil }) => {
        if (daysUntil < 0) {
          return false;
        }
        if (!record.reminderDays.includes(daysUntil)) {
          return false;
        }
        return !record.notifiedDates.includes(today);
      })
      .map(({ record, daysUntil }) =>
        mapCalendarEvent(record, {
          days_until: daysUntil,
        }),
      );
  },
});

export const deleteEvent = mutationGeneric({
  args: {
    eventId: v.string(),
  },
  handler: async (ctx, args) => {
    const normalizedId = ctx.db.normalizeId("calendarEvents", args.eventId);
    if (!normalizedId) {
      return { deleted: false };
    }

    const existing = await ctx.db.get(normalizedId);
    if (!existing) {
      return { deleted: false };
    }

    await ctx.db.delete(normalizedId);
    return { deleted: true };
  },
});

export const markNotified = mutationGeneric({
  args: {
    eventId: v.string(),
    reminderDay: v.number(),
    notifiedDate: v.string(),
  },
  handler: async (ctx, args) => {
    const notifiedDate = requireIsoDate(args.notifiedDate, "notifiedDate");
    const normalizedId = ctx.db.normalizeId("calendarEvents", args.eventId);
    if (!normalizedId) {
      throw clientError("unknown_event_id", `Unknown calendar event ID: ${args.eventId}`);
    }

    const existing = await ctx.db.get(normalizedId);
    if (!existing) {
      throw clientError("missing_event", `Calendar event not found: ${args.eventId}`);
    }

    const reminderDay = Math.max(0, Math.floor(args.reminderDay));
    validateReminderNotification(existing, reminderDay, notifiedDate);

    const notifiedDates = Array.from(new Set([...existing.notifiedDates, notifiedDate])).sort();

    await ctx.db.patch(normalizedId, {
      notifiedDates,
      updatedAt: Date.now(),
    });

    const updated = await ctx.db.get(normalizedId);
    return updated ? mapCalendarEvent(updated) : null;
  },
});