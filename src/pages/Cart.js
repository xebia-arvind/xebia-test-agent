import { useContext, useState } from "react";
import { CartContext } from "../context/CartContext";
import { Link } from "react-router-dom";

function Cart() {
    const { cart, updateQuantity, removeItem, appliedCoupon, applyCoupon, removeCoupon } = useContext(CartContext);
    const [couponCode, setCouponCode] = useState("");
    const [error, setError] = useState("");

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

    const handleApplyCoupon = () => {
        try {
            setError("");
            applyCoupon(couponCode);
            setCouponCode("");
        } catch (err) {
            setError(err.message);
        }
    };

    return (
        <div className="container mt-4">
            <h2 className="mb-4">Your Shopping Cart</h2>

            <div className="row">
                <div className="col-md-8">
                    {cart.length === 0 ? (
                        <div className="text-center p-5 bg-light rounded h-100 d-flex flex-column justify-content-center">
                            <h4>Your cart is empty</h4>
                            <Link to="/" className="btn btn-primary mt-3 align-self-center">Start Shopping</Link>
                        </div>
                    ) : (
                        cart.map((item) => (
                            <div className="card mb-3 p-3 shadow-sm border-0" key={item.id}>
                                <div className="row align-items-center">
                                    <div className="col-2">
                                        <img src={item.image} alt={item.name} className="img-fluid rounded" />
                                    </div>
                                    <div className="col-4">
                                        <h5 className="mb-1">{item.name}</h5>
                                        <p className="text-muted mb-0">₹{item.price}</p>
                                    </div>
                                    <div className="col-3">
                                        <input
                                            type="number"
                                            min="1"
                                            value={item.quantity}
                                            onChange={(e) =>
                                                updateQuantity(item.id, parseInt(e.target.value))
                                            }
                                            className="form-control text-center"
                                            style={{ width: "70px" }}
                                        />
                                    </div>
                                    <div className="col-3 text-end">
                                        <p className="fw-bold mb-2">₹{item.price * item.quantity}</p>
                                        <button
                                            className="btn btn-sm btn-outline-danger"
                                            onClick={() => removeItem(item.id)}
                                        >
                                            <i className="bi bi-trash me-1"></i> Remove
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                </div>

                <div className="col-md-4">
                    <div className="card p-4 shadow-sm border-0 bg-light">
                        <h5 className="mb-4">Order Summary</h5>

                        <div className="d-flex justify-content-between mb-2">
                            <span>Subtotal</span>
                            <span>₹{subtotal}</span>
                        </div>

                        {/* Coupon Section */}
                        <div className="my-3" data-testid="coupon-section">
                            <label className="form-label small text-muted">Have a coupon?</label>
                            <div className="input-group">
                                <input
                                    type="text"
                                    className="form-control"
                                    placeholder="Enter code"
                                    value={couponCode}
                                    onChange={(e) => setCouponCode(e.target.value)}
                                    disabled={!!appliedCoupon || cart.length === 0}
                                />
                                <button
                                    className="btn btn-dark"
                                    onClick={handleApplyCoupon}
                                    disabled={!!appliedCoupon || !couponCode || cart.length === 0}
                                >
                                    Apply
                                </button>
                            </div>
                            {error && <div className="text-danger small mt-1">{error}</div>}
                            {appliedCoupon && (
                                <div className="bg-success bg-opacity-10 text-success p-2 rounded mt-2 d-flex justify-content-between align-items-center">
                                    <span className="small fw-bold">Coupon {appliedCoupon.code} applied!</span>
                                    <button className="btn btn-sm p-0 text-success" onClick={removeCoupon}>
                                        <i className="bi bi-x-circle-fill"></i>
                                    </button>
                                </div>
                            )}
                        </div>

                        {discount > 0 && (
                            <div className="d-flex justify-content-between mb-2 text-danger">
                                <span>Discount</span>
                                <span>-₹{discount}</span>
                            </div>
                        )}

                        <hr />

                        <div className="d-flex justify-content-between mb-4 mt-2">
                            <span className="h5 mb-0">Total</span>
                            <span className="h5 mb-0 fw-bold text-primary">₹{total}</span>
                        </div>

                        <Link to="/checkout" className={`btn btn-primary w-100 py-3 rounded-pill fw-bold shadow-sm ${cart.length === 0 ? 'disabled' : ''}`}>
                            Proceed to Checkout
                        </Link>

                        <Link to="/" className="btn btn-link w-100 mt-2 text-decoration-none text-muted small">
                            Continue Shopping
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Cart;
