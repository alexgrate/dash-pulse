class BankRouter:
    """Keeps Django's own tables off the bank database."""

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return db == "default"