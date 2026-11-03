import type { MetadataRoute } from "next";

// Outil interne en accès libre : on demande aux moteurs de ne rien indexer.
export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", disallow: "/" } };
}
