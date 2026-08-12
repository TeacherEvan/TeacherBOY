// convex/banList.ts
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const upsert = mutation({
  args: {
    groupId: v.string(),
    userId: v.string(),
    bannedBy: v.string(),
    reason: v.optional(v.string()),
    bannedAt: v.number(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("banList")
      .withIndex("by_group_user", (q) => q.eq("groupId", args.groupId).eq("userId", args.userId))
      .unique();
    if (existing) await ctx.db.patch(existing._id, args);
    else await ctx.db.insert("banList", args);
    return args;
  },
});

export const getByGroupUser = query({
  args: { groupId: v.string(), userId: v.string() },
  handler: async (ctx, args) =>
    ctx.db
      .query("banList")
      .withIndex("by_group_user", (q) => q.eq("groupId", args.groupId).eq("userId", args.userId))
      .unique(),
});

export const getByGroup = query({
  args: { groupId: v.string() },
  handler: async (ctx, args) =>
    ctx.db.query("banList").withIndex("by_group", (q) => q.eq("groupId", args.groupId)).collect(),
});

export const remove = mutation({
  args: { groupId: v.string(), userId: v.string() },
  handler: async (ctx, args) => {
    const doc = await ctx.db
      .query("banList")
      .withIndex("by_group_user", (q) => q.eq("groupId", args.groupId).eq("userId", args.userId))
      .unique();
    if (doc) await ctx.db.delete(doc._id);
    return { success: true };
  },
});