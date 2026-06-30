import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg:      "#0a0e17",
        panel:   "#111726",
        panel2:  "#161d2e",
        border:  "#1f2940",
        txt:     "#e2e8f5",
        dim:     "#7d8aa8",
        up:      "#16c784",
        down:    "#ea3943",
        accent:  "#3d8bff",
        warn:    "#f7a440",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
