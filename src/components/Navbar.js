import { Link } from "react-router-dom";
import { useContext } from "react";
import { CartContext } from "../context/CartContext";

function Navbar() {
    const { cart, wishlist } = useContext(CartContext);

    const totalItems = cart.reduce(
        (sum, item) => sum + item.quantity,
        0
    );
    const wishlistCount = wishlist.length;

    return (
        <nav className="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm">
            <div className="container">
                <Link className="navbar-brand fw-bold" to="/">
                    MyShop
                </Link>

                <div className="collapse navbar-collapse">
                    <ul className="navbar-nav me-auto">
                        <li className="nav-item">
                            <Link className="nav-link" to="/">Home</Link>
                        </li>
                        <li className="nav-item">
                            <Link className="nav-link" to="/">Products</Link>
                        </li>
                        <li className="nav-item">
                            <Link className="nav-link" to="/contact">Contact Us</Link>
                        </li>
                    </ul>

                    <div className="d-flex align-items-center gap-3">
                        <Link
                            to="/wishlist"
                            data-testid="wishlist-icon"
                            className="position-relative text-white"
                        >
                            <i className="bi bi-heart fs-4"></i>
                            {wishlistCount > 0 && (
                                <span className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-warning text-dark">
                                    {wishlistCount}
                                </span>
                            )}
                        </Link>

                        {/* Cart Icon */}
                        <Link
                            to="/cart"
                            data-testid="cart-icon"
                            className="position-relative text-white"
                        >
                            <i className="bi bi-bag fs-4"></i>

                            {totalItems > 0 && (
                                <span className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">
                                    {totalItems}
                                </span>
                            )}
                        </Link>
                    </div>
                </div>
            </div>
        </nav>
    );
}

export default Navbar;
