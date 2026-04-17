from django.urls import path
from .views import (
    MedicineDetailView,
    MedicineListView,
    OrderDetailView,
    OrderListView,
    CancelOrderView,
    OrderFromPrescriptionView,
    AdminOrderStatusView,
    PayMongoWebhookView,
    PrescriptionUploadView,
    PrescriptionUploadFileView,
)

urlpatterns = [
    path("medicines",                        MedicineListView.as_view(),           name="medicine-list"),
    path("medicines/<int:pk>",               MedicineDetailView.as_view(),         name="medicine-detail"),
    path("prescriptions/upload",             PrescriptionUploadView.as_view(),     name="prescription-upload"),
    path("prescriptions/upload/<int:pk>/file", PrescriptionUploadFileView.as_view(), name="prescription-upload-file"),
    path("orders",                           OrderListView.as_view(),               name="order-list"),
    path("orders/from-prescription",         OrderFromPrescriptionView.as_view(),   name="order-from-prescription"),
    path("orders/<int:pk>",                  OrderDetailView.as_view(),             name="order-detail"),
    path("orders/<int:pk>/cancel",           CancelOrderView.as_view(),             name="order-cancel"),
    path("orders/<int:pk>/status",           AdminOrderStatusView.as_view(),        name="order-status-update"),
    path("paymongo/webhook",                 PayMongoWebhookView.as_view(),         name="paymongo-webhook"),
]
