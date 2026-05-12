from django.db import models
from orders.models import Order
from django.conf import settings



class Delivery(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    delivery_person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('searching', 'Searching'), ('on_way', 'On Way'),('picked_up', 'Picked Up'), ('delivered', 'Delivered')], default='searching')
    current_lat = models.FloatField(null=True, blank=True)
    current_lng = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Delivery for Order {self.order.id} - Status: {self.status}"
