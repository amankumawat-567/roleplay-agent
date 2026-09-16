import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Production: the built dist/ is served directly by FastAPI (same origin,
// see main.py), so /api needs no proxy there. This proxy only matters for
// `npm run dev` against a locally running backend (`make dev`, port 8000).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      // Game covers, profile avatars, and voice samples are all served
      // straight off data/ by FastAPI (see main.py's /media mounts) - same
      // dev-only proxy gap /api has, just not hit until AudioPage's sample
      // playback actually exercised it.
      "/media": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
