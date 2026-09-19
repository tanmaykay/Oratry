import { defineConfig, globalIgnores } from "eslint/config";
import { FlatCompat } from "@eslint/eslintrc";
import nextVitals from "eslint-config-next/core-web-vitals.js";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });
export default defineConfig(...compat.config(nextVitals), globalIgnores([".next/**", "node_modules/**"]));
