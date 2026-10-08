"""URL của app ``rag`` (được include dưới tiền tố ``/rag/``)."""

from django.urls import path

from apps.rag.views import (
    RagChunkDetailView,
    RagChunkListView,
    RawDataDetailView,
    RawDataListCreateView,
)

urlpatterns = [
    path("raw-data/", RawDataListCreateView.as_view(), name="raw-data-list-view"),
    path(
        "raw-data/<uuid:id>/",
        RawDataDetailView.as_view(),
        name="raw-data-detail-view",
    ),
    path("chunks/", RagChunkListView.as_view(), name="rag-chunk-list-view"),
    path(
        "chunks/<uuid:id>/",
        RagChunkDetailView.as_view(),
        name="rag-chunk-detail-view",
    ),
]
