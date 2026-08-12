import { mutationGeneric, queryGeneric } from "convex/server";
import { v } from "convex/values";

export const getSetting = queryGeneric({
  args: {
    key: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("appSettings")
      .withIndex("by_key", (query) => query.eq("key", args.key))
      .unique();
  },
});

export const setSetting = mutationGeneric({
  args: {
    key: v.string(),
    value: v.any(),
    updatedBy: v.optional(v.union(v.string(), v.null())),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const existing = await ctx.db
      .query("appSettings")
      .withIndex("by_key", (query) => query.eq("key", args.key))
      .unique();

    if (existing) {
      await ctx.db.patch(existing._id, {
        value: args.value,
        updatedBy: args.updatedBy ?? undefined,
        updatedAt: now,
      });
      return await ctx.db.get(existing._id);
    }

    const settingId = await ctx.db.insert("appSettings", {
      key: args.key,
      value: args.value,
      updatedBy: args.updatedBy ?? undefined,
      updatedAt: now,
    });

    return await ctx.db.get(settingId);
  },
});