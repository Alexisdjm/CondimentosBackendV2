from django.contrib import admin
from core.models import Product, Collection

class CollectionAdmin(admin.ModelAdmin):
    filter_horizontal = ("collection_products",)

admin.site.register(Product)
admin.site.register(Collection, CollectionAdmin)