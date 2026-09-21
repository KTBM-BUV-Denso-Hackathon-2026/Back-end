from rest_framework import serializers
from apps.rag.models import RagData, RawData

class RawDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawData
        fields = ['id', 'title', 'description', 'datatype', 'file', 'user']

class RawDataListSerializer(serializers.ListSerializer):
    class Meta:
        model = RawData
        fields = ['id', 'title', 'user']

class RagSerializer(serializers.ModelSerializer):
    class Meta:
        model = RagData
        fields = ['id', 'raw_data', 'vector', 'processed_data']

class RagListSerializer(serializers.ListSerializer):
    class Meta:
        model = RagData
        fields = ['id', 'raw_data', 'vector']