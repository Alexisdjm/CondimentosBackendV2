from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, StringRelatedField
from core.models import Product, Collection

class SessionSerializer(serializers.Serializer):
    session_key = serializers.CharField()

class ProductSerializer(ModelSerializer):
    session = serializers.SerializerMethodField()

    image = serializers.ImageField(
        max_length=None, allow_empty_file=False, allow_null=True, use_url=True, required=False)
    class Meta:
        model = Product
        fields = ['id','name', 'measurement', 'description','available','featured','image','category', 'session']

    def get_session(self, obj):
        request = self.context.get('request')
        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key
        status = False
        cart = request.session.get('cart', {})
        for key, product in cart.items():
            if key == str(obj.id):
                status = True
        return {'in_cart': status}

class CollectionSerializer(ModelSerializer):
    collection_products = ProductSerializer(many=True)
    class Meta:
        model = Collection
        fields = ['id','title','discount_percent', 'featured', 'collection_products']
