import { mutationGeneric, queryGeneric } from "convex/server";
import { v } from "convex/values";

const nullableString = v.optional(v.union(v.string(), v.null()));
const nullableNumber = v.optional(v.union(v.number(), v.null()));

function normalizeStrings(values: string[] | undefined | null): string[] {
  if (!values || values.length === 0) {
    return [];
  }
  return values.map((value) => value.trim()).filter((value) => value.length > 0);
}

export const appendInteraction = mutationGeneric({
  args: {
    lineUserId: nullableString,
    sourceChatId: v.string(),
    messageType: v.string(),
    direction: v.string(),
    textPreview: nullableString,
    handledAgent: nullableString,
  },
  handler: async (ctx, args) => {
    const interactionId = await ctx.db.insert("interactions", {
      lineUserId: args.lineUserId ?? undefined,
      sourceChatId: args.sourceChatId,
      messageType: args.messageType,
      direction: args.direction,
      textPreview: args.textPreview ?? undefined,
      handledAgent: args.handledAgent ?? undefined,
      createdAt: Date.now(),
    });

    return await ctx.db.get(interactionId);
  },
});

export const createNote = mutationGeneric({
  args: {
    ownerLineUserId: nullableString,
    sourceChatId: v.string(),
    title: v.string(),
    body: v.string(),
    tags: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const noteId = await ctx.db.insert("notes", {
      ownerLineUserId: args.ownerLineUserId ?? undefined,
      sourceChatId: args.sourceChatId,
      title: args.title,
      body: args.body,
      tags: normalizeStrings(args.tags),
      createdAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(noteId);
  },
});

export const createAssignment = mutationGeneric({
  args: {
    ownerLineUserId: nullableString,
    sourceChatId: v.string(),
    title: v.string(),
    details: nullableString,
    dueDate: nullableString,
    status: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const assignmentId = await ctx.db.insert("assignments", {
      ownerLineUserId: args.ownerLineUserId ?? undefined,
      sourceChatId: args.sourceChatId,
      title: args.title,
      details: args.details ?? undefined,
      dueDate: args.dueDate ?? undefined,
      status: args.status ?? "open",
      createdAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(assignmentId);
  },
});

export const createCharacterization = mutationGeneric({
  args: {
    ownerLineUserId: nullableString,
    sourceChatId: v.string(),
    summary: v.string(),
    source: v.string(),
    confidence: nullableNumber,
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const characterizationId = await ctx.db.insert("characterizations", {
      ownerLineUserId: args.ownerLineUserId ?? undefined,
      sourceChatId: args.sourceChatId,
      summary: args.summary,
      source: args.source,
      confidence: args.confidence ?? undefined,
      createdAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(characterizationId);
  },
});

export const createDailyReport = mutationGeneric({
  args: {
    ownerLineUserId: nullableString,
    sourceChatId: v.string(),
    reportDate: v.string(),
    summary: v.string(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const reportId = await ctx.db.insert("dailyReports", {
      ownerLineUserId: args.ownerLineUserId ?? undefined,
      sourceChatId: args.sourceChatId,
      reportDate: args.reportDate,
      summary: args.summary,
      createdAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(reportId);
  },
});

export const createStaffMemoryItem = mutationGeneric({
  args: {
    itemId: v.string(),
    title: v.string(),
    summary: v.string(),
    priority: v.string(),
    dueDate: nullableString,
    sourceChatId: v.string(),
    createdBy: v.string(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const recordId = await ctx.db.insert("staffMemoryItems", {
      itemId: args.itemId,
      title: args.title,
      summary: args.summary,
      priority: args.priority,
      dueDate: args.dueDate ?? null,
      sourceChatId: args.sourceChatId,
      createdBy: args.createdBy,
      createdAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(recordId);
  },
});

export const upsertStaffMemoryItem = mutationGeneric({
  args: {
    itemId: v.string(),
    title: v.string(),
    summary: v.string(),
    priority: v.string(),
    dueDate: nullableString,
    sourceChatId: v.string(),
    createdBy: v.string(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const existingRecord = await (ctx.db.query("staffMemoryItems") as any)
      .withIndex("by_item_id", (query: any) => query.eq("itemId", args.itemId))
      .unique();

    if (existingRecord) {
      await ctx.db.patch(existingRecord._id, {
        title: args.title,
        summary: args.summary,
        priority: args.priority,
        dueDate: args.dueDate ?? null,
        sourceChatId: args.sourceChatId,
        createdBy: args.createdBy,
        updatedAt: now,
      });

      return await ctx.db.get(existingRecord._id);
    }

    const recordId = await ctx.db.insert("staffMemoryItems", {
      itemId: args.itemId,
      title: args.title,
      summary: args.summary,
      priority: args.priority,
      dueDate: args.dueDate ?? null,
      sourceChatId: args.sourceChatId,
      createdBy: args.createdBy,
      createdAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(recordId);
  },
});

export const listStaffMemoryItemsForWeek = queryGeneric({
  args: {
    weekStart: v.string(),
    weekEnd: v.string(),
  },
  handler: async (ctx, args) => {
    const staffMemoryQuery = ctx.db.query("staffMemoryItems") as any;
    const items = await staffMemoryQuery
      .withIndex("by_due_date", (query: any) =>
        query.gte("dueDate", args.weekStart).lte("dueDate", args.weekEnd),
      )
      .collect();

    return items
      .sort((left: any, right: any) => {
        if (left.priority !== right.priority) {
          return left.priority.localeCompare(right.priority);
        }

        const leftDueDate = left.dueDate ?? "9999-12-31";
        const rightDueDate = right.dueDate ?? "9999-12-31";
        if (leftDueDate !== rightDueDate) {
          return leftDueDate.localeCompare(rightDueDate);
        }

        return left.title.localeCompare(right.title);
      });
  },
});