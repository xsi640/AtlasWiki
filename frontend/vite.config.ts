import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
  },
  server: {
    // styles/tokens.css 通过相对路径 @import 仓库根目录的 design/tokens.css，
    // 该文件在 frontend/ 之外，需显式放行才能被 dev server 读取。
    fs: {
      allow: [".."],
    },
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
});
