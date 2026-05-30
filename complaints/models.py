# complaints/models.py
from django.db import models
from django.conf import settings

class Complaint(models.Model):

    ISSUE_TYPES = [
        ('garbage',     'Garbage'),
        ('road',        'Road Damage'),
        ('water',       'Water Supply'),
        ('streetlight', 'Streetlight'),
    ]
    STATUS = [
        ('submitted', 'Submitted'),
        ('seen',      'Seen'),
        ('resolved',  'Resolved'),
    ]

    user        = models.ForeignKey(
                    settings.AUTH_USER_MODEL,
                    on_delete=models.CASCADE
                  )
    issue_type  = models.CharField(max_length=20, choices=ISSUE_TYPES)
    description = models.TextField(blank=True)
    image       = models.ImageField(upload_to='complaints/', blank=True)
    latitude    = models.FloatField(default=0.0)
    longitude   = models.FloatField(default=0.0)
    status      = models.CharField(max_length=20, choices=STATUS, default='submitted')
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.issue_type} — {self.status}"

    class Meta:
        ordering = ['-created_at']