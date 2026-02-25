class PlaywrightRouter:

    route_app_labels = {"test_analytics", "test_generation"}

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return "playwright"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return "playwright"
        return None

    def allow_migrate(self, db, app_label, **hints):
        if app_label in self.route_app_labels:
            return db == "playwright"
        return db == "default"
