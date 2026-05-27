import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        whub: "#7001F5",
        ink: "#241D19",
        porcelain: "#F7F4F0",
        chalk: "#FFFFFF",
        lilac: "#EEE3FF",
        graphite: "#141118",
        mist: "#F1EDF7"
      },
      boxShadow: {
        soft: "0 24px 70px rgba(36, 29, 25, 0.10)",
        violet: "0 18px 42px rgba(112, 1, 245, 0.28)"
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
};
export default config;
