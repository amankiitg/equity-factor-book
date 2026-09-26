import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The build config: the page and its one stylesheet. The tests have their own
// config (`vitest.config.ts`) with no plugins at all, because the only thing they
// need is a DOM and Vite's own JSX transform, and a plugins array there drags two
// copies of Vite's plugin types into one file for no gain.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "dist", emptyOutDir: true },
});
