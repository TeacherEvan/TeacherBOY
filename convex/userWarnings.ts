// convex/userWarnings.ts
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const upsert = mutation({
  args: {
    groupId: v.string(),
    userId: v.string(),
    count: v.number(),
    lastWarningAt: v.number(),
    lastWarningBy: v.string(),
    lastWarningReason: v.optional(v.string()),
    readByUser: v.boolean(),
    readAt: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("userWarnings")
      .withIndex("by_group_user", (q) => q.eq("groupId", args.groupId).eq("userId", args.userId))
      .unique();
    if (existing) await ctx.db.patch(existing._id, { ...args, updatedAt: Date.now() });
    else await ctx.db.insert("userWarnings", { ...args, createdAt: Date.now(), updatedAt: Date.now() });
    return args;
  },
});

export const getByGroupUser = query({
  args: { groupId: v.string(), userId: v.string() },
  handler: async (ctx, args) =>
    ctx.db
      .query("userWarnings")
      .withIndex("by_group_user", (q) => q.eq("groupId", args.groupId).eq("userId", args.userId))
      .unique(),
});

export const getByGroup = query({
  args: { groupId: v.string() },
  handler: async (ctx, args) =>
    ctx.db.query("userWarnings").withIndex("by_group", (q) => q.eq("groupId", args.groupId)).collect(),
});