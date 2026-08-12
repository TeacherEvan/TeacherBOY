// convex/modModeState.ts
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const upsert = mutation({
  args: {
    groupId: v.string(),
    mode: v.union(v.literal("all"), v.literal("special")),
    activatedBy: v.string(),
    specialUserId: v.optional(v.string()),
    isActive: v.boolean(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("modModeState")
      .withIndex("by_group", (q) => q.eq("groupId", args.groupId))
      .unique();
    if (existing) {
      await ctx.db.patch(existing._id, { ...args, updatedAt: Date.now() });
      return { ...existing, ...args, updatedAt: Date.now() };
    }
    const id = await ctx.db.insert("modModeState", {
      ...args,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    });
    return { _id: id, ...args };
  },
});

export const getByGroup = query({
  args: { groupId: v.string() },
  handler: async (ctx, args) =>
    ctx.db
      .query("modModeState")
      .withIndex("by_group", (q) => q.eq("groupId", args.groupId))
      .unique(),
});

export const deactivate = mutation({
  args: { groupId: v.string() },
  handler: async (ctx, args) => {
    const doc = await ctx.db
      .query("modModeState")
      .withIndex("by_group", (q) => q.eq("groupId", args.groupId))
      .unique();
    if (doc) await ctx.db.patch(doc._id, { isActive: false, updatedAt: Date.now() });
    return { success: true };
  },
});