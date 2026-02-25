import { Link } from "react-router-dom";
import { useContext } from "react";
import { CartContext } from "../context/CartContext";

function ProductCard({ product }) {
    const { toggleWishlist, isWishlisted } = useContext(CartContext);
    const wishlisted = isWishlisted(product.id);

    return (
        <div className="col-md-4 mb-4">
            <div className="card h-100 shadow-sm">
                <img
                    src={product.image}
                    className="card-img-top"
                    alt={product.name}
                    style={{ height: "250px", objectFit: "cover" }}
                />
                <div className="card-body text-center">
                    <h5>{product.name}</h5>
                    <p className="text-success fw-bold">₹{product.price}</p>
                    <div className="d-flex justify-content-center gap-2">
                        <Link id={`product_view_details_${product.id}`} className="btn btn-primary" to={`/product/${product.id}`}>
                            View Details
                        </Link>
                        <button
                            type="button"
                            className={`btn ${wishlisted ? "btn-warning" : "btn-outline-warning"}`}
                            onClick={() => toggleWishlist(product)}
                        >
                            {wishlisted ? "Wishlisted" : "Wishlist"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default ProductCard;
