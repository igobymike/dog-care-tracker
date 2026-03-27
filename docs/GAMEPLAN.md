# dog-care-tracker — Build Game Plan

**Date:** 2026-03-27
**Status:** Active

---

## Overview

Build the first useful iPhone version fast: walking, feeding, history, settings, and local persistence. Keep the architecture simple and shippable first, then layer on reminders, notifications, and caregiver coordination later.

---

## Step 1 — Scaffold the app
**Goal:** Create a correct iOS project with deploy pipeline wiring.
**Tasks:**
- Run `create-app.py`
- Generate Xcode project
- Generate CLAUDE.md and CI workflow
- Confirm repo structure
**Deliverable:** OTA-ready iOS scaffold
**Estimated Time:** 15–20 min

## Step 2 — Build the core data model
**Goal:** Represent walks, feedings, and dog settings cleanly.
**Tasks:**
- Create care event models
- Create profile/settings model
- Create persistence snapshot model
**Deliverable:** Codable local data model
**Estimated Time:** 30–45 min

## Step 3 — Build the app state layer
**Goal:** Centralize mutations and derived dashboard logic.
**Tasks:**
- Create DogCareStore
- Add JSON persistence
- Add derived totals and due/overdue status
- Add walk / feeding actions
**Deliverable:** Working local-first store
**Estimated Time:** 45–60 min

## Step 4 — Build the UI
**Goal:** Ship a useful MVP interface.
**Tasks:**
- Dashboard screen
- History screen
- Settings screen
- Feeding entry sheet
- Manual walk sheet
- Finish walk sheet
**Deliverable:** Usable iPhone MVP
**Estimated Time:** 60–90 min

## Step 5 — Register project files and push
**Goal:** Make the code buildable in CI.
**Tasks:**
- Run `add-file.py --scan`
- Commit files
- Push to GitHub
**Deliverable:** CI-ready repo state
**Estimated Time:** 10–15 min

## Step 6 — Verify deploy chain
**Goal:** Confirm the app can actually be built and installed.
**Tasks:**
- Inspect GitHub Actions run
- Verify webhook/downstream deploy path
- Verify OTA/install URL
**Deliverable:** First installable build
**Estimated Time:** 20–40 min
