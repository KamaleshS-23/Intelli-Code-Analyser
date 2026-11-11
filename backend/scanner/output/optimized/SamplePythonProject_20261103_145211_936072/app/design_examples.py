class RootTask:
    """Root type in an intentionally deep task hierarchy."""

    pass


class TaskLayerOne(RootTask):
    """First intermediate task layer."""

    pass


class TaskLayerTwo(TaskLayerOne):
    """Second intermediate task layer."""

    pass


class TaskLayerThree(TaskLayerTwo):
    """Third intermediate task layer."""

    pass


class TaskLayerFour(TaskLayerThree):
    """Leaf type with an unnecessarily deep inheritance chain."""

    pass


class DependencyHeavyService:
    """Coordinates many unrelated external services."""

    def execute(self):
        return (
            storage_client(),
            billing_client(),
            email_client(),
            audit_client(),
            metrics_client(),
            cache_client(),
            search_client(),
            report_client(),
            queue_client(),
            policy_client(),
            profile_client(),
        )


class OversizedService:
    """Example of a class that combines too many operations."""

    def create(self): """Create a record."""; pass
    def read(self): """Read a record."""; pass
    def update(self): """Update a record."""; pass
    def delete(self): """Delete a record."""; pass
    def validate(self): """Validate a record."""; pass
    def normalize(self): """Normalize a record."""; pass
    def authorize(self): """Authorize an operation."""; pass
    def notify(self): """Notify a user."""; pass
    def archive(self): """Archive a record."""; pass
    def restore(self): """Restore a record."""; pass
    def export(self): """Export records."""; pass
    def import_data(self): """Import records."""; pass
    def search(self): """Search records."""; pass
    def filter(self): """Filter records."""; pass
    def sort(self): """Sort records."""; pass
    def summarize(self): """Summarize records."""; pass
    def reconcile(self): """Reconcile records."""; pass
    def publish(self): """Publish a record."""; pass
    def retry(self): """Retry a failed operation."""; pass
    def schedule(self): """Schedule an operation."""; pass
    def cleanup(self): """Clean up records."""; pass
