from django.urls import path
from .views import PayoutRequestView, MerchantBalanceView, PayoutStatusView

urlpatterns = [
    path('payouts/', PayoutRequestView.as_view(), name='payout-request'),
    path('merchants/<uuid:merchant_id>/', MerchantBalanceView.as_view(), name='merchant-balance'),
    path('payouts/<uuid:payout_id>/', PayoutStatusView.as_view(), name='payout-status'),
]