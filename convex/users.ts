import { mutationGeneric, queryGeneric } from "convex/server";
import { v } from "convex/values";

const nullableString = v.optional(v.union(v.string(), v.null()));
const nullableStringArray = v.optional(v.union(v.array(v.string()), v.null()));

function normalizeAliases(values: string[] | undefined | null): string[] | undefined {
  if (!values || values.length === 0) {
    return undefined;
  }

  const aliases = Array.from(
    new Set(values.map((value) => value.trim()).filter((value) => value.length > 0)),
  );
  return aliases.length > 0 ? aliases : undefined;
}

export const getByLineUserId = queryGeneric({
  args: {
    lineUserId: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("users")
      .withIndex("by_line_user_id", (query) => query.eq("lineUserId", args.lineUserId))
      .unique();
  },
});

export const upsertUser = mutationGeneric({
  args: {
    lineUserId: v.string(),
    displayName: nullableString,
    role: nullableString,
    aliases: nullableStringArray,
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const existing = await ctx.db
      .query("users")
      .withIndex("by_line_user_id", (query) => query.eq("lineUserId", args.lineUserId))
      .unique();

    const patch = {
      lineUserId: args.lineUserId,
      displayName: args.displayName ?? undefined,
      role: args.role ?? undefined,
      aliases: normalizeAliases(args.aliases),
      updatedAt: now,
    };

    if (existing) {
      await ctx.db.patch(existing._id, patch);
      return await ctx.db.get(existing._id);
    }

    const userId = await ctx.db.insert("users", {
      ...patch,
      createdAt: now,
    });

    return await ctx.db.get(userId);
  },
});