class ProjectMemory:
    def __init__(self):
        self.sessions = {}

    def get_session(self, project_id):
        project_id = project_id or "default"
        self.sessions.setdefault(project_id, {"history": [], "latest_scan": None})
        return self.sessions[project_id]

    def remember(self, project_id, message, response):
        session = self.get_session(project_id)
        session["history"].append({
            "user": message,
            "assistant": response,
        })

    def store_scan(self, project_id, scan_result):
        session = self.get_session(project_id)
        session["latest_scan"] = scan_result

    def get_latest_scan(self, project_id):
        return self.get_session(project_id).get("latest_scan")

    def get_history(self, project_id):
        return self.get_session(project_id).get("history", [])
