from django.db import models
from orders.models import Order
from django.conf import settings
from geopy.distance import geodesic

class Delivery(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    delivery_person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('searching', 'Searching'), ('on_way', 'On Way'),('picked_up', 'Picked Up'), ('delivered', 'Delivered')], default='searching')
    current_lat = models.FloatField(null=True, blank=True)
    current_lng = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Delivery for Order {self.order.id} - Status: {self.status}"
    
    
    def calculate_distance(self):
        try:
            if not self.current_lat or not self.current_lng:
                return 0
            if not self.order.restaurant.latitude or not self.order.restaurant.longitude:
                return 0
            restaurant_coords = (float(self.order.restaurant.latitude), float(self.order.restaurant.longitude))
            delivery_coords = (float(self.current_lat), float(self.current_lng))
            return round(geodesic(restaurant_coords, delivery_coords).km, 2)
        except Exception as e:
            print(f"Error calculating distance: {e}")
        return 0

    @property
    def delivery_fee(self):
        distance = self.calculate_distance()
        base_fee = 200
        per_km_fee = 1500
        return int(base_fee + (distance * per_km_fee))



