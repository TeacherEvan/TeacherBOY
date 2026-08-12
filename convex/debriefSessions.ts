import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const createDebrief = mutation({
  args: {
    date: v.string(),
    chatId: v.string(),
    timePeriod: v.optional(v.string()),
    subject: v.optional(v.string()),
    lesson: v.optional(v.string()),
    teacher: v.optional(v.string()),
    observations: v.string(),
    imageUrlRef: v.optional(v.string()),
    validatedByCalendar: v.boolean(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const id = await ctx.db.insert("debriefSessions", {
      ...args,
      createdAt: now,
      updatedAt: now,
    });
    return id;
  },
});

export const getWeeklyDebriefs = query({
  args: {
    chatId: v.string(),
    startDate: v.string(), // YYYY-MM-DD
    endDate: v.string(), // YYYY-MM-DD
  },
  handler: async (ctx, args) => {
    const sessions = await ctx.db
      .query("debriefSessions")
      .withIndex("by_date_chat", (q) =>
        q.eq("chatId", args.chatId).gte("date", args.startDate).lte("date", args.endDate)
      )
      .order("asc")
      .collect();
    
    return sessions;
  },
});

export const getRecentDebriefs = query({
  args: {
    chatId: v.string(),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const limit = args.limit ?? 5;
    return await ctx.db
      .query("debriefSessions")
      .withIndex("by_date_chat", (q) => q.eq("chatId", args.chatId))
      .order("desc")
      .take(limit);
  },
});
