import nextConfig from "eslint-config-next";

const eslintConfig = [
  ...nextConfig,
  {
    // Same files eslint-config-next registers the react-hooks plugin for; without
    // this the rule names fail on other files (server-wrapper.cjs).
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    rules: {
      "react/no-unescaped-entities": "off",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/immutability": "warn",
    },
  },
];

export default eslintConfig;
