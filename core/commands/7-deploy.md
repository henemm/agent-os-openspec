# Deploy to Production

Deploy the current main branch to production.

**CUSTOMIZE THIS FILE for your project's deployment setup!**

## Pre-Flight Checks

Before deploying, verify:

```bash
# Current branch
git branch --show-current

# Uncommitted changes?
git status --porcelain

# Main is up to date with remote?
git fetch origin main
git log HEAD..origin/main --oneline
```

**STOP if:**
- Uncommitted changes exist -> Commit or stash first
- Main is behind origin -> Run `git pull` first
- Tests are failing -> Fix tests first

## Deployment Steps

### Option A: Git-based Deployment

```bash
# Ensure on main
git checkout main

# Push to main (if not already)
git push origin main

# Merge to production branch
git checkout production
git merge main --no-edit
git push origin production

# Return to main
git checkout main
```

### Option B: Direct Deployment (customize for your platform)

**For Vercel:**
```bash
vercel --prod
```

**For Google Cloud Run:**
```bash
gcloud builds submit --config=cloudbuild.yaml
```

**For AWS:**
```bash
aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment
```

**For Heroku:**
```bash
git push heroku main
```

## Post-Deployment Verification

1. **Check deployment status** (platform-specific)
2. **Verify application is running:**
   - Open production URL
   - Check health endpoint
   - Verify key functionality

3. **Monitor logs for errors:**
   ```bash
   # Example for various platforms
   # vercel logs
   # gcloud run services logs read <service>
   # heroku logs --tail
   ```

## Rollback (if needed)

```bash
# Git-based rollback
git checkout production
git revert HEAD
git push origin production
```

## Configuration

Customize this template by updating:
- Deployment commands for your platform
- Production URL
- Health check endpoints
- Log viewing commands
- Rollback procedures

---

**Note:** This is a template. Copy to your project and customize for your specific deployment setup.
