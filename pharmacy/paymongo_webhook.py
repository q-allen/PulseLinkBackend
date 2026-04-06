import json
import hmac
import hashlib
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings


@csrf_exempt
@require_http_methods(["POST"])
def paymongo_webhook(request):
    """Handle PayMongo webhook events"""
    
    # Verify webhook signature
    signature = request.headers.get('Paymongo-Signature')
    if not signature or not verify_signature(request.body, signature):
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    # Parse event
    try:
        event = json.loads(request.body)
        event_type = event['data']['attributes']['type']
        
        # Handle payment events
        if event_type in ['payment.paid', 'checkout_session.payment.paid']:
            handle_payment_success(event)
        elif event_type in ['payment.failed', 'checkout_session.payment.failed']:
            handle_payment_failed(event)
        elif event_type in ['payment.cancelled', 'checkout_session.payment.cancelled']:
            handle_payment_cancelled(event)
            
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def verify_signature(payload, signature):
    """Verify PayMongo webhook signature"""
    secret = settings.PAYMONGO_WEBHOOK_SECRET
    if not secret:
        return False
    
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


def handle_payment_success(event):
    """Update order/appointment status when payment succeeds"""
    # TODO: Implement based on your models
    pass


def handle_payment_failed(event):
    """Handle failed payments"""
    # TODO: Implement based on your models
    pass


def handle_payment_cancelled(event):
    """Handle cancelled payments"""
    # TODO: Implement based on your models
    pass
