import { useContext } from "react";
import { Link } from "react-router-dom";
import { CartContext } from "../context/CartContext";

function Wishlist() {
    const { wishlist, removeFromWishlist, moveWishlistToCart } = useContext(CartContext);

    return (
        <div className="container mt-4">
            <h2>Your Wishlist</h2>

            {wishlist.length === 0 && (
                <div className="alert alert-info mt-3">
                    Wishlist is empty. Browse products and add your favorites.
                </div>
            )}

            {wishlist.map((item) => (
                <div className="card mb-3 p-3" key={item.id}>
                    <div className="d-flex justify-content-between align-items-center">
                        <div>
                            <h5>{item.name}</h5>
                            <p className="mb-0">₹{item.price}</p>
                        </div>

                        <div className="d-flex gap-2">
                            <button
                                className="btn btn-primary"
                                onClick={() => moveWishlistToCart(item.id)}
                            >
                                Move to Cart
                            </button>
                            <button
                                className="btn btn-outline-danger"
                                onClick={() => removeFromWishlist(item.id)}
                            >
                                Remove
                            </button>
                        </div>
                    </div>
                </div>
            ))}

            <Link to="/" className="btn btn-outline-secondary mt-2">
                Continue Shopping
            </Link>
        </div>
    );
}

export default Wishlist;
