import { useContext, useState } from "react";
import { CartContext } from "../context/CartContext";
import { useNavigate } from "react-router-dom";

function Checkout() {
    const { cart, clearCart, saveOrder, appliedCoupon } = useContext(CartContext);
    const navigate = useNavigate();

    const [shipping, setShipping] = useState({
        name: "",
        address: "",
        city: "",
        zip: "",
    });

    const [billing, setBilling] = useState({
        name: "",
        address: "",
        city: "",
        zip: "",
    });

    const [sameAsShipping, setSameAsShipping] = useState(false);
    const [loading, setLoading] = useState(false);

    const subtotal = cart.reduce(
        (sum, item) => sum + item.price * item.quantity,
        0
    );

    let discount = 0;
    if (appliedCoupon) {
        if (appliedCoupon.type === "PERCENT") {
            discount = (subtotal * appliedCoupon.value) / 100;
        } else if (appliedCoupon.type === "FLAT") {
            discount = appliedCoupon.value;
        }
    }

    const total = subtotal - discount;

    const handlePayment = () => {
        if (!shipping.name || !shipping.address) {
            alert("Please fill Shipping Details");
            return;
        }

        const finalBilling = sameAsShipping ? shipping : billing;

        const orderData = {
            id: Date.now(),
            items: cart,
            subtotal,
            discount,
            total,
            coupon: appliedCoupon ? appliedCoupon.code : null,
            shipping,
            billing: finalBilling,
            date: new Date().toLocaleString(),
        };

        setLoading(true);

        setTimeout(() => {
            saveOrder(orderData);
            clearCart();
            localStorage.removeItem("coupon"); // Clear coupon after order
            navigate("/confirmation");
        }, 2000);
    };

    return (
        <div className="container mt-4">
            <h2>Checkout</h2>

            <div className="row mt-4">
                {/* Order Summary */}
                <div className="col-md-4">
                    <div className="card p-3 shadow-sm">
                        <h5>Order Details</h5>
                        {cart.map((item) => (
                            <div key={item.id} className="d-flex justify-content-between small mb-1">
                                <span>{item.name} x {item.quantity}</span>
                                <span>₹{item.price * item.quantity}</span>
                            </div>
                        ))}
                        <hr />
                        <div className="d-flex justify-content-between mb-1">
                            <span>Subtotal:</span>
                            <span>₹{subtotal}</span>
                        </div>
                        {discount > 0 && (
                            <div className="d-flex justify-content-between mb-1 text-danger">
                                <span>Discount ({appliedCoupon.code}):</span>
                                <span>-₹{discount}</span>
                            </div>
                        )}
                        <div className="d-flex justify-content-between fw-bold h6 mt-2">
                            <span>Total:</span>
                            <span>₹{total}</span>
                        </div>
                    </div>
                </div>

                {/* Address Forms */}
                <div className="col-md-8">
                    <div className="card p-3 shadow-sm mb-3" data-testid="shipping-section">
                        <h5>Shipping Address</h5>
                        <input
                            className="form-control mb-2"
                            placeholder="Full Name"
                            onChange={(e) =>
                                setShipping({ ...shipping, name: e.target.value })
                            }
                        />
                        <input
                            className="form-control mb-2"
                            placeholder="Address"
                            onChange={(e) =>
                                setShipping({ ...shipping, address: e.target.value })
                            }
                        />
                        <input
                            className="form-control mb-2"
                            placeholder="City"
                            onChange={(e) =>
                                setShipping({ ...shipping, city: e.target.value })
                            }
                        />
                        <input
                            className="form-control mb-2"
                            placeholder="ZIP Code"
                            onChange={(e) =>
                                setShipping({ ...shipping, zip: e.target.value })
                            }
                        />
                    </div>

                    <div className="form-check mb-3">
                        <input
                            type="checkbox"
                            className="form-check-input"
                            onChange={(e) => setSameAsShipping(e.target.checked)}
                        />
                        <label className="form-check-label">
                            Billing address same as Shipping
                        </label>
                    </div>

                    {!sameAsShipping && (
                        <div className="card p-3 shadow-sm mb-3" data-testid="billing-section">
                            <h5>Billing Address</h5>
                            <input
                                className="form-control mb-2"
                                placeholder="Full Name"
                                onChange={(e) =>
                                    setBilling({ ...billing, name: e.target.value })
                                }
                            />
                            <input
                                className="form-control mb-2"
                                placeholder="Address"
                                onChange={(e) =>
                                    setBilling({ ...billing, address: e.target.value })
                                }
                            />
                            <input
                                className="form-control mb-2"
                                placeholder="City"
                                onChange={(e) =>
                                    setBilling({ ...billing, city: e.target.value })
                                }
                            />
                            <input
                                className="form-control mb-2"
                                placeholder="ZIP Code"
                                onChange={(e) =>
                                    setBilling({ ...billing, zip: e.target.value })
                                }
                            />
                        </div>
                    )}

                    {/* Payment */}
                    <div className="text-end">
                        <button
                            id="pay-now-btn"
                            className="btn btn-success pay-now-button"
                            onClick={handlePayment}
                            disabled={loading}
                        >
                            {loading ? "Processing Payment..." : "Pay Now"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Checkout;
