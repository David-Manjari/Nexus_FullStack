import uuid

def simulate_payment(amount, currency="KES", simulated_result="paid"):
    """
    Simulate a payment without transferring real money.
    Only paid and failed outcomes are supported.
    """
    if simulated_result not in ("paid", "failed"):
        raise ValueError("Simulated result must be 'paid' or 'failed'.")

    payment_reference = "SIM-" + uuid.uuid4().hex[:12].upper()

    if simulated_result == "failed":
        return {
            "status": "failed",
            "payment_reference": payment_reference,
            "message": "Simulated payment failure. No money was transferred.",
        }

    return {
        "status": "paid",
        "payment_reference": payment_reference,
        "message": (
            f"Simulated payment of {currency} {amount:.2f} completed. "
            "No money was transferred."
        ),
    }
