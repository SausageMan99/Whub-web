import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        whub: "#7001F5",
        ink: "#241D19"
      }
    }
  },
  plugins: []
};
export default config;
