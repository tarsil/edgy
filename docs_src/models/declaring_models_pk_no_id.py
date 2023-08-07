import uuid

import edgy
from edgy import Database, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


class User(edgy.Model):
    name = edgy.CharField(max_length=255, primary_key=True, default=str(uuid.uuid4))
    age = edgy.IntegerField(minimum=18)
    is_active = edgy.BooleanField(default=True)

    class Meta:
        registry = models
