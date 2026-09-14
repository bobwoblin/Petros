"""In-memory Antistasi snapshot normalization and transition tracking."""

from collections import deque


TASK_NAMES = {
    "AS": "Assassination",
    "CON": "Conquest",
    "CONVOY": "Convoy Ambush",
    "DES": "Destroy",
    "LOG": "Supply",
    "RES": "Rescue",
    "RIV_ATT": "Rival Attack",
    "SUPP": "Support",
}


def duration(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return ("{}h ".format(hours) if hours else "") + "{}m".format(minutes)


class CampaignTracker:
    """Keep one reconciled campaign baseline, bounded activity, and one session."""

    def __init__(self, idle_grace=600, recent_limit=75):
        self.idle_grace = idle_grace
        self.recent = deque(maxlen=recent_limit)
        self.snapshot = None
        self.tasks = {}
        self.locations = {}
        self.session = None
        self.empty_since = None
        self.low_fps_samples = 0
        self.low_fps_alerted = False
        self.capability_alerts = set()
        self.saving = None
        self.last_save_started = None
        self.last_save_completed = None

    @staticmethod
    def _tasks(snapshot):
        result = {}
        for item in snapshot.get("missions", []):
            if not isinstance(item, (list, tuple)) or len(item) < 4:
                continue
            task_id, task_type, state, created = item[:4]
            if not all(isinstance(value, str) for value in (task_id, task_type, state)):
                continue
            if state not in ("CREATED", "SUCCEEDED", "FAILED"):
                continue
            try:
                created = float(created)
            except (TypeError, ValueError, OverflowError):
                continue
            result[task_id] = {
                "id": task_id, "type": task_type, "state": state,
                "created": created, "name": TASK_NAMES.get(task_type, task_type),
            }
        return result

    @staticmethod
    def _locations(snapshot):
        result = {}
        for item in snapshot.get("locations", []):
            if not isinstance(item, (list, tuple)) or len(item) < 5:
                continue
            marker, name, kind, owner, grid = (str(value) for value in item[:5])
            if marker:
                result[marker] = {"marker": marker, "name": name, "type": kind,
                                  "owner": owner, "grid": grid}
        return result

    @staticmethod
    def _capabilities(snapshot):
        return {str(item[0]): bool(item[1]) for item in snapshot.get("capabilities", [])
                if isinstance(item, (list, tuple)) and len(item) >= 2}

    @staticmethod
    def _event(kind, description, fields):
        return {"kind": kind, "description": description, "fields": fields}

    def _record(self, now, event):
        self.recent.appendleft({"time": now, **event})

    def _track_session_event(self, event):
        if self.session is None:
            return
        if event["kind"] == "territory_gain":
            self.session["gained"].append(event["fields"][0][1])
        elif event["kind"] == "territory_loss":
            self.session["lost"].append(event["fields"][0][1])
        elif event["kind"] == "mission_succeeded":
            self.session["completed"] += 1
        elif event["kind"] == "mission_failed":
            self.session["failed"] += 1

    def observe_save(self, saving, now):
        """Record only authoritative Antistasi save-state edges."""
        if not isinstance(saving, bool):
            return False
        if saving and self.saving is not True:
            self.last_save_started = now
        elif not saving and self.saving is True:
            self.last_save_completed = now
        self.saving = saving
        if self.snapshot is not None:
            self.snapshot["saving"] = saving
        return True

    def observe_territory(self, row, now):
        """Apply one marker event; the next snapshot then reconciles without duplication."""
        locations = self._locations({"locations": [row]})
        if not locations:
            return []
        marker, current = next(iter(locations.items()))
        previous = self.locations.get(marker)
        self.locations[marker] = current
        if previous is None or previous["owner"] == current["owner"]:
            return []
        old_locations = self.locations
        self.locations = {marker: previous}
        events = self._territory_events({marker: current})
        self.locations = old_locations
        for event in events:
            self._track_session_event(event)
            self._record(now, event)
        return events

    def save_status_text(self, now):
        snapshot = self.snapshot or {}
        capabilities = self._capabilities(snapshot)
        supported = capabilities.get("save", False)
        saving = self.saving if isinstance(self.saving, bool) else snapshot.get("saving", False)
        def observed(value):
            return "not observed since Petros started" if value is None else duration(now - value) + " ago"
        autosave = snapshot.get("nextAutosave", -1)
        autosave_text = duration(autosave) if isinstance(autosave, (int, float)) and autosave >= 0 else "unavailable"
        state = "saving now" if saving else "idle"
        if self.saving is None and not snapshot:
            state = "not observed"
        return (
            "**Antistasi Save Status**\n"
            "State: {}\nLast start: {}\nLast completion: {}\n"
            "Next autosave: {}\nSave support: {}"
        ).format(state, observed(self.last_save_started),
                 observed(self.last_save_completed), autosave_text,
                 "available" if supported else "unsupported")

    def _territory_events(self, locations):
        events = []
        for marker, current in locations.items():
            previous = self.locations.get(marker)
            if not previous or previous["owner"] == current["owner"]:
                continue
            old_owner, new_owner = previous["owner"], current["owner"]
            if new_owner == "Resistance":
                kind, description = "territory_gain", "Resistance control established."
            elif old_owner == "Resistance":
                kind, description = "territory_loss", "Resistance control lost."
            else:
                continue
            events.append(self._event(kind, description, [
                ["Location", current["name"], True], ["Type", current["type"], True],
                ["Previous Owner", old_owner, True], ["New Owner", new_owner, True],
                ["Grid", current["grid"], True],
            ]))
        return events

    def _task_events(self, tasks, uptime):
        events = []
        for task_id, current in tasks.items():
            previous = self.tasks.get(task_id)
            if previous is None:
                events.append(self._event("mission_started", "Mission assigned.", [
                    ["Mission", current["name"], True], ["Task ID", task_id, True]
                ]))
            elif previous["state"] != current["state"] and current["state"] in ("SUCCEEDED", "FAILED"):
                kind = "mission_" + current["state"].lower()
                events.append(self._event(kind, "Mission {}.".format(current["state"].lower()), [
                    ["Mission", current["name"], True],
                    ["Duration", duration(uptime - current["created"]), True],
                    ["Task ID", task_id, True],
                ]))
        for task_id, previous in self.tasks.items():
            if task_id not in tasks and previous["state"] == "CREATED":
                events.append(self._event("mission_cancelled", "Mission removed before an outcome was recorded.", [
                    ["Mission", previous["name"], True], ["Task ID", task_id, True]
                ]))
        return events

    def _start_session(self, snapshot, now):
        self.session = {
            "started": now, "peak": int(snapshot.get("playerCount", 0)),
            "startWar": int(snapshot.get("warLevel", -1)),
            "startHr": int(snapshot.get("hr", -1)),
            "startResources": int(snapshot.get("resources", -1)),
            "gained": [], "lost": [], "completed": 0, "failed": 0,
        }
        self.empty_since = None

    def _finish_session(self, snapshot, now):
        session = self.session
        self.session = None
        self.empty_since = None
        fields = [
            ["Duration", duration(now - session["started"]), True],
            ["Peak Players", str(session["peak"]), True],
            ["Territory", "+{} / -{}".format(len(session["gained"]), len(session["lost"])), True],
            ["War Level", "{} → {}".format(session["startWar"], snapshot.get("warLevel", -1)), True],
            ["HR", self._delta(session["startHr"], snapshot.get("hr", -1)), True],
            ["Resources", self._delta(session["startResources"], snapshot.get("resources", -1)), True],
            ["Missions", "{} succeeded / {} failed".format(session["completed"], session["failed"]), False],
        ]
        changed = session["gained"] + session["lost"]
        if changed:
            fields.append(["Strategic Locations", ", ".join(changed[:10]), False])
        return self._event("session_report", "Campaign play session complete.", fields)

    @staticmethod
    def _delta(start, end):
        try:
            if int(start) < 0 or int(end) < 0:
                return "Unavailable"
            value = int(end) - int(start)
            return "{:+d}".format(value)
        except (TypeError, ValueError, OverflowError):
            return "Unavailable"

    def observe(self, snapshot, now):
        if not isinstance(snapshot, dict):
            return []
        tasks = self._tasks(snapshot)
        locations = self._locations(snapshot)
        if self.snapshot is not None and (
            snapshot.get("map") != self.snapshot.get("map") or
            snapshot.get("campaignId") != self.snapshot.get("campaignId")
        ):
            self.snapshot = None
            self.tasks = {}
            self.locations = {}
            self.session = None
            self.empty_since = None
            self.saving = None
            self.last_save_started = None
            self.last_save_completed = None
        self.observe_save(snapshot.get("saving"), now)
        if self.snapshot is None:
            self.snapshot, self.tasks, self.locations = snapshot, tasks, locations
            if int(snapshot.get("playerCount", 0)) > 0:
                self._start_session(snapshot, now)
            return []

        events = self._territory_events(locations) + self._task_events(
            tasks, float(snapshot.get("uptime", 0)))
        old_war, new_war = int(self.snapshot.get("warLevel", -1)), int(snapshot.get("warLevel", -1))
        if old_war >= 0 and new_war != old_war:
            events.append(self._event("war_change", "Campaign War Level changed.", [
                ["Previous", str(old_war), True], ["Current", str(new_war), True]
            ]))
        old_commander, new_commander = self.snapshot.get("commander"), snapshot.get("commander")
        if old_commander != new_commander and new_commander:
            events.append(self._event("commander_change", "Campaign commander changed.", [
                ["Previous", old_commander or "None", True], ["Current", new_commander, True]
            ]))

        capabilities = self._capabilities(snapshot)
        for name in ("tasks", "territory", "resources"):
            if capabilities.get(name, False):
                if name in self.capability_alerts:
                    self.capability_alerts.remove(name)
                    events.append(self._event("integration_recovered", "Antistasi capability recovered.", [
                        ["Capability", name, True], ["Mode", "Available", True]
                    ]))
            elif name not in self.capability_alerts:
                self.capability_alerts.add(name)
                events.append(self._event("integration_health", "Antistasi capability unavailable.", [
                    ["Capability", name, True], ["Mode", "Degraded", True]
                ]))

        fps = float(snapshot.get("fps", 0))
        self.low_fps_samples = self.low_fps_samples + 1 if 0 < fps < 10 else 0
        if self.low_fps_samples >= 3 and not self.low_fps_alerted:
            self.low_fps_alerted = True
            events.append(self._event("integration_health", "Server FPS is critically low.", [["FPS", str(fps), True]]))
        elif self.low_fps_alerted and fps >= 15:
            self.low_fps_alerted = False
            events.append(self._event("integration_recovered", "Server FPS recovered.", [["FPS", str(fps), True]]))

        for event in events:
            self._track_session_event(event)

        players = int(snapshot.get("playerCount", 0))
        if players > 0:
            if self.session is None:
                self._start_session(snapshot, now)
            self.empty_since = None
            self.session["peak"] = max(self.session["peak"], players)
        elif self.session is not None:
            if self.empty_since is None:
                self.empty_since = now
            elif now - self.empty_since >= self.idle_grace:
                events.append(self._finish_session(snapshot, now))

        for event in events:
            self._record(now, event)
        self.snapshot, self.tasks, self.locations = snapshot, tasks, locations
        return events

    def activity_text(self):
        if not self.recent:
            return "No campaign transitions have been observed since Petros started."
        lines = []
        for item in list(self.recent)[:15]:
            fields = {field[0]: field[1] for field in item["fields"]}
            subject = fields.get("Mission") or fields.get("Location") or fields.get("Current") or ""
            lines.append("- **{}**{}".format(item["kind"].replace("_", " ").title(),
                                             ": " + str(subject) if subject else ""))
        return "\n".join(lines)
