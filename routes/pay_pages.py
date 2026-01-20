from flask import Blueprint

pay_pages_bp = Blueprint("pay_pages", __name__)

@pay_pages_bp.get("/pay/success")
def pay_success():
    # Simple page Stripe redirects to after payment
    return """
    <html>
      <head><title>Payment Success</title></head>
      <body style="font-family: system-ui; max-width: 720px; margin: 40px auto;">
        <h1>Payment Successful ✅</h1>
        <p>Your payment was accepted. Your booking will be confirmed automatically (via Stripe webhook).</p>
        <p>You can now return to the app and check <b>My Bookings</b>.</p>
      </body>
    </html>
    """, 200

@pay_pages_bp.get("/pay/cancel")
def pay_cancel():
    return """
    <html>
      <head><title>Payment Cancelled</title></head>
      <body style="font-family: system-ui; max-width: 720px; margin: 40px auto;">
        <h1>Payment Cancelled ❌</h1>
        <p>No payment was taken. You can try booking again from the Slots page.</p>
      </body>
    </html>
    """, 200
