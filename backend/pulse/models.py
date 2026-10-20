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


class FailureNotice(models.Model):
    tx_id = models.BigIntegerField(unique=True)
    sent_at = models.DateTimeField(auto_now_add=True)


class ReportLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    at = models.DateTimeField(auto_now_add=True)
    start = models.DateField()
    end = models.DateField()
    action = models.CharField(max_length=20)
    sent_to = models.EmailField(blank=True)
    status = models.CharField(max_length=20, default="done")
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-at"]
