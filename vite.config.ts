import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { workingMemoryPreview } from "./working-memory/dev-proxy";

export default defineConfig({
  plugins: [react(), workingMemoryPreview()],
  server: {
    host: "127.0.0.1",
    fs: { deny: [".env", ".env.*", "*.{crt,pem}", "**/.git/**", "**/.local/**"] },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
