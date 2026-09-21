from django.urls import path
from .views import RagListView, RawDataDetailView, RawDataListView, RagDetailView

urlpatterns = [
    path('rag-data/', RagListView.as_view(), name='rag-data-list-view'),
    path('rag-data/<int:id>/', RagDetailView.as_view(), name='rag-data-detail-view'),
    path('raw-data/', RawDataListView.as_view(), name='raw-data-list-view'),
    path('raw-data/<int:id>/', RawDataDetailView.as_view(), name='raw-data-detail-view'),
]