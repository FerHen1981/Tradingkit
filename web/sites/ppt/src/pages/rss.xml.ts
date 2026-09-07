import rss from "@astrojs/rss";
import type { APIContext } from "astro";

import { site } from "../site.config";
import { allPosts, postPath } from "../lib/posts";

/**
 * A blog without a feed is a blog you can only read by remembering to visit.
 * Summaries only — the full post lives on the site.
 */
export async function GET(context: APIContext) {
  const posts = await allPosts();

  return rss({
    title: site.name,
    description: site.description,
    site: context.site ?? site.origin,
    trailingSlash: false,
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.summary,
      pubDate: post.data.date,
      link: postPath(post),
      categories: [...post.data.tags],
    })),
    customData: "<language>nl-nl</language>",
  });
}
