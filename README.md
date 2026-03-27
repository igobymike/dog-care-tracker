# dog-care-tracker

> Native iPhone app for logging dog walks and feedings in seconds, with daily status, overdue signals, and care history you can trust.

[![Built by BAITEKS](https://img.shields.io/badge/Built%20by-BAITEKS-0066cc)](https://baiteks.com)
[![Platform](https://img.shields.io/badge/Platform-iOS%2017%2B-black)]()
[![Status](https://img.shields.io/badge/Status-MVP%20Built-brightgreen)]()

---

## The Problem

Dog care gets handled in real life, but tracking often happens in memory, texts, or not at all. That creates avoidable friction:
- Did the dog already eat?
- How long ago was the last walk?
- Did the walk include pee, poop, both, or neither?
- Who handled what today?

The cost is not just annoyance — it's missed feedings, duplicate feedings, inconsistent walks, and low-confidence care handoffs.

## The Solution

dog-care-tracker is a native iPhone app that turns dog care into a simple daily timeline. It lets you start a walk, finish a walk, log a manual walk, log a feeding, review today's activity, and check whether another walk or meal is due. The MVP is local-first, fast, and intentionally optimized for actual use instead of overbuilt pet-tech complexity.

## Key Features

- **Start / finish live walks** with quick timing and relief status
- **Manual walk logging** for walks you forgot to start in-app
- **Feeding logging** with meal type, amount, notes, and timestamp
- **Today's dashboard** with walk/feed counts and walk minutes
- **Due / overdue status** for feeding and walking cadence
- **History screen** grouped by day with edit/delete support
- **Settings** for dog name, meal defaults, and timing windows
- **Offline-first local storage** via JSON snapshot persistence
- **OTA-ready iOS scaffold** wired into ios-deploy-kit CI/CD

## Architecture

| Layer | Responsibility |
|------|-----------------|
| SwiftUI App Shell | Tab-based navigation for Dashboard / History / Settings |
| DogCareStore | Central state, persistence, business rules, derived dashboard data |
| Care Models | Walk / feeding events, dog profile settings, persistence snapshot |
| JSON Persistence | Local-first storage in app documents directory |
| ios-deploy-kit Scaffold | GitHub Actions build/sign/deploy + OTA pipeline |

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|--------|
| App UI | SwiftUI | Native iPhone interface |
| State | ObservableObject | Central reactive app state |
| Persistence | JSON + FileManager | Local-first MVP storage |
| CI/CD | ios-deploy-kit + GitHub Actions | macOS build, signing, OTA deploy |
| OTA Install | deploy.baiteks.com webhook | iPhone install flow |

## Getting Started

```bash
cd /home/mike/dog-care-tracker

# Register all Swift files in the Xcode project after adding new files
python3 /home/mike/ios-deploy-kit/scripts/add-file.py \
  --project DogCareTracker/DogCareTracker.xcodeproj/project.pbxproj \
  --source-root DogCareTracker/DogCareTracker \
  --scan

# Commit and push to trigger the iOS build pipeline
git add -A
git commit -m "Build dog care tracker MVP"
git push origin main
```

## Roadmap

- [x] Scaffold iOS app with ios-deploy-kit
- [x] Build local-first MVP for walks, feedings, dashboard, history, settings
- [ ] Push and verify GitHub Actions build
- [ ] Stage OTA and verify install URL
- [ ] Add local notifications / reminders
- [ ] Add richer analytics and shared caregiver workflows

## License

MIT
