from django.shortcuts import render
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from apps.rag.models import RawData, RagData
from apps.rag.serializers import RagSerializer


"""
##########################################
Raw Data Views
##########################################
"""
# Create your views here.
class RawDataListView(ListCreateAPIView):
    queryset = RawData.objects.all()
    serializer_class = RagSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = self.request.user
        if self.request.user.is_superuser:
            return RawData.objects.all()
        elif self.request.user.level == 'senior engineer':
            return RawData.objects.filter(user=user)
        else:
            return 400, {"message": "You do not have permission to view this data."}

    def post(self, request, *args, **kwargs):
        user = self.request.user
        if self.request.user.is_superuser or self.request.user.level == 'senior engineer':
            title = request.data.get('title')
            description = request.data.get('description')
            datatype = request.data.get('datatype')
            file = request.data.get('file')

            raw_data = RawData.objects.create(
                title=title,
                description=description,
                datatype=datatype,
                file=file,
                user=user
            )

            if raw_data:
                return 200, {"message": "Raw data created successfully."}
            else:
                return 400, {"message": "Failed to create raw data."}
            #return super().post(request, *args, **kwargs)

class RawDataDetailView(RetrieveUpdateDestroyAPIView):
    queryset = RawData.objects.all()
    serializer_class = RagSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, id, *args, **kwargs):
        user = self.request.user
        data = RawData.objects.filter(id=id).first()
        if not data:
            return 404, {"message": "Data not found."}
        if self.request.user.is_superuser or self.request.user.level == 'senior engineer' or data.user == user:
            return data

    def put(self, request, id, *args, **kwargs):
        user = self.request.user
        data = RawData.objects.filter(id=id).first()
        if not data:
            return 404, {"message": "Data not found."}
        if self.request.user.is_superuser or self.request.user.level == 'senior engineer' or data.user == user:
            title = request.data.get('title')
            description = request.data.get('description')
            datatype = request.data.get('datatype')
            file = request.data.get('file')

            data.title = title if title else data.title
            data.description = description if description else data.description
            data.datatype = datatype if datatype else data.datatype
            data.file = file if file else data.file
            data.save()

            return 200, {"message": "Raw data updated successfully."}
        else:
            return 400, {"message": "You do not have permission to update this data."}

    def delete(self, request, id, *args, **kwargs):
        user = self.request.user
        data = RawData.objects.filter(id=id).first()
        if not data:
            return 404, {"message": "Data not found."}
        if self.request.user.is_superuser or self.request.user.level == 'senior engineer' or data.user == user:
            data.delete()
            return 200, {"message": "Raw data deleted successfully."}
        else:
            return 400, {"message": "You do not have permission to delete this data."}



"""
##########################################
RAG Data Views
##########################################
"""        
class RagListView(ListCreateAPIView):
    queryset = RagData.objects.all()
    serializer_class = RagSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = self.request.user
        if user.is_superuser:
            return RagData.objects.all()
        else:
            return 400, {"message": "You do not have permission to view this data."}


class RagDetailView(RetrieveUpdateDestroyAPIView):
    queryset = RagData.objects.all()
    serializer_class = RagSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, id, *args, **kwargs):
        user = self.request.user
        data = RagData.objects.filter(id=id).first()
        if not data:
            return 404, {"message": "Data not found."}
        if user.is_superuser:
            return data
        else:
            return 400, {"message": "You do not have permission to view this data."}