from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def homepage(request):
    return JsonResponse({
        'service': 'Playto Payout Engine',
        'status': 'running',
        'version': '1.0.0',
        'endpoints': {
            'admin': '/admin/',
            'payout_request': '/api/v1/payouts/',
            'merchant_balance': '/api/v1/merchants/{merchant_id}/',
            'payout_status': '/api/v1/payouts/{payout_id}/',
        },
        'test_merchants': {
            'rahul': '/api/v1/merchants/4c22ecd4-4f40-4ffb-b26f-6ccfca874796/',
            'priya': '/api/v1/merchants/d64bebe0-a3e6-4857-8e96-2fe6c32405c6/',
            'arjun': '/api/v1/merchants/d0132f05-a997-43a0-be58-a3c52d285ec4/',
        }
    })

urlpatterns = [
    path('', homepage),
    path('admin/', admin.site.urls),
    path('api/v1/', include('payouts.urls')),
]