// Minimal process.env declaration so api.ts compiles without @types/node.
// Next.js inlines NEXT_PUBLIC_* env vars at build time; this just satisfies
// the TypeScript compiler before npm install has run.
declare const process: {
  env: {
    NEXT_PUBLIC_API_URL?: string;
    NODE_ENV: "development" | "production" | "test";
    [key: string]: string | undefined;
  };
};
