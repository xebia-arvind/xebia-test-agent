import { useContext } from "react";
import { CartContext } from "../context/CartContext";
import { Link } from "react-router-dom";

function Cart() {
    const { cart, updateQuantity, removeItem } = useContext(CartContext);

    const total = cart.reduce(
        (sum, item) => sum + item.price * item.quantity,
        0
    );

    return (
        <div className="container mt-4">
            <h2>Your Cart</h2>

            {cart.map((item) => (
                <div className="card mb-3 p-3" key={item.id}>
                    <div className="d-flex justify-content-between align-items-center">
                        <div>
                            <h5>{item.name}</h5>
                            <p>₹{item.price}</p>
                        </div>

                        <div>
                            <input
                                type="number"
                                min="1"
                                value={item.quantity}
                                onChange={(e) =>
                                    updateQuantity(item.id, parseInt(e.target.value))
                                }
                                className="form-control"
                                style={{ width: "80px" }}
                            />
                        </div>

                        <div>
                            <button
                                className="btn btn-danger"
                                onClick={() => removeItem(item.id)}
                            >
                                Remove
                            </button>
                        </div>
                    </div>
                </div>
            ))}

            <h4>Total: ₹{total}</h4>

            <Link to="/checkout" className="btn btn-primary mt-3">
                Proceed to Checkout
            </Link>
        </div>
    );
}

export default Cart;
