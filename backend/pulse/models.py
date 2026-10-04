from django.conf import settings
from django.db import models


class ExploreLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    at = models.DateTimeField(auto_now_add=True)
    path = models.CharField(max_length=255)
    query = models.CharField(max_length=1000, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]
