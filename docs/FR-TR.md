# dog-care-tracker — Functional & Technical Requirements

**Date:** 2026-03-27
**Status:** MVP Built

---

## 1. Executive Summary

### 1.1 Purpose
Build a native iPhone app for tracking dog walks and feedings with the least possible friction, while preserving a useful care history and surfacing overdue care status at a glance.

### 1.2 Scope
The MVP includes:
- walk tracking (live + manual)
- feeding tracking
- daily dashboard summaries
- local history review
- dog settings for cadence and meal defaults
- local-first persistence

Out of scope for MVP:
- multi-user sync
- cloud accounts
- veterinary records
- medication tracking
- Apple Watch support

## 2. Functional Requirements

### FR-1 — Start a walk
User shall be able to start a live walk timer from the dashboard.

### FR-2 — Finish a walk
User shall be able to finish the active walk and record relief status and notes.

### FR-3 — Manual walk logging
User shall be able to log a completed walk manually with duration and notes.

### FR-4 — Feeding logging
User shall be able to log a feeding with meal type, amount, time, and notes.

### FR-5 — Daily dashboard
App shall show today's walk count, total walk minutes, and feeding count.

### FR-6 — Due / overdue visibility
App shall show whether a walk or feeding is due based on configured cadence.

### FR-7 — History view
App shall show a reverse-chronological history grouped by day.

### FR-8 — Settings
User shall be able to change dog name, default meal amount, walk cadence, and feeding cadence.

### FR-9 — Local persistence
Events and settings shall survive app restarts.

## 3. Technical Requirements

### TR-1 — Native UI
Use SwiftUI for the app interface.

### TR-2 — Local-first storage
Persist MVP data to a JSON snapshot in the app documents directory.

### TR-3 — Central store
Use a single observable store to manage mutations and derived state.

### TR-4 — OTA-ready scaffold
Use ios-deploy-kit project structure, GitHub Actions workflow, signing, and OTA deployment flow.

### TR-5 — Project wiring discipline
All newly added Swift files must be registered with `add-file.py`; never manually edit `project.pbxproj`.

## 4. Data Requirements

The app shall store:
- dog profile settings
- care events
- walk start/end times
- feeding times
- meal kind / amount
- notes
- walk relief status

## 5. Security Requirements

- No secrets stored in app state.
- CI/CD secrets remain in operator infrastructure / GitHub secrets.
- MVP user data remains local on device.

## 6. Performance Requirements

- Logging a walk or feeding should take only a few taps.
- Dashboard should load instantly from local state.
- Persistence should be atomic and resilient to app restarts.
