## Project notes

### Stack
- **Language:** TypeScript
- **Framework:** Next.js 14
- **Database:** Postgres via Prisma

### Conventions
- Use `pnpm`, not `npm`
- Tests live in `__tests__/` next to the source
- Commit messages follow Conventional Commits

### Open items
1. Migrate auth from NextAuth to Lucia
2. Add rate limiting on `/api/upload`
3. Fix flaky test in `billing.spec.ts`