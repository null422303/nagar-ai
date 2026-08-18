# Publishing NagarAI to GitHub — Step-by-Step

This guide covers pushing the project to GitHub so you can share it (and show a clean
single-commit history to judges). It assumes git is installed and the repo lives at
`/home/steven/hackathonn` (it already has commits).

> **Repo already published:** this project lives at
> `https://github.com/null422303/nagar-ai`. The steps below are for a fresh publish
> or a clean-history re-push.

---

## 1. Check the current state

```bash
cd /home/steven/hackathonn
git status          # should be clean ("nothing to commit, working tree clean")
git log --oneline   # shows your commit history
```

If you see uncommitted changes, commit them first:
```bash
git add -A
git commit -m "describe the change"
```

---

## 2. Make sure secrets are NOT committed

The repo ignores secrets via `.gitignore`. **Confirm before pushing:**

```bash
# .env should NOT be tracked (it holds API keys)
git ls-files | grep -E "\.env|sk-" || echo "OK: no secrets tracked"
```

If `backend/.env` ever gets tracked, remove it from history:
```bash
git rm --cached backend/.env
echo "backend/.env" >> .gitignore
git add .gitignore && git commit -m "stop tracking .env"
```

> ⚠️ The demo admin password (`<ADMIN_PASSWORD>`) is a **placeholder** in the repo — the
> real value exists only on the live server. The API keys are **never** committed.

---

## 3. Create the GitHub repository

**Option A — web:**
1. Go to https://github.com/new
2. Name it `nagarai` (or `nagar-ai`).
3. Make it **Public** (or Private — judges may need access, so Public is easier).
4. Do **not** tick "Add a README" (you already have one).
5. Click **Create repository**.

**Option B — CLI (`gh`):**
```bash
gh repo create nagarai --public --source . --remote origin
```

---

## 4. Add the remote & push

```bash
cd /home/steven/hackathonn
git remote add origin https://github.com/YOUR_USERNAME/nagarai.git
git branch -M main
git push -u origin main
```

> If you already pushed to `master`, push again after renaming:
> ```bash
> git push -u origin main
> ```

---

## 5. Verify on GitHub

1. Open `https://github.com/YOUR_USERNAME/nagarai`.
2. The README should render with the architecture diagram.
3. Check `docs/` for the usage guide, screenshots, and tech note.
4. Click **Commits** to show the version history (great for judging).

---

## 6. Optional: add a screenshot to the README header

The README references screenshots in `docs/screenshots/`. GitHub renders relative image
paths automatically once pushed:

```md
![Admin dashboard](docs/screenshots/3-admin-dashboard.png)
```

---

## 7. Keeping it updated after changes

After any change, publish with:
```bash
cd /home/steven/hackathonn
git add -A
git commit -m "your change"
git push
```

### Reset history to a single clean commit (before re-push)
If you want a clean one-commit history on GitHub (recommended for judging — no messy
intermediate commits):
```bash
cd /home/steven/hackathonn
git checkout --orphan clean   # new branch with no history
git add -A
git commit -m "NagarAI — civic complaint intelligence engine"
git branch -M main            # replace main
git push -u origin main --force
# remove the temporary branch
git branch -D clean
```
> `--force` overwrites the remote history — only do this when you intend to replace it.

---

## 8. Repo layout

The repo root is the project: `backend/`, `frontend/`, `scripts/`, `docs/`, `README.md`
all at the top level. No subfolder wrapper — push as-is.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `remote origin already exists` | `git remote set-url origin <new-url>` |
| Auth prompt (HTTPS) | Use a Personal Access Token, or `gh auth login` |
| `src refspec main does not match` | You're on `master`: `git branch -M main` then push |
| Large files (screenshots) rejected | They're small PNGs (~100-400KB) — fine. If a big file blocks, add it to `.gitignore`. |
| `.env` accidentally pushed | See step 2 — use `git rm --cached` and add to history-ignore (`git filter-repo` if needed). |
