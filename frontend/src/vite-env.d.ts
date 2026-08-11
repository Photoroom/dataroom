/**
 * Bring in Vite's global type declarations for the frontend.
 *
 * This enables typing for `import.meta.env` (and related Vite globals) used in the
 * React code. Without it, TypeScript will error with:
 *   Property 'env' does not exist on type 'ImportMeta'.
 *
 */
/// <reference types="vite/client" />

declare const __GIT_COMMIT__: string;
declare const __GIT_REPO_URL__: string;
