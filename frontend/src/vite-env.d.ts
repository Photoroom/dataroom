/**
 * Bring in Vite's global type declarations for the frontend.
 *
 * This enables typing for `import.meta.env` (and related Vite globals) used in the
 * React code. Without it, TypeScript will error with:
 *   Property 'env' does not exist on type 'ImportMeta'.
 *
 */
/// <reference types="vite/client" />
