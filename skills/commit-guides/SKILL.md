---
name: commit-guides
description: >
  Creates professional git commits following conventional-commits format.
  Trigger: When creating commits, after completing code changes, when user asks to commit.
metadata:
  auto_invoke:
    - "Creating a git commit"
    - "Committing changes"
---

## Critical Rules

- ALWAYS use conventional-commits format: `type(scope): description`
- ALWAYS keep the first line under 72 characters
- ALWAYS ask for user confirmation before committing
- NEVER be overly specific (avoid counts like "6 subsections", "3 files")
- NEVER include implementation details in the title
- NEVER use `-n` flag unless user explicitly requests it
- NEVER use `git push --force` or `git push -f` (destructive, rewrites history)
- NEVER proactively offer to commit - wait for user to explicitly request it
- **NEVER add `Co-Authored-By` lines automatically (e.g. `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` or any agent signature)**

---

## Commit Format

```
type(scope): concise description

- Key change 1
- Key change 2
- Key change 3
```

### Types

| Type | Use When |
|------|----------|
| `feat` | New feature or functionality |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `chore` | Maintenance, dependencies, configs |
| `refactor` | Code change without feature/fix |
| `test` | Adding or updating tests |
| `perf` | Performance improvement |
| `style` | Formatting, no code change |

### Scopes

| Scope | When |
|-------|------|
| `api` | Changes in `api/` |
| `ui` | Changes in `ui/` |
| `skills` | Changes in `skills/` |
| `docs` | Changes in `docs/` |
| *omit* | Multiple scopes or root-level |

---

## Language Rules

- ALWAYS write the commit title description in Spanish
- ALWAYS write the commit body in Spanish
- KEEP `type` and `scope` in English (Conventional Commits standard)
- NEVER translate `type` (feat, fix, docs, chore, etc.)
- NEVER translate `scope` (api, ui, auth, etc.)
- DO NOT mix Spanish and English within the same commit message

### Writing Style

- ALWAYS use clear and concise Spanish
- ALWAYS use verbs in infinitive form (e.g., "agregar", "corregir", "mejorar", "implementar")
- AVOID unnecessary technical details in the title
- KEEP the title under 72 characters
- USE neutral and professional tone

### Example


## Good vs Bad Examples

### Title Line

```
# GOOD - Concise and clear
feat(api): add provider connection retry logic
fix(ui): resolve dashboard loading state
chore(skills): add Celery documentation
docs: update installation guide

# BAD - Too specific or verbose
feat(api): add provider connection retry logic with exponential backoff and jitter (3 retries max)
chore(skills): add comprehensive Celery documentation covering 8 topics
fix(ui): fix the bug in dashboard component on line 45
```

### Body (Bullet Points)

```
# GOOD - High-level changes
- Add retry mechanism for failed connections
- Document task composition patterns
- Expand configuration reference

# BAD - Too detailed
- Add retry with max_retries=3, backoff=True, jitter=True
- Add 6 subsections covering chain, group, chord
- Update lines 45-67 in dashboard.tsx
```

---

## Workflow

1. **Analyze changes**
   ```bash
   git status
   git diff --stat HEAD
   git log -3 --oneline  # Check recent commit style
   ```

2. **Draft commit message**
   - Choose appropriate type and scope
   - Write concise title (< 72 chars)
   - Add 2-5 bullet points for significant changes

3. **Present to user for confirmation**
   - Show files to be committed
   - Show proposed message
   - Wait for explicit confirmation

4. **Execute commit**
   ```bash
   git add <files>
   git commit -m "$(cat <<'EOF'
   type(scope): description

   - Change 1
   - Change 2
   EOF
   )"
   ```

---

## Decision Tree

```
Single file changed?
├─ Yes → May omit body, title only
└─ No → Include body with key changes

Multiple scopes affected?
├─ Yes → Omit scope: `feat: description`
└─ No → Include scope: `feat(api): description`

Fixing a bug?
├─ User-facing → fix(scope): description
└─ Internal/dev → chore(scope): fix description

Adding documentation?
├─ Code docs (docstrings) → Part of feat/fix
└─ Standalone docs → docs: or docs(scope):
```

---

## Commands

```bash
# Check current state
git status
git diff --stat HEAD

# Standard commit
git add <files>
git commit -m "type(scope): description"

# Multi-line commit
git commit -m "$(cat <<'EOF'
type(scope): description

- Change 1
- Change 2
EOF
)"

# Amend last commit (same message)
git commit --amend --no-edit

# Amend with new message
git commit --amend -m "new message"
```