from django.urls import path
from . import views
app_name = 'restaurants'
urlpatterns = [
    path('', views.restaurant_list, name="restaurant_list"),
    path("dashboard/", views.restaurant_dashboard, name="restaurant_dashboard"),
    path("search/", views.all_menu_items, name="all_menu_items"),
    path("<int:restaurant_id>/", views.restaurant_menu, name="restaurant_menu"),
    path("add-item/", views.add_menu_item, name="add_menu_item"),
    path("add_discount/", views.add_discount, name="add_discount"),
    path("manage_menu/", views.manage_menu, name="manage_menu"),
    path("category/add/", views.add_category, name="add_category"),
    path("settings/update/", views.update_restaurant_settings, name="update_restaurant_settings"),
    path("settings/update-logo/", views.update_logo, name="update_logo"),
    path("delete_menu_item/<int:item_id>/", views.delete_menu_item, name="delete_menu_item"),
    path("set-location/", views.set_customer_location, name="set_customer_location"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
]