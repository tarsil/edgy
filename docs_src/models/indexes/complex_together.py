import edgy
from edgy import Database, Index, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


class User(edgy.Model):
    name = edgy.CharField(max_length=255)
    email = edgy.EmailField(max_length=70)
    is_active = edgy.BooleanField(default=True)
    status = edgy.CharField(max_length=255)

    class Meta:
        registry = models
        indexes = [
            Index(fields=["name", "email"]),
            Index(fields=["is_active", "status"], name="active_status_idx"),
        ]