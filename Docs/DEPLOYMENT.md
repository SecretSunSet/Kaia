# Deployment

## Production Environment

- **Host**: AWS EC2
- **Runtime**: Docker + systemd
- **CI/CD**: GitHub Actions (auto-deploy on `main` push)
- **Database**: Supabase PostgreSQL (hosted)

---

## Running Migrations

Migrations are applied manually in the Supabase SQL editor. They are not auto-run at deploy time.

### Phase CH-1 — Channel System (migration 002)

**BEFORE deploying Phase CH-1 code:**

1. Open the Supabase project's SQL editor
2. Paste the contents of `kaia/database/migrations/002_channels.sql`
3. Run it

The migration creates 4 new tables (`channels`, `user_channel_state`, `channel_profile`, `channel_conversations`), seeds 5 channel definitions, enables RLS, and grants service-role access.

The migration is idempotent: `CREATE TABLE IF NOT EXISTS` on tables, `ON CONFLICT (channel_id) DO NOTHING` on seed inserts, `DROP POLICY IF EXISTS` before recreating RLS policies. Re-running it is safe.

### Phase CH-1.1 — Forum Topics Support (migration 003)

**BEFORE deploying Phase CH-1.1 code:**

1. Open the Supabase SQL editor
2. Paste `kaia/database/migrations/003_forum_topics.sql`
3. Run it

Creates the `forum_topic_mappings` table, adds an index on `chat_id`, enables RLS, and grants service-role access. Idempotent.

### Bot permissions for Forum mode

For `/setup_forum` to work the bot needs to be an **admin** in the target group with the **Manage Topics** permission enabled. The group also needs **Topics** turned on (Group Settings → Topics → ON). The `/setup_forum` command surfaces a clear error message if either prerequisite is missing.

### Verification

After running, confirm in Supabase:

```sql
SELECT channel_id, character_name, role FROM channels ORDER BY channel_id;
-- Should return 5 rows: akabane, general, hevn, kazuki, makubex
```

---

## Deployment Steps (Phase CH-1)

1. **Run migration 002** in Supabase SQL editor (see above)
2. **Merge PR to `main`** — GitHub Actions deploys to EC2
3. **Check systemd status** on the EC2 host: `systemctl status kaia`
4. **Smoke test** in Telegram:
   - `/team` should show all 5 team members
   - `/hevn` should trigger an in-character onboarding message
   - `/exit` should return to general
   - A financial question in general chat should trigger an expert suggestion

### Rollback

If issues arise, the schema additions are non-destructive (no column drops, no data migrations). Simply redeploy the previous image tag — the old code ignores the new tables.

The new tables can be left in place; they do not affect Phase 1 functionality.

---

## Cost Considerations

Phase CH-1 adds one additional AI call path but no significant new baseline cost:

- **Channel extraction**: fires after each channel conversation (1 call per exchange). Same cost profile as the existing memory extractor.
- **Expert detector**: rule-based keyword matching — zero AI calls.
- **Onboarding**: one AI call on first visit only (per channel per user).

Expected delta: ~5–10% increase in AI spend if users engage with experts regularly.
