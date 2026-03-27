# CLAUDE.md — Agent Instructions for DogCareTracker

**STOP. Read this file completely before writing any code.**

This app was built with [ios-deploy-kit](https://github.com/igobymike/ios-deploy-kit). The kit handles CI/CD, code signing, OTA deployment, and push notifications. Do NOT improvise any of that infrastructure.

---

## Mandatory Reading

Before doing any work, read these files in order:
```bash
cat ~/ios-deploy-kit/AGENT.md        # Generic rules and architecture
cat ~/ios-deploy-kit/OPERATOR.md     # Server credentials and URLs (if exists)
```

---

## Critical Rules

1. **You do NOT need a Mac.** GitHub Actions provides macOS runners.
2. **Do NOT manually edit `project.pbxproj`.** Use `add-file.py`:
   ```bash
   python3 ~/ios-deploy-kit/scripts/add-file.py \
     --project DogCareTracker/DogCareTracker.xcodeproj/project.pbxproj \
     --source-root DogCareTracker/DogCareTracker \
     --scan
   ```
3. **Use Tailscale** for server communication. Do NOT create Cloudflare tunnel routes.
4. **All apps share ONE deploy webhook.** Do NOT create new webhook instances.
5. **Do NOT add App Groups or Share Extensions** in the initial build (requires Apple portal registration first).

## SwiftUI Gotchas

- `.foregroundStyle(.accentColor)` **won't compile** — use `.foregroundStyle(Color.accentColor)`
- `Section("Title") { } footer: { }` **won't compile** — use `Section { } header: { Text("Title") } footer: { }`

## This App

| Item | Value |
|------|-------|
| App Name | DogCareTracker |
| Bundle ID | com.baiteks.DogCareTracker |
| GitHub Repo | igobymike/dog-care-tracker |

## Workflow: Adding Code

1. Write your `.swift` files
2. Register them: `python3 ~/ios-deploy-kit/scripts/add-file.py --project DogCareTracker/DogCareTracker.xcodeproj/project.pbxproj --source-root DogCareTracker/DogCareTracker --scan`
3. Commit and push to `main`
4. GitHub Actions builds and signs the IPA
5. Webhook stages OTA files and sends push notification
6. Download artifact, copy IPA to OTA directory (see OPERATOR.md for paths)

## Full Reference

```bash
cat ~/ios-deploy-kit/AGENT.md        # Rules, architecture, error fixes
cat ~/ios-deploy-kit/OPERATOR.md     # Your server credentials and URLs
```
