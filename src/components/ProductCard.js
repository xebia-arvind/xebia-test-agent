import { Link } from "react-router-dom";

function ProductCard({ product }) {
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
                    <Link id={`product_view_details_${product.id}`} className="btn btn-primary" to={`/product/${product.id}`}>
                        View Details
                    </Link>
                </div>
            </div>
        </div>
    );
}

export default ProductCard;
