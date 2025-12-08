# Test Setup Instructions

## Installing Test Dependencies

The property-based tests for the middleware require the following dependencies:

```bash
npm install --save-dev vitest @vitest/ui fast-check
```

**Note:** If you encounter issues with the `canvas` package during installation, you may need to:
1. Install system dependencies (macOS): `brew install pkg-config cairo pango libpng jpeg giflib librsvg pixman`
2. Or use `--legacy-peer-deps` flag: `npm install --legacy-peer-deps`

## Running Tests

Once dependencies are installed, you can run the tests using:

```bash
# Run all tests once
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with UI
npm run test:ui

# Run specific test file
npx vitest run src/middleware.test.ts
```

## Test Coverage

The middleware tests include three property-based tests that validate:

1. **Property 1**: Unauthenticated users visiting `/` or `/enterprise` are redirected to `/auth`
2. **Property 2**: Authenticated users visiting `/` or `/enterprise` are redirected to `/dashboard`
3. **Property 3**: Auth callback parameters are preserved when redirecting to `/auth/callback`

Each property test runs 100 iterations with randomly generated inputs to ensure comprehensive coverage.

## Test Files

- `src/middleware.test.ts` - Property-based tests for middleware routing logic
- `vitest.config.ts` - Vitest configuration
